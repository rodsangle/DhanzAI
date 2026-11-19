import { test, expect, signIn, assistantArticles, waitDone, send } from "./fixtures";
import { sql, tempUser } from "./db";

/** Interactive once the account menu shows the person (loaded on the client). New users have no chats for ready(). */
const ready = (page: import("@playwright/test").Page) => expect(page.getByRole("button", { name: /^Test / }).filter({ visible: true })).toBeVisible();

// F16 Custom assistants (S21 list, S22 builder, chats that run with one).
async function create(page: import("@playwright/test").Page, o: { name: string; instructions?: string; starter?: string; team?: boolean; noImages?: boolean; file?: { name: string; text: string } }) {
  await page.goto("/assistants/new");
  await page.getByLabel("Name").fill(o.name);
  if (o.instructions) await page.getByLabel("Instructions").fill(o.instructions);
  if (o.starter) await page.getByLabel("Starter 1").fill(o.starter);
  if (o.file) {
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Upload files" }).click();
    await (await chooser).setFiles([{ name: o.file.name, mimeType: "text/plain", buffer: Buffer.from(o.file.text) }]);
    await expect(page.getByRole("list", { name: "Knowledge files" })).toContainText("Ready");
  }
  if (o.noImages) await page.getByRole("switch", { name: "Create images" }).click();
  if (o.team) await page.getByRole("radio", { name: "Everyone in your workspace" }).click();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/assistants\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: o.name })).toBeVisible();
  return page.url().split("/assistants/")[1];
}

