import { test, expect, signIn, newChat, waitDone } from "./fixtures";
import { sql, tempUser } from "./db";
import type { Browser, Page } from "@playwright/test";

// F13 Write a page in Space (S12): pages, subpages, inherited access, comments, AI edits, chat → page,
// and the no-lost-edits guard with live updates between two people.

const ready = (page: Page) => expect(page.getByRole("button", { name: /^Test / }).filter({ visible: true })).toBeVisible();
// Next keeps the previous page mounted (hidden), so always scope to what's visible.
const editorBox = (page: Page) => page.getByRole("textbox", { name: "Page content" }).filter({ visible: true });
const titleBox = (page: Page) => page.getByLabel("Page title", { exact: true }).filter({ visible: true });
const status = (page: Page) => page.getByRole("status").filter({ visible: true }).filter({ hasText: /Saved|Saving|Unsaved|Not saved|Updated by|View only|You can comment/ });

async function api<T = unknown>(page: Page, method: string, url: string, data?: unknown): Promise<T> {
  const res = await page.request.fetch(url, { method, data });
  expect(res.ok(), `${method} ${url} → ${res.status()} ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

async function second(browser: Browser, email: string) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await signIn(page, email);
  return { ctx, page };
}

async function newPageFromHome(page: Page, title: string, body: string) {
  await page.goto("/space");
  await ready(page);
  await page.getByRole("button", { name: "New page", exact: true }).click();
  await expect(page).toHaveURL(/\/space\/[0-9a-f-]{36}$/);
  await titleBox(page).fill(title);
  await editorBox(page).click();
  await page.keyboard.type(body);
  await expect(status(page)).toHaveText("Saved", { timeout: 10_000 });
  return page.url().split("/space/")[1];
}

test.describe("F13 Space", () => {
  test("F13-H1 write a page with formatting; it saves itself and is there after a reload", async ({ page, a11y }) => {
    const u = await tempUser("space");
    await signIn(page, u.email);
    await page.goto("/space");
    await ready(page);
    await expect(page.getByRole("heading", { name: "Pages", level: 2, exact: true }).filter({ visible: true })).toBeVisible();
    await a11y("S12 space home");
    const id = await newPageFromHome(page, "FW26 drop brief", "Six fitteds in washed black and bone.");
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Bulleted list" }).click();
    await page.keyboard.type("Shoot on the roof");
    await page.keyboard.press("Enter");
    await page.keyboard.type("Launch Friday at noon");
    await expect(status(page)).toHaveText("Saved", { timeout: 10_000 });
    await a11y("S12 page editor");

    // In the tree, and kept after a reload.
    const tree = page.getByRole("navigation", { name: "Pages" }).filter({ visible: true });
    await expect(tree.getByRole("link", { name: "FW26 drop brief" })).toBeVisible();
    await page.reload();
    await expect(titleBox(page)).toHaveValue("FW26 drop brief");
    await expect(editorBox(page).locator("ul li")).toHaveCount(2);
    const [row] = await sql`select title, text, version from pages where id = ${id}`;
    expect(row.title).toBe("FW26 drop brief");
    expect(row.text).toContain("Launch Friday at noon");
    expect(row.version).toBeGreaterThan(1);

    // Found by search, by a word inside it.
    await page.keyboard.press("ControlOrMeta+k");
    await page.getByRole("dialog").getByRole("combobox").fill("roof");
    const hit = page.getByRole("dialog").getByRole("option", { name: /FW26 drop brief/ });
    await expect(hit).toBeVisible();
    await hit.click();
    await expect(page).toHaveURL(new RegExp(`/space/${id}$`));
  });

  test("F13-H2 subpages: add one inside, breadcrumbs, and deleting the parent deletes both", async ({ page }) => {
    const u = await tempUser("space");
    await signIn(page, u.email);
    const parent = await newPageFromHome(page, "Campaign plan", "Overview.");
    await page.getByRole("button", { name: "Page options" }).click();
    await page.getByRole("menuitem", { name: "Add a page inside" }).click();
    await expect(page).not.toHaveURL(new RegExp(parent));
    await titleBox(page).fill("Shot list");
    const breadcrumb = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(breadcrumb.getByRole("link", { name: "Campaign plan" })).toBeVisible();
    await breadcrumb.getByRole("link", { name: "Campaign plan" }).click();
    await expect(page.getByRole("region", { name: "Pages inside" }).getByRole("link", { name: "Shot list" })).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: "Page options" }).click();
    await page.getByRole("menuitem", { name: "Delete page" }).click();
    await expect(page.getByRole("dialog", { name: "Delete this page?" })).toContainText("Pages inside it are deleted too");
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Deleted the page and 1 inside it").first()).toBeVisible();
    await expect(page).toHaveURL(/\/space$/);
    const [{ n }] = await sql`select count(*)::int as n from pages pg join spaces s on s.id = pg.space_id where s.owner_id = ${u.id}`;
    expect(n).toBe(0);
  });

  test("F13-H3 share a page: access flows to its subpages, not its siblings; view-only can't edit", async ({ page, browser, a11y }) => {
    const owner = await tempUser("space");
    const mate = await tempUser("mate");
    await signIn(page, owner.email);
    const other = await second(browser, mate.email); // signs in once so they're a member
    const parent = await api<{ id: string }>(page, "POST", "/api/pages", { title: "Lookbook" });
    const child = await api<{ id: string }>(page, "POST", "/api/pages", { parent_page_id: parent.id, title: "Lookbook looks" });
    const sibling = await api<{ id: string }>(page, "POST", "/api/pages", { title: "Private notes" });

    await page.goto(`/space/${parent.id}`);
    await page.getByRole("button", { name: "Share" }).click();
    const dialog = page.getByRole("dialog", { name: /Share “Lookbook”/ });
    await dialog.getByLabel("Add a teammate").selectOption({ label: `Test mate (${mate.email})` });
    await dialog.getByLabel("Access", { exact: true }).selectOption("view");
    await dialog.getByRole("button", { name: "Share", exact: true }).click();
    await expect(dialog.getByRole("list", { name: "People with access" })).toContainText("Test mate");
    await a11y("S12 share page");
    await dialog.getByRole("button", { name: "Done" }).click();

    // The teammate: parent and child yes (read-only), sibling no.
    await other.page.goto(`/space/${child.id}`);
    await expect(titleBox(other.page)).toHaveValue("Lookbook looks");
    await expect(status(other.page)).toHaveText("View only");
    await expect(editorBox(other.page)).toHaveAttribute("contenteditable", "false");
    await expect(other.page.getByRole("button", { name: "Ask AI" })).toBeHidden();
    const tree = other.page.getByRole("navigation", { name: "Pages" }).filter({ visible: true });
    await expect(tree.getByRole("link", { name: "Lookbook", exact: true })).toBeVisible();
    await expect(tree.getByRole("link", { name: "Private notes" })).toBeHidden();
    expect((await other.page.request.get(`/api/pages/${sibling.id}`)).status()).toBe(404);
    // Writes are refused server-side too.
    expect((await other.page.request.patch(`/api/pages/${child.id}`, { data: { title: "Hijacked" } })).status()).toBe(403);
    expect((await other.page.request.post("/api/pages", { data: { parent_page_id: parent.id, title: "Sneaky" } })).status()).toBe(403);
    expect((await other.page.request.delete(`/api/pages/${child.id}`)).status()).toBe(403);

    // The child's share dialog shows the access as inherited.
    await other.page.getByRole("button", { name: "Share" }).click();
    await expect(other.page.getByRole("dialog").getByText("From “Lookbook”")).toBeVisible();
    await expect(other.page.getByRole("dialog")).toContainText("Only people who can edit can change who has access.");

    // Upgrade to edit: the teammate can now edit the child.
    await api(page, "POST", `/api/pages/${parent.id}/access`, { user_id: mate.id, level: "edit" });
    const r = await other.page.request.patch(`/api/pages/${child.id}`, { data: { title: "Lookbook looks v2" } });
    expect(r.status()).toBe(200);
    // Removing access: gone again.
    const access = await api<{ people: { id: string; user_id: string }[] }>(page, "GET", `/api/pages/${parent.id}/access`);
    await api(page, "DELETE", `/api/page-access/${access.people.find((p) => p.user_id === mate.id)!.id}`);
    expect((await other.page.request.get(`/api/pages/${child.id}`)).status()).toBe(404);
    await other.ctx.close();
  });

  test("F13-H4 team space open to everyone; personal space stays private", async ({ page, browser }) => {
    const owner = await tempUser("space");
    const mate = await tempUser("mate");
    await signIn(page, owner.email);
    const other = await second(browser, mate.email);
    await page.goto("/space");
    await ready(page);
    await page.getByRole("button", { name: "New space" }).click();
    const d = page.getByRole("dialog", { name: "New space" });
    await d.getByLabel("Name").fill(`Drops ${owner.id.slice(0, 6)}`);
    await d.getByRole("radio", { name: "Everyone in your workspace can comment" }).click();
    await d.getByRole("button", { name: "Create space" }).click();
    await expect(page.getByText(/^Created Drops/).first()).toBeVisible();
    const { spaces } = await api<{ spaces: { id: string; name: string; is_personal: boolean }[] }>(page, "GET", "/api/spaces");
    const team = spaces.find((s) => s.name.startsWith("Drops"))!;
    const mine = spaces.find((s) => s.is_personal)!;
    const teamPage = await api<{ id: string }>(page, "POST", "/api/pages", { space_id: team.id, title: "Drop calendar" });
    const privatePage = await api<{ id: string }>(page, "POST", "/api/pages", { space_id: mine.id, title: "Diary" });

    const seen = await api<{ spaces: { id: string }[]; pages: { id: string; level: string }[] }>(other.page, "GET", "/api/spaces");
    expect(seen.spaces.map((s) => s.id)).toContain(team.id);
    expect(seen.spaces.map((s) => s.id)).not.toContain(mine.id);
    expect(seen.pages.find((p) => p.id === teamPage.id)?.level).toBe("comment");
    expect(seen.pages.find((p) => p.id === privatePage.id)).toBeUndefined();
    // Comment level: can comment, can't add pages or edit.
    expect((await other.page.request.post(`/api/pages/${teamPage.id}/comments`, { data: { body: "Move launch to 1pm?" } })).status()).toBe(200);
    expect((await other.page.request.post("/api/pages", { data: { space_id: team.id, title: "Mine now" } })).status()).toBe(403);
    // Personal spaces can't be opened to everyone.
    expect((await page.request.patch(`/api/spaces/${mine.id}`, { data: { everyone_level: "view" } })).status()).toBe(400);
    await other.ctx.close();
  });

  test("F13-H5 comments: on a passage, reply, resolve, reopen; counts on the page", async ({ page, browser }) => {
    const owner = await tempUser("space");
    const mate = await tempUser("mate");
    await signIn(page, owner.email);
    const other = await second(browser, mate.email);
    const id = await newPageFromHome(page, "Caption deck", "Built for the block. Made to last.");
    await api(page, "POST", `/api/pages/${id}/access`, { user_id: mate.id, level: "comment" });

    // Select a passage and comment on it.
    await editorBox(page).getByText("Built for the block.").dblclick();
    await page.keyboard.press("Home");
    await page.keyboard.press("Shift+End");
    await page.getByRole("button", { name: "Comments" }).click();
    const panel = page.getByRole("complementary", { name: "Comments" });
    await expect(panel).toContainText("On “Built for the block. Made to last.”");
    await panel.getByLabel("New comment").fill("Swap “block” for “street”?");
    await panel.getByRole("button", { name: "Comment", exact: true }).click();
    const open = panel.getByRole("list", { name: "Open comments" });
    await expect(open.getByRole("listitem")).toHaveCount(1);

    // The commenter replies.
    await other.page.goto(`/space/${id}`);
    await expect(status(other.page)).toHaveText("You can comment");
    await other.page.getByRole("button", { name: /Comments/ }).click();
    const theirs = other.page.getByRole("complementary", { name: "Comments" });
    await expect(theirs).toContainText("Swap “block” for “street”?");
    await theirs.getByLabel("Reply").fill("Street works.");
    await theirs.getByRole("button", { name: "Reply" }).click();
    await expect(theirs).toContainText("Street works.");
    // They can't resolve someone else's thread (comment level, not the author).
    await expect(theirs.getByRole("button", { name: "Resolve" })).toBeHidden();

    // The owner resolves; it moves to resolved; reopen brings it back.
    await expect(open).toContainText("Street works.", { timeout: 15_000 });
    await open.getByRole("button", { name: "Resolve" }).click();
    await expect(panel.getByText("No open comments.")).toBeVisible();
    await panel.getByRole("button", { name: "Show 1 resolved" }).click();
    await expect(panel.getByRole("list", { name: "Resolved comments" })).toContainText(`Resolved by Test space`);
    await panel.getByRole("list", { name: "Resolved comments" }).getByRole("button", { name: "Reopen" }).click();
    await expect(open.getByRole("listitem")).toHaveCount(1);
    // A viewer can read but not add.
    const viewer = await tempUser("view");
    const v = await second(browser, viewer.email);
    await api(page, "POST", `/api/pages/${id}/access`, { user_id: viewer.id, level: "view" });
    expect((await v.page.request.post(`/api/pages/${id}/comments`, { data: { body: "hi" } })).status()).toBe(403);
    expect((await v.page.request.get(`/api/pages/${id}/comments`)).status()).toBe(200);
    await other.ctx.close();
    await v.ctx.close();
  });

  test("F13-H6 Ask AI: suggest an edit for a selection, accept it, or discard it", async ({ page, a11y }) => {
    const u = await tempUser("space");
    await signIn(page, u.email);
    await newPageFromHome(page, "Product copy", "Structured six-panel crown. Embroidered logo. Adjustable strap.");
    await editorBox(page).click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.getByRole("button", { name: "Ask AI" }).click();
    const d = page.getByRole("dialog", { name: "Ask AI to edit" });
    await expect(d).toContainText("Changes the selected passage.");
    await a11y("S12 ask AI");
    await d.getByRole("button", { name: "Turn into a bulleted list" }).click();
    const proposal = page.getByRole("region", { name: "Suggested edit" });
    await expect(proposal.locator("li")).toHaveCount(3);
    // Nothing changed yet.
    await expect(editorBox(page).locator("li")).toHaveCount(0);
    await proposal.getByRole("button", { name: "Accept" }).click();
    await expect(editorBox(page).locator("li")).toHaveCount(3);
    await expect(status(page)).toHaveText("Saved", { timeout: 10_000 });

    // Whole page, discarded: no change.
    await editorBox(page).click();
    await page.keyboard.press("End");
    await page.getByRole("button", { name: "Ask AI" }).click();
    await page.getByRole("dialog", { name: "Ask AI to edit" }).getByLabel("What should change?").fill("make it all caps");
    await page.getByRole("button", { name: "Suggest edit" }).click();
    await expect(page.getByRole("region", { name: "Suggested edit" })).toContainText("STRUCTURED SIX-PANEL CROWN.");
    await page.getByRole("button", { name: "Discard" }).click();
    await expect(editorBox(page)).toContainText("Structured six-panel crown.");
  });

  test("F13-H7 save a chat as a page: drafted from the thread, linked back, opens in Space", async ({ page }) => {
    const u = await tempUser("space");
    await signIn(page, u.email);
    await newChat(page, "Plan the FW26 fitted launch week");
    await waitDone(page);
    await page.getByRole("button", { name: "Save as a page" }).click();
    const toastOpen = page.getByRole("button", { name: "Open" }).filter({ visible: true });
    await expect(page.getByText(/^Saved “Plan the FW26 fitted launch week” to your pages/).first()).toBeVisible({ timeout: 15_000 });
    const chatUrl = page.url();
    await toastOpen.click();
    await expect(page).toHaveURL(/\/space\/[0-9a-f-]{36}$/);
    await expect(titleBox(page)).toHaveValue("Plan the FW26 fitted launch week");
    await expect(editorBox(page).getByRole("heading", { name: "Summary" })).toBeVisible();
    await page.getByRole("button", { name: "Page options" }).click();
    await page.getByRole("menuitem", { name: "Open the chat it came from" }).click();
    await expect(page).toHaveURL(chatUrl);
  });

  test("F13-E1 two people on one page: live update when idle, no lost edits when both type", async ({ page, browser, allowConsole }) => {
    allowConsole(/Failed to load resource|ERR_FAILED/); // the test cuts the presence poll on purpose
    const a = await tempUser("space");
    const b = await tempUser("mate");
    await signIn(page, a.email);
    const other = await second(browser, b.email);
    const id = await newPageFromHome(page, "Shared draft", "First line.");
    await api(page, "POST", `/api/pages/${id}/access`, { user_id: b.id, level: "edit" });

    // B opens it; each sees the other is here.
    await other.page.goto(`/space/${id}`);
    await expect(editorBox(other.page)).toContainText("First line.");
    await expect(page.getByRole("group", { name: /Also here: Test mate/ })).toBeVisible({ timeout: 10_000 });

    // B types while A is idle: A's page updates in place.
    await editorBox(other.page).click();
    await other.page.keyboard.press("ControlOrMeta+End");
    await other.page.keyboard.type(" Added by B.");
    await expect(status(other.page)).toHaveText("Saved", { timeout: 10_000 });
    await expect(editorBox(page)).toContainText("First line. Added by B.", { timeout: 15_000 });

    // Both type before either sees the other's save: the second save is stopped, nothing is lost.
    await other.page.route(`**/api/pages/${id}/state`, (r) => r.abort()); // B stops hearing about A for now
    await page.route(`**/api/pages/${id}/state`, (r) => r.abort());
    await editorBox(page).click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.type(" A's edit.");
    await expect(status(page)).toHaveText("Saved", { timeout: 10_000 });
    await other.page.keyboard.type(" B's second edit.");
    const banner = other.page.getByRole("status").filter({ hasText: "changed this page while you were editing" });
    await expect(banner).toBeVisible({ timeout: 10_000 });
    await expect(banner).toContainText("Test space changed this page while you were editing");
    let [row] = await sql`select text from pages where id = ${id}`;
    expect(row.text).toContain("A's edit.");
    expect(row.text).not.toContain("B's second edit.");
    // B keeps theirs: it replaces A's, by choice.
    await banner.getByRole("button", { name: "Keep mine" }).click();
    await expect(banner).toBeHidden();
    [row] = await sql`select text from pages where id = ${id}`;
    expect(row.text).toContain("B's second edit.");
    // A stale save straight to the API is refused too.
    const stale = await page.request.patch(`/api/pages/${id}`, { data: { doc: { type: "doc", content: [] }, text: "", base_version: 1 } });
    expect(stale.status()).toBe(409);
    expect((await stale.json()).latest.text).toContain("B's second edit.");
    await other.ctx.close();
  });

  test("F13-N1 bad input and other people's spaces", async ({ page, browser }) => {
    const a = await tempUser("space");
    const b = await tempUser("mate");
    await signIn(page, a.email);
    const other = await second(browser, b.email);
    const { spaces } = await api<{ spaces: { id: string; is_personal: boolean }[] }>(page, "GET", "/api/spaces");
    const mine = spaces.find((s) => s.is_personal)!;
    // Someone else's personal space: invisible and closed.
    expect((await other.page.request.post("/api/pages", { data: { space_id: mine.id, title: "x" } })).status()).toBe(404);
    expect((await other.page.request.post(`/api/spaces/${mine.id}/access`, { data: { user_id: b.id, level: "edit" } })).status()).toBe(404);
    expect((await other.page.request.delete(`/api/spaces/${mine.id}`)).status()).toBe(404);
    // Can't delete your personal space; can't nest past the limit; can't share outside the workspace.
    expect((await page.request.delete(`/api/spaces/${mine.id}`)).status()).toBe(400);
    let parent = (await api<{ id: string }>(page, "POST", "/api/pages", { title: "L1" })).id;
    for (let i = 2; i <= 8; i++) parent = (await api<{ id: string }>(page, "POST", "/api/pages", { parent_page_id: parent, title: `L${i}` })).id;
    expect((await page.request.post("/api/pages", { data: { parent_page_id: parent, title: "L9" } })).status()).toBe(400);
    expect((await page.request.post(`/api/pages/${parent}/access`, { data: { user_id: "00000000-0000-4000-8000-000000000000", level: "view" } })).status()).toBe(400);
    // Garbage content and ids.
    expect((await page.request.patch(`/api/pages/${parent}`, { data: { doc: { type: "paragraph" }, base_version: 1 } })).status()).toBe(400);
    expect((await page.request.patch(`/api/pages/${parent}`, { data: { doc: { type: "doc", content: [] }, text: "" } })).status()).toBe(400);
    expect((await page.request.get("/api/pages/not-an-id")).status()).toBe(404);
    // A link to a page you can't see: a clear message, not a crash.
    await other.page.goto(`/space/${parent}`);
    await expect(other.page.getByRole("heading", { name: "Page not found" })).toBeVisible();
    // The AI's output can't carry script or script links into the page.
    const md = await api<{ html: string }>(page, "POST", `/api/pages/${parent}/ai`, { instruction: "keep it", selection: "<img src=x onerror=alert(1)> [x](javascript:alert(1))" });
    expect(md.html).not.toMatch(/<img|javascript:/i);
    await other.ctx.close();
  });
});
