import { test, expect, signIn, assistantArticles, composer, waitDone, send } from "./fixtures";
import { sql, tempUser } from "./db";

// F11 Connect an app and use it in chat (S20 Apps, approval cards, @mentions).
const MOCK = "http://localhost:4010";
const ready = (page: import("@playwright/test").Page) => expect(page.getByRole("button", { name: /^Test / }).filter({ visible: true })).toBeVisible();
const mockLog = async (page: import("@playwright/test").Page) => (await page.request.get(`${MOCK}/__log`)).json();

async function connect(page: import("@playwright/test").Page, name: "Google Drive" | "Slack") {
  await page.goto("/apps");
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name }) });
  await card.getByRole("link", { name: `Connect ${name}` }).click();
  await expect(page).toHaveURL(/\/apps\?connected=/);
  await expect(page.getByText(`${name} is connected`)).toBeVisible();
  return card;
}
async function ask(page: import("@playwright/test").Page, text: string) {
  await page.goto("/");
  await ready(page);
  await send(page, text);
  await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
  await waitDone(page);
  return assistantArticles(page).last();
}

test.describe("F11 Apps", () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post(`${MOCK}/__reset`);
  });

  test("F11-H1 connect Google Drive with your own account; tokens are stored encrypted", async ({ page, a11y }) => {
    const u = await tempUser("drive");
    await signIn(page, u.email);
    await page.goto("/apps");
    await ready(page);
    await a11y("S20 apps");
    const card = await connect(page, "Google Drive");
    await expect(card).toContainText("Connected as dante@rodrech.com");
    await a11y("S20 apps connected");
    const [t] = await sql`select t.access_token_enc, t.refresh_token_enc from app_tokens t join app_connections c on c.id = t.connection_id where c.user_id = ${u.id}`;
    expect(Buffer.from(t.access_token_enc).includes("g-at-1")).toBe(false);
    expect(Buffer.from(t.refresh_token_enc).includes("g-rt-1")).toBe(false);
    // Signed-in people can't read token rows at all.
    const [{ n }] = await sql.begin(async (q) => {
      await q`select set_config('request.jwt.claims', ${JSON.stringify({ sub: u.id, role: "authenticated" })}, true)`;
      await q`set local role authenticated`;
      return q`select count(*)::int as n from app_tokens`;
    });
    expect(n).toBe(0);
  });

  test("F11-H2 @mention Google Drive: it searches, reads the file and answers from it", async ({ page, a11y }) => {
    const u = await tempUser("mention");
    await signIn(page, u.email);
    await connect(page, "Google Drive");
    await page.goto("/");
    await ready(page);
    await composer(page).click();
    await page.keyboard.type("@Goo");
    const list = page.getByRole("listbox", { name: "Apps" });
    await expect(list.getByRole("option", { name: "@Google Drive" })).toBeVisible();
    await a11y("composer @mention");
    await page.keyboard.press("Enter");
    await expect(composer(page)).toHaveValue("@Google Drive ");
    await page.keyboard.type("find files about the FW26 lookbook brief and summarise it");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    const answer = assistantArticles(page).last();
    const activity = answer.getByRole("list", { name: "App activity" });
    await expect(activity).toContainText("Searched Google Drive for “FW26 lookbook brief”");
    await expect(activity).toContainText("Read a file from Google Drive");
    await expect(answer).toContainText("shoot on the roof at golden hour");
    const log = await mockLog(page);
    const api = log.calls.filter((c: { path: string }) => c.path.startsWith("/google/drive/"));
    expect(api.map((c: { path: string }) => c.path)).toEqual(["/google/drive/v3/files", "/google/drive/v3/files/doc-lookbook", "/google/drive/v3/files/doc-lookbook/export"]);
    expect(api.every((c: { auth: string }) => c.auth === "Bearer g-at-1")).toBe(true);
  });

  test("F11-H3 posting to Slack waits for approval; approve posts, decline doesn't", async ({ page, a11y }) => {
    const u = await tempUser("slack");
    await signIn(page, u.email);
    await connect(page, "Slack");
    const answer = await ask(page, "@Slack post “Drop is live at noon” to #drops");
    const card = answer.getByRole("region", { name: "Allow Slack to do this?" });
    await expect(card).toContainText("Post in #drops on Slack");
    await expect(card).toContainText("Drop is live at noon");
    await a11y("approval card");
    expect((await mockLog(page)).slackPosts).toHaveLength(0);
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(answer.getByRole("region", { name: "Slack action" })).toContainText("Approved");
    await expect(answer.getByRole("list", { name: "App activity" })).toContainText("Posted in #drops on Slack");
    await waitDone(page);
    expect((await mockLog(page)).slackPosts).toEqual([{ channel: "C0DROPS1", text: "Drop is live at noon" }]);
    // Reloading shows the same, decided card (no buttons).
    await page.reload();
    await expect(assistantArticles(page).last().getByRole("button", { name: "Approve" })).toHaveCount(0);

    await send(page, "@Slack post “Second note” to #general");
    await waitDone(page);
    const second = assistantArticles(page).last();
    await second.getByRole("region", { name: "Allow Slack to do this?" }).getByRole("button", { name: "Decline" }).click();
    await expect(second.getByRole("region", { name: "Slack action" })).toContainText("Declined");
    await expect(second).toContainText("Okay, I didn't do that.");
    expect((await mockLog(page)).slackPosts).toHaveLength(1);
  });

  test("F11-H4 permission levels: ask before every action, and Always allow", async ({ page }) => {
    const u = await tempUser("levels");
    await signIn(page, u.email);
    const card = await connect(page, "Google Drive");
    await card.getByLabel("When to ask you first").selectOption("always_ask");
    await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
    const answer = await ask(page, "@Google Drive find files about the size chart");
    const approval = answer.getByRole("region", { name: "Allow Google Drive to do this?" });
    await expect(approval).toContainText("Search Google Drive for “size chart”");
    await approval.getByRole("button", { name: "Always allow" }).click();
    await expect(answer.getByRole("list", { name: "App activity" })).toContainText("Searched Google Drive");
    await waitDone(page);
    const [c] = await sql`select always_allowed from app_connections where user_id = ${u.id}`;
    expect(c.always_allowed).toEqual(["drive_search"]);
    const again = await ask(page, "@Google Drive find files about the size chart again");
    await expect(again.getByRole("region", { name: /Google Drive/ })).toHaveCount(0);
    await expect(again.getByRole("list", { name: "App activity" })).toContainText("Searched Google Drive");
  });

  test("F11-H5 Shopify: connect a store, then an approved description update reaches the store", async ({ page }) => {
    const u = await tempUser("shop");
    await signIn(page, u.email);
    await page.goto("/apps");
    const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Shopify" }) });
    await card.getByLabel("Store address").fill("rodrech-test");
    await card.getByRole("button", { name: "Connect" }).click();
    await expect(page.getByText("Shopify is connected")).toBeVisible();
    await expect(card).toContainText("Connected as rodrech-test.myshopify.com");
    const answer = await ask(page, "@Shopify update the description for the olive fitted");
    await expect(answer.getByRole("list", { name: "App activity" })).toContainText("Searched Shopify products");
    const approval = answer.getByRole("region", { name: "Allow Shopify to do this?" });
    await expect(approval).toContainText("Olive fitted");
    await expect(approval).toContainText("Structured six-panel crown");
    expect((await mockLog(page)).shopify["101"]).toBe("<p>Old copy</p>");
    await approval.getByRole("button", { name: "Approve" }).click();
    await expect(answer.getByRole("list", { name: "App activity" })).toContainText("Updated the description of Olive fitted on Shopify");
    await waitDone(page);
    expect((await mockLog(page)).shopify["101"]).toContain("Structured six-panel crown");
  });

  test("F11-N1 forged callbacks, someone else's approval, disconnect and unconnected mentions", async ({ page, browser }) => {
    const u = await tempUser("guard");
    await signIn(page, u.email);
    // A callback without the matching signed state is refused.
    await page.goto("/api/apps/google_drive/callback?code=x&state=forged");
    await expect(page.getByText("That connection attempt expired or didn't match. Try again.")).toBeVisible();
    // A Shopify reply for a different store is refused.
    await page.goto("/api/apps/shopify/connect?shop=nota-store.example.com");
    await expect(page.getByText("Enter your store's .myshopify.com address.")).toBeVisible();
    // Mentioning an app that isn't connected says so.
    const answer = await ask(page, "@Slack search for drop dates");
    await expect(answer).toContainText("which isn't connected");

    await connect(page, "Slack");
    const pending = await ask(page, "@Slack post “Hi” to #drops");
    await expect(pending.getByRole("region", { name: "Allow Slack to do this?" })).toBeVisible();
    const [a] = await sql`select id from action_approvals where user_id = ${u.id} and decision = 'pending'`;
    const ctx = await browser.newContext();
    const other = await ctx.newPage();
    const mate = await tempUser("approver");
    await signIn(other, mate.email);
    expect((await other.request.post(`/api/approvals/${a.id}`, { data: { decision: "approve" } })).status()).toBe(404);
    expect(((await (await other.request.get("/api/apps")).json()) as { connection: unknown }[]).every((x) => x.connection === null)).toBe(true);
    await ctx.close();
    expect((await mockLog(page)).slackPosts).toHaveLength(0);
    // Twice: the second answer is refused.
    expect((await page.request.post(`/api/approvals/${a.id}`, { data: { decision: "deny" } })).ok()).toBe(true);
    expect((await page.request.post(`/api/approvals/${a.id}`, { data: { decision: "approve" } })).status()).toBe(409);

    // Disconnect revokes the token at Slack and forgets it.
    await page.goto("/apps");
    const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Slack" }) });
    await card.getByRole("button", { name: "Disconnect" }).click();
    await page.getByRole("dialog", { name: "Disconnect Slack?" }).getByRole("button", { name: "Disconnect" }).click();
    await expect(card.getByRole("link", { name: "Connect Slack" })).toBeVisible();
    expect((await mockLog(page)).revoked).toContain("slack");
    const [{ n }] = await sql`select count(*)::int as n from app_connections where user_id = ${u.id}`;
    expect(n).toBe(0);
  });

  test("F11-E1 an expired Google token is refreshed before use", async ({ page }) => {
    const u = await tempUser("refresh");
    await signIn(page, u.email);
    await connect(page, "Google Drive");
    await sql`update app_tokens set expires_at = now() - interval '1 minute' where connection_id in (select id from app_connections where user_id = ${u.id})`;
    const answer = await ask(page, "@Google Drive find files about the size chart");
    await expect(answer.getByRole("list", { name: "App activity" })).toContainText("Searched Google Drive");
    const log = await mockLog(page);
    expect(log.calls.some((c: { path: string; body: string }) => c.path === "/google/token" && c.body.includes("grant_type=refresh_token"))).toBe(true);
    expect(log.calls.filter((c: { path: string }) => c.path === "/google/drive/v3/files").at(-1).auth).toBe("Bearer g-at-2");
  });
});