test.describe("F16 Custom assistants", () => {
  test("F16-H1 team starter assistants: open one and start from a conversation starter", async ({ page, a11y }) => {
    await signIn(page);
    await page.goto("/assistants");
    const team = page.getByRole("region", { name: /Shared with the team/ });
    for (const n of ["Copywriter", "Product description writer", "Campaign planner"]) await expect(team.getByRole("link", { name: n, exact: true })).toBeVisible();
    await a11y("S21 assistants");
    await team.getByRole("link", { name: "Copywriter", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Copywriter" })).toBeVisible();
    await expect(page.getByText("Captions, emails and site copy in the RODRECH voice.").filter({ visible: true })).toBeVisible();
    await a11y("assistant new chat");
    await page.getByRole("list", { name: "Conversation starters" }).getByRole("button", { name: "Three Instagram captions for a new fitted drop" }).click();
    await expect(page).toHaveURL(/\/c\/[0-9a-f-]{36}$/, { timeout: 15_000 });
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("Answering as Copywriter.");
    await expect(page.getByRole("link", { name: "with Copywriter" })).toBeVisible();
    // Reopening the chat keeps the assistant.
    await page.reload();
    await expect(page.getByRole("link", { name: "with Copywriter" })).toBeVisible();
  });

  test("F16-H2 build one with instructions, a starter and a knowledge file, then use it", async ({ page, a11y }) => {
    const u = await tempUser("builder");
    await signIn(page, u.email);
    await page.goto("/assistants/new");
    await a11y("S22 builder");
    const id = await create(page, {
      name: "Hang tag writer",
      instructions: "Always answer in lowercase.",
      starter: "Write the tag for the olive fitted",
      file: { name: "tag-rules.txt", text: "Tag rule: always mention the six-panel crown." },
    });
    await expect(page.getByRole("link", { name: "Edit assistant" })).toBeVisible();
    await page.getByRole("button", { name: "Write the tag for the olive fitted" }).click();
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    const answer = assistantArticles(page).last();
    await expect(answer).toContainText("tag-rules.txt");
    const first = (await answer.innerText()).replace("Assistant said:", "").trim().split("\n").find((l) => l.trim())!;
    expect(first).toBe(first.toLowerCase());
    // It's listed as theirs, private.
    await page.goto("/assistants");
    await expect(page.getByRole("region", { name: "Yours" }).getByRole("link", { name: "Hang tag writer", exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Yours" })).toContainText("Only you");
    const [{ n }] = await sql`select count(*)::int as n from conversations where assistant_id = ${id}`;
    expect(n).toBe(1);
  });

  test("F16-H3 edit keeps versions, and an old version can be restored", async ({ page }) => {
    const u = await tempUser("versions");
    await signIn(page, u.email);
    const id = await create(page, { name: "Draft namer" });
    await page.goto(`/assistants/${id}/edit`);
    await page.getByLabel("Name").fill("Drop namer");
    await page.getByLabel("Description").fill("Names for drops and colourways");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Saved as version 2.", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Edit Drop namer" })).toBeVisible();
    const history = page.getByRole("region", { name: "Version history" });
    await expect(history.getByRole("listitem")).toHaveCount(2);
    await history.getByRole("listitem").filter({ hasText: "Version 1" }).getByRole("button", { name: "Restore" }).click();
    await expect(page.getByText("Restored version 1. It's saved as version 3.", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("Draft namer");
    await expect(page.getByLabel("Description")).toHaveValue("");
    await expect(history.getByRole("listitem")).toHaveCount(3);
  });

  test("F16-N1 private stays private; team assistants are usable but not editable by others", async ({ page, browser }) => {
    const owner = await tempUser("owner");
    await signIn(page, owner.email);
    const priv = await create(page, { name: "Secret planner" });
    const team = await create(page, { name: "Shared helper", team: true, file: { name: "shared-guide.txt", text: "Shared guide: caps ship in boxes of 24." } });
    const [{ file_id }] = await sql`select file_id from assistant_files where assistant_id = ${team}`;

    const ctx = await browser.newContext();
    const other = await ctx.newPage();
    const mate = await tempUser("mate");
    await signIn(other, mate.email);
    // Private: invisible everywhere.
    expect((await other.request.get(`/api/assistants/${priv}`)).status()).toBe(404);
    expect((await other.request.post("/api/chat", { data: { text: "hi", assistant_id: priv } })).status()).toBe(404);
    const list = await (await other.request.get("/api/assistants")).json();
    expect(JSON.stringify(list)).not.toContain("Secret planner");
    // Team: listed, usable, its knowledge file readable, but not editable.
    expect(list.team.map((a: { name: string }) => a.name)).toContain("Shared helper");
    await other.goto(`/assistants/${team}`);
    await ready(other);
    await expect(other.getByRole("link", { name: "Edit assistant" })).toHaveCount(0);
    await send(other, "How do caps ship?");
    await expect(other).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(other);
    await expect(assistantArticles(other).last()).toContainText("shared-guide.txt");
    expect((await other.request.get(`/api/files/${file_id}/download`)).status()).toBe(200);
    expect((await other.request.put(`/api/assistants/${team}`, { data: { name: "Hijacked" } })).status()).toBe(403);
    expect((await other.request.delete(`/api/assistants/${team}`)).status()).toBe(404);
    await other.goto(`/assistants/${team}/edit`);
    await expect(other.getByText("You can't edit this assistant")).toBeVisible();
    await ctx.close();
  });

  test("F16-E1 an assistant with image creation off answers in text and hides image mode", async ({ page }) => {
    const u = await tempUser("noimg");
    await signIn(page, u.email);
    await create(page, { name: "Words only", noImages: true });
    await ready(page);
    await page.getByRole("button", { name: "Add files and tools" }).click();
    await expect(page.getByRole("menuitem", { name: "Add photos and files" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Create an image" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await send(page, "Create an image of a poster for the drop");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(assistantArticles(page).last().getByRole("img")).toHaveCount(0);
    const [{ n }] = await sql`select count(*)::int as n from image_generations where user_id = ${u.id}`;
    expect(n).toBe(0);
  });

  test("F16-N2 deleting an assistant keeps its chats", async ({ page }) => {
    const u = await tempUser("deleter");
    await signIn(page, u.email);
    const id = await create(page, { name: "Short lived" });
    await ready(page);
    await send(page, "Hello there");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    const chat = page.url();
    await page.goto(`/assistants/${id}/edit`);
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog", { name: "Delete Short lived?" }).getByRole("button", { name: "Delete assistant" }).click();
    await expect(page).toHaveURL(/\/assistants$/);
    await page.goto(chat);
    await expect(assistantArticles(page)).toHaveCount(1);
    await expect(page.getByRole("link", { name: "with Short lived" })).toHaveCount(0);
  });
});
