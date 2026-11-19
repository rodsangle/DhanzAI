import { test, expect, signIn, assistantArticles, newChat, send, waitDone } from "./fixtures";
import fs from "node:fs";
import path from "node:path";
import { strFromU8, unzipSync } from "fflate";
import { sql, tempUser } from "./db";

async function openSettings(page: import("@playwright/test").Page, name: RegExp, tab?: string) {
  await page.getByRole("button", { name }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  if (tab) await page.getByRole("tab", { name: tab }).click();
}

test.describe("F12 Personalize and F14 Account", () => {
  test("F12-H1 response style shapes new answers", async ({ page, a11y }) => {
    const u = await tempUser("pers");
    await signIn(page, u.email);
    await page.goto("/");
    await openSettings(page, /Test pers/, "Personalization");
    await page.getByLabel("How should it respond?").fill("Always lowercase. Short.");
    await a11y("S24 personalization");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Saved. New answers will follow these instructions.", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await newChat(page, "Write A Plan For The Drop");
    const line = (await assistantArticles(page).last().innerText()).replace("Assistant said:", "").trim().split("\n").find((l) => l.trim())!;
    expect(line).toBe(line.toLowerCase());
  });

  test("F12-H3 memory builds from chats, is used, can be corrected, and deleted", async ({ page, a11y }) => {
    test.setTimeout(120_000);
    const u = await tempUser("mem");
    await signIn(page, u.email);
    const first = await newChat(page, "I'm the creative lead and I run our headwear drops. Write a caption for the olive fitted.");
    // Memory updates in the background after the answer.
    await expect.poll(async () => (await (await page.request.get("/api/memory")).json()).body, { timeout: 15_000 })
      .toContain("I'm the creative lead and I run our headwear drops.");

    // A new chat uses memory and the related earlier chat, and lists both as sources.
    await newChat(page, "Write a caption for the bone snapback");
    const answer = assistantArticles(page).last();
    await expect(answer).toContainText("From memory: I'm the creative lead and I run our headwear drops.");
    const sources = answer.getByRole("list", { name: "Sources" });
    await expect(sources.getByRole("button", { name: "Memory" })).toBeVisible();
    const earlier = sources.getByRole("link", { name: /^Earlier chat:/ });
    await expect(earlier).toHaveAttribute("href", `/c/${first}`);
    await a11y("S04 answer with sources");

    // Correct it.
    await openSettings(page, /Test mem/, "Personalization");
    await page.getByRole("button", { name: "Manage" }).click();
    const box = page.getByLabel("Remembered");
    await expect(box).toHaveValue(/creative lead/);
    await a11y("S25 memory summary");
    await box.fill("- Goes by Dee. Brand director at RODRECH.");
    await page.getByRole("button", { name: "Save", exact: true }).last().click();
    await expect(page.getByText("Memory saved.", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await newChat(page, "Draft a launch tweet for the beanie");
    await expect(assistantArticles(page).last()).toContainText("From memory: Goes by Dee. Brand director at RODRECH.");

    // Delete it and turn it off: nothing remembered or used after that.
    await openSettings(page, /Test mem/, "Personalization");
    await page.getByRole("button", { name: "Manage" }).click();
    await page.getByRole("button", { name: "Delete memory and turn off" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Memory deleted and turned off.", { exact: true })).toBeVisible();
    await expect(page.getByRole("switch", { name: "Memory" })).not.toBeChecked();
    await expect(page.getByRole("switch", { name: "Reference chat history" })).toBeDisabled();
    await page.keyboard.press("Escape");
    await newChat(page, "Write a caption for the bone snapback again");
    await expect(assistantArticles(page).last()).not.toContainText("From memory");
    await expect(assistantArticles(page).last().getByRole("list", { name: "Sources" })).toHaveCount(0);
    expect((await (await page.request.get("/api/memory")).json()).body).toBe("");
  });

  test("F12-H4 chat history can be off while memory stays on", async ({ page }) => {
    const u = await tempUser("hist");
    await signIn(page, u.email);
    await newChat(page, "I'm on the wholesale team. Plan the olive fitted restock.");
    await expect.poll(async () => (await (await page.request.get("/api/memory")).json()).body, { timeout: 15_000 }).toContain("wholesale");
    await page.goto("/");
    await openSettings(page, /Test hist/, "Personalization");
    await page.getByRole("switch", { name: "Reference chat history" }).click();
    await expect(page.getByText("Earlier chats won't be used.", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await newChat(page, "Plan the olive fitted restock for spring");
    const answer = assistantArticles(page).last();
    await expect(answer).toContainText("From memory");
    await expect(answer).not.toContainText("earlier chat");
    await expect(answer.getByRole("list", { name: "Sources" }).getByRole("link")).toHaveCount(0);
  });

  test("F12-E2 temporary chats use no memory and aren't remembered", async ({ page }) => {
    const u = await tempUser("temp");
    await signIn(page, u.email);
    await newChat(page, "I'm the head of retail. Write a store sign.");
    await expect.poll(async () => (await (await page.request.get("/api/memory")).json()).body, { timeout: 15_000 }).toContain("head of retail");
    await sql`update memory_summaries set refreshed_at = now() - interval '2 hours' where user_id = ${u.id}`;
    await page.goto("/");
    await page.getByRole("button", { name: "Temporary chat" }).click();
    await send(page, "My secret codename is Falcon. Write a store sign.");
    await waitDone(page);
    await expect(assistantArticles(page).last()).not.toContainText("From memory");
    await page.waitForTimeout(1500);
    expect((await (await page.request.get("/api/memory")).json()).body).not.toContain("Falcon");
  });

  test("X-8 a shared link doesn't carry memory or earlier-chat sources", async ({ page }) => {
    const u = await tempUser("sharemem");
    await signIn(page, u.email);
    const earlier = await newChat(page, "I'm the photo lead. Plan the lookbook shoot.");
    await expect.poll(async () => (await (await page.request.get("/api/memory")).json()).body, { timeout: 15_000 }).toContain("photo lead");
    const id = await newChat(page, "Plan the lookbook shoot schedule");
    await expect(assistantArticles(page).last().getByRole("list", { name: "Sources" })).toBeVisible();
    const res = await page.request.post(`/api/conversations/${id}/share`);
    expect(res.ok()).toBeTruthy();
    const [row] = await sql`select snapshot::text as s from shared_links where conversation_id = ${id}`;
    expect(row.s).not.toContain('"sources"');
    expect(row.s).not.toContain(earlier);
  });

  test("F12-E1 fields stop at 3,000 characters", async ({ page }) => {
    const u = await tempUser("limit3k");
    await signIn(page, u.email);
    await page.goto("/");
    await openSettings(page, /Test limit3k/, "Personalization");
    await page.getByLabel("What should the assistant know about you?").fill("a".repeat(3001));
    await expect(page.getByLabel("What should the assistant know about you?")).toHaveValue("a".repeat(3000));
    await expect(page.getByText("3000 / 3,000")).toBeVisible();
  });

  test("F14-H1 dark theme persists and the name is kept", async ({ page, a11y }) => {
    const u = await tempUser("theme");
    await signIn(page, u.email);
    await page.goto("/");
    await openSettings(page, /Test theme/);
    await a11y("S23 general");
    await page.getByRole("radio", { name: "Dark" }).click();
    await page.keyboard.press("Escape");
    await page.reload();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.getByRole("button", { name: /Test theme/ })).toBeVisible();
    await a11y("S03 dark");
  });

  test("F14-H2 deleting a shared link in Data controls", async ({ page, context }) => {
    await signIn(page);
    await newChat(page, "Link managed from settings");
    await page.getByRole("button", { name: "Share", exact: true }).click();
    await page.getByRole("button", { name: "Create link" }).click();
    const url = await page.getByLabel("Link", { exact: true }).inputValue();
    await page.keyboard.press("Escape");
    await openSettings(page, /Dante/, "Data controls");
    const row = page.getByRole("listitem").filter({ hasText: "Link managed from settings" });
    await row.getByRole("button", { name: "Delete" }).click();
    await expect(row).toHaveCount(0);
    const view = await context.newPage();
    await view.goto(url);
    await expect(view.getByText("This link doesn't work")).toBeVisible();
  });

  test("F14-H4 export all data: a zip with chats, files and memory, emailed and signed-in only", async ({ page, browser, a11y }) => {
    test.setTimeout(90_000);
    const u = await tempUser("export");
    await signIn(page, u.email);
    await page.goto("/");
    await page.getByRole("button", { name: "Add files and tools" }).click();
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("menuitem", { name: "Add photos and files" }).click();
    await (await chooser).setFiles([{ name: "drop-notes.txt", mimeType: "text/plain", buffer: Buffer.from("Drop notes <b>bold</b>") }]);
    await expect(page.getByRole("list", { name: "Attachments" })).toContainText("ready");
    await send(page, "I'm the export tester. Summarise <these> notes & more");
    await waitDone(page);

    await openSettings(page, /Test export/, "Data controls");
    await page.getByRole("button", { name: "Export", exact: true }).click();
    await expect(page.getByText("Preparing your export. We'll email you when it's ready.", { exact: true })).toBeVisible();
    const download = page.getByRole("link", { name: "Download" });
    await expect(download).toBeVisible({ timeout: 30_000 });
    await a11y("S27 data controls with an export");
    const [file] = await Promise.all([page.waitForEvent("download"), download.click()]);
    expect(file.suggestedFilename()).toMatch(/^dhanz-gpt-export-\d{4}-\d{2}-\d{2}\.zip$/);
    const zip = unzipSync(new Uint8Array(fs.readFileSync(await file.path())));
    const text = (n: string) => strFromU8(zip[n]);
    expect(Object.keys(zip).sort()).toEqual(
      ["README.txt", "assistants.json", "chats.html", "chats.json", "files.json", "files/drop-notes.txt", "memory.md", "pages.json", "projects.json", "settings.json", "tasks.json"],
    );
    expect(text("files/drop-notes.txt")).toBe("Drop notes <b>bold</b>");
    expect(text("chats.html")).toContain("Summarise &lt;these&gt; notes &amp; more");
    expect(text("chats.html")).not.toContain("<these>");
    const chats = JSON.parse(text("chats.json"));
    expect(chats).toHaveLength(1);
    expect(chats[0].messages.map((m: { role: string }) => m.role)).toEqual(["user", "assistant"]);
    expect(text("memory.md")).toContain("I'm the export tester");

    // The email links to the download, which needs the owner's sign-in.
    const mail = fs.readFileSync(path.join(__dirname, "..", ".data", "outbox.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((m) => m.to === u.email);
    expect(mail).toHaveLength(1);
    expect(mail[0].subject).toBe("Your Dhanz GPT export is ready");
    const link = /(http\S+\/api\/account\/export\/[0-9a-f-]{36}\/download)/.exec(mail[0].text)![1];
    const path_ = new URL(link).pathname;
    const other = await browser.newContext();
    const anon = await other.request.get(path_, { maxRedirects: 0 });
    expect(anon.status()).toBe(401);
    const maya = await tempUser("notowner");
    await other.request.post("/api/auth/dev-login", { data: { email: maya.email } });
    expect((await other.request.get(path_)).status()).toBe(404);
    await other.close();

    // After 24 hours it's gone.
    await sql`update data_exports set expires_at = now() - interval '1 minute' where user_id = ${u.id}`;
    expect((await page.request.get(path_)).status()).toBe(410);
    expect((await (await page.request.get("/api/account/export")).json()).status).toBe("expired");
  });

  test("F14-E3 an export that never started is picked up by the cron sweep", async ({ page }) => {
    const u = await tempUser("sweep");
    await signIn(page, u.email);
    const [row] = await sql`insert into data_exports (user_id, created_at) values (${u.id}, now() - interval '3 minutes') returning id`;
    const res = await page.request.get("/api/cron/sweep", { headers: { Authorization: "Bearer local-test-secret" } });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).exports.ran).toBeGreaterThanOrEqual(1);
    const [after] = await sql`select status from data_exports where id = ${row.id}`;
    expect(after.status).toBe("ready");
  });

  test("F14-H5 delete all chats: every chat goes, files and memory stay", async ({ page }) => {
    const u = await tempUser("wipe");
    await signIn(page, u.email);
    await newChat(page, "I'm the wipe tester. First chat");
    const second = await newChat(page, "Second chat");
    await page.request.patch(`/api/conversations/${second}`, { data: { archived: true } });
    await expect.poll(async () => (await (await page.request.get("/api/memory")).json()).body, { timeout: 15_000 }).toContain("wipe tester");
    const [{ files }] = await sql`select count(*)::int as files from files where owner_id = ${u.id}`;
    await page.goto(`/c/${second}`);
    await openSettings(page, /Test wipe/, "Data controls");
    await page.getByRole("button", { name: "Delete all", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Delete all chats?" });
    await expect(dialog).toContainText("can't be undone");
    await dialog.getByRole("button", { name: "Delete all chats" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("What are we making today");
    const [{ n }] = await sql`select count(*)::int as n from conversations where user_id = ${u.id}`;
    expect(n).toBe(0);
    const [{ files: after }] = await sql`select count(*)::int as files from files where owner_id = ${u.id}`;
    expect(after).toBe(files);
    expect((await (await page.request.get("/api/memory")).json()).body).toContain("wipe tester");
    // Another person's chats are untouched.
    const [{ others }] = await sql`select count(*)::int as others from conversations c join profiles p on p.id = c.user_id where p.email = 'dante@rodrech.com'`;
    expect(others).toBeGreaterThan(0);
  });

  test("F14-N1 + H3 account deletion needs DELETE, then really deletes", async ({ page, a11y }) => {
    const u = await tempUser("bye");
    await signIn(page, u.email);
    await page.goto("/");
    await openSettings(page, /Test bye/, "Account");
    await page.getByRole("button", { name: "Delete account" }).click();
    const dialog = page.getByRole("dialog", { name: "Delete your account?" });
    await dialog.getByLabel("Type DELETE").fill("delete");
    await expect(dialog.getByRole("button", { name: "Delete account" })).toBeDisabled();
    await a11y("delete account dialog");
    await dialog.getByLabel("Type DELETE").fill("DELETE");
    await dialog.getByRole("button", { name: "Delete account" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Work email").fill(u.email);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("isn't part of this workspace")).toBeVisible();
  });
});
