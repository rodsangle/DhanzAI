import fs from "node:fs";
import path from "node:path";
import { test, expect, signIn, composer, assistantArticles, userArticles, waitDone, send, ready } from "./fixtures";
import { sql, asUserCount, tempUser, userIdFor } from "./db";

const fixture = (name: string, mimeType: string) => ({ name, mimeType, buffer: fs.readFileSync(path.join(__dirname, "files", name)) });
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function pickFiles(page: import("@playwright/test").Page, files: { name: string; mimeType: string; buffer: Buffer }[]) {
  await page.getByRole("button", { name: "Add files and tools" }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("menuitem", { name: "Add photos and files" }).click();
  await (await chooser).setFiles(files);
}
const chip = (page: import("@playwright/test").Page, name: string) =>
  page.getByRole("list", { name: "Attachments" }).getByRole("listitem").filter({ hasText: name });

test.describe("F02 Chat with a file", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/");
    await ready(page);
  });

  test("F02-H1 upload a text file and ask about it", async ({ page, a11y }) => {
    await pickFiles(page, [{ name: "fw26-brief.txt", mimeType: "text/plain", buffer: Buffer.from("FW26 brief: headwear-led drop.\nFriday noon.") }]);
    await expect(chip(page, "fw26-brief.txt")).toContainText("ready");
    await a11y("composer with attachment");
    await send(page, "Summarise this brief");
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("fw26-brief.txt");
    await expect(assistantArticles(page).last()).toContainText("headwear-led");
  });

  test("F02-H3 a PDF is read", async ({ page }) => {
    await pickFiles(page, [fixture("fw26-tech-pack.pdf", "application/pdf")]);
    await expect(chip(page, "fw26-tech-pack.pdf")).toContainText("ready");
    await send(page, "Summarise this");
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText('It starts: "FW26 Snapback Tech Pack"');
  });

  test("F02-H4 a Word document is read", async ({ page }) => {
    await pickFiles(page, [fixture("holiday-brief.docx", DOCX)]);
    await expect(chip(page, "holiday-brief.docx")).toContainText("ready");
    await send(page, "What's the hero product?");
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText('It starts: "Holiday campaign brief"');
  });

  test("F02-N3 a file over 2M tokens is refused at upload, with the reason", async ({ page }) => {
    const huge = Buffer.alloc(8_400_000, "word ");
    await pickFiles(page, [{ name: "everything.txt", mimeType: "text/plain", buffer: huge }]);
    await expect(chip(page, "everything.txt")).toContainText("about 2.1M tokens, over the 2M limit for one file", { timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  test("F02-N4 files too long for one message are refused before anything is saved", async ({ page }) => {
    const before = (await sql`select count(*)::int as n from messages where role = 'user'`)[0].n;
    await pickFiles(page, [{ name: "season-notes.txt", mimeType: "text/plain", buffer: Buffer.alloc(700_000, "note ") }]);
    await expect(chip(page, "season-notes.txt")).toContainText("ready");
    await send(page, "Summarise these notes");
    const banner = page.getByRole("alert").filter({ hasText: "Message not sent" });
    await expect(banner).toContainText("season-notes.txt is about 175k tokens, more than one message can read (150k)");
    await expect(banner).toContainText("Add it to a project instead");
    await expect(chip(page, "season-notes.txt")).toBeVisible();
    expect((await sql`select count(*)::int as n from messages where role = 'user'`)[0].n).toBe(before);
  });

  test("F02-N5 a damaged PDF says it can't be read", async ({ page }) => {
    await pickFiles(page, [{ name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 this is not really a pdf") }]);
    await expect(chip(page, "broken.pdf")).toContainText("We couldn't read this file");
  });

  test("X-7 file text chunks follow the file's access rules", async ({ page }) => {
    await pickFiles(page, [fixture("holiday-brief.docx", DOCX)]);
    await expect(chip(page, "holiday-brief.docx")).toContainText("ready");
    const [f] = await sql`select id from files where name = 'holiday-brief.docx' order by created_at desc limit 1`;
    const chunks = (q: import("postgres").TransactionSql) => q<{ n: number }[]>`select count(*)::int as n from file_chunks where file_id = ${f.id}`;
    expect(await asUserCount(await userIdFor("dante@rodrech.com"), chunks)).toBeGreaterThan(0);
    const other = await tempUser("chunks");
    expect(await asUserCount(other.id, chunks)).toBe(0);
  });

  test("F02-H5 reuse a Library file from the + menu, without uploading again", async ({ page, a11y }) => {
    await pickFiles(page, [{ name: "reuse-notes.txt", mimeType: "text/plain", buffer: Buffer.from("Reuse notes: the olive fitted ships first.") }]);
    await expect(chip(page, "reuse-notes.txt")).toContainText("ready");
    await send(page, "Keep this for later");
    await waitDone(page);
    const [{ n: before }] = await sql`select count(*)::int as n from files where name = 'reuse-notes.txt'`;

    await page.goto("/");
    await ready(page);
    await page.getByRole("button", { name: "Add files and tools" }).click();
    await page.getByRole("menuitem", { name: "Add from Library" }).click();
    const dialog = page.getByRole("dialog", { name: "Add from Library" });
    await dialog.getByLabel("Search your files").fill("reuse");
    await a11y("Library picker");
    await dialog.getByRole("checkbox", { name: "reuse-notes.txt" }).first().click();
    await dialog.getByRole("button", { name: "Attach 1 file" }).click();
    await expect(chip(page, "reuse-notes.txt")).toContainText("ready");
    await send(page, "What ships first?");
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText('It starts: "Reuse notes: the olive fitted ships first."');
    const [{ n: after }] = await sql`select count(*)::int as n from files where name = 'reuse-notes.txt'`;
    expect(after).toBe(before);
  });

  test("F02-H6 'Use in a chat' from the Library starts a chat with the file attached", async ({ page }) => {
    await pickFiles(page, [{ name: "library-brief.txt", mimeType: "text/plain", buffer: Buffer.from("Library brief: shoot on the roof at 5pm.") }]);
    await expect(chip(page, "library-brief.txt")).toContainText("ready");
    await send(page, "Save this");
    await waitDone(page);
    await page.goto("/library");
    await page.getByRole("button", { name: "Use library-brief.txt in a chat" }).first().click();
    await expect(page).toHaveURL(/\/$/);
    await expect(chip(page, "library-brief.txt")).toContainText("ready");
    await send(page, "When is the shoot?");
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText('It starts: "Library brief: shoot on the roof at 5pm."');
    // Handed over once: a fresh new chat starts empty.
    await page.goto("/");
    await ready(page);
    await expect(page.getByRole("list", { name: "Attachments" })).toHaveCount(0);
  });

  test("F02-H2 drag and drop an image", async ({ page }) => {
    const dt = await page.evaluateHandle((b64) => {
      const d = new DataTransfer();
      d.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], "moodboard.png", { type: "image/png" }));
      return d;
    }, PNG.toString("base64"));
    await page.dispatchEvent("#main", "dragover", { dataTransfer: dt });
    await expect(page.getByText("Drop files to attach them")).toBeVisible();
    await page.dispatchEvent("#main", "drop", { dataTransfer: dt });
    await expect(chip(page, "moodboard.png")).toContainText("ready");
    await send(page, "What do you see?");
    await waitDone(page);
    await expect(userArticles(page).first().getByRole("img", { name: "moodboard.png" })).toBeVisible();
  });

  test("F02-E1 empty file is refused", async ({ page }) => {
    await pickFiles(page, [{ name: "empty.txt", mimeType: "text/plain", buffer: Buffer.alloc(0) }]);
    await expect(chip(page, "empty.txt")).toContainText("This file is empty");
    await composer(page).fill("Read it");
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
    await page.getByRole("button", { name: "Remove empty.txt" }).click();
    await expect(page.getByRole("button", { name: "Send message" })).toBeEnabled();
  });

  test("F02-E2 more than 10 files", async ({ page }) => {
    const files = Array.from({ length: 11 }, (_, i) => ({ name: `f${i}.txt`, mimeType: "text/plain", buffer: Buffer.from(`file ${i}`) }));
    await pickFiles(page, files);
    await expect(page.getByText("Attach up to 10 files at a time.", { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Attachments" }).getByRole("listitem")).toHaveCount(10);
  });

  test("F02-E3 emoji and accents in a file name", async ({ page }) => {
    const name = "lookbook ✨ été.txt";
    await pickFiles(page, [{ name, mimeType: "text/plain", buffer: Buffer.from("notes") }]);
    await expect(chip(page, name)).toContainText("ready");
    await send(page, "Keep this");
    await waitDone(page);
    await page.goto("/library");
    await expect(page.getByText(name)).toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByLabel("Search chats, projects and files").fill("été");
    await expect(page.getByRole("option", { name, exact: true })).toBeVisible();
  });

  test("F02-E4 can't send while a file is uploading", async ({ page }) => {
    await page.route("**/api/files/*/upload", async (r) => {
      await new Promise((res) => setTimeout(res, 2500));
      await r.continue();
    });
    await pickFiles(page, [{ name: "slow.txt", mimeType: "text/plain", buffer: Buffer.from("slow upload") }]);
    await composer(page).fill("Read this");
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
    await composer(page).press("Enter");
    await expect(page).toHaveURL("/");
    await expect(chip(page, "slow.txt")).toContainText("ready", { timeout: 10_000 });
    await composer(page).press("Enter");
    await expect(page).toHaveURL(/\/c\//);
    await waitDone(page);
  });

  test("F02-E5 long paste becomes an attachment", async ({ page }) => {
    await composer(page).focus();
    await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.setData("text/plain", "line of pasted copy\n".repeat(400));
      document.activeElement!.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    });
    await expect(chip(page, "Pasted text.txt")).toContainText("ready");
    await expect(composer(page)).toHaveValue("");
  });

  test("F02-N1 oversize upload is refused by the API", async ({ page }) => {
    const res = await page.request.post("/api/files", { data: { name: "big.mov", mime: "video/quicktime", bytes: 600_000_000 } });
    expect(res.status()).toBe(413);
    expect((await res.json()).error).toMatch(/512 MB/);
  });
});
