import type { Page } from "@playwright/test";
import { test, expect, signIn, assistantArticles, waitDone, send } from "./fixtures";
import { sql } from "./db";

// Round 5: image shape and edits (S13/F06), Think longer with its reasoning summary (S06),
// Read aloud, recordings with transcripts, and the Library's storage bar (S11).

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function tool(page: Page, name: string) {
  await page.getByRole("button", { name: "Add files and tools" }).click();
  await page.getByRole("menuitem", { name }).click();
}
async function pickFiles(page: Page, files: { name: string; mimeType: string; buffer: Buffer }[]) {
  await page.getByRole("button", { name: "Add files and tools" }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("menuitem", { name: "Add photos and files" }).click();
  await (await chooser).setFiles(files);
}
const imgSize = (page: Page, name: string | RegExp) =>
  assistantArticles(page).last().getByRole("img", { name }).evaluate((i: HTMLImageElement) => ({ w: i.naturalWidth, h: i.naturalHeight }));

test.describe("F06 image shape and edits", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/");
  });

  test("F06-H2 landscape image, and Try again keeps the shape", async ({ page, a11y }) => {
    await tool(page, "Create an image");
    await page.getByRole("button", { name: /^Image shape: Square/ }).click();
    await page.getByRole("menuitem", { name: "Landscape" }).click();
    await expect(page.getByRole("button", { name: /^Image shape: Landscape/ })).toBeVisible();
    await a11y("composer with image shape");
    const prompt = "a wide street at dusk with neon signs";
    await send(page, prompt);
    await waitDone(page);
    const first = await imgSize(page, prompt);
    expect(first.w).toBeGreaterThan(first.h);
    // Image mode turns off after sending; the shape picker goes with it.
    await expect(page.getByRole("button", { name: /^Image shape:/ })).toHaveCount(0);

    await page.getByRole("button", { name: "Try again" }).last().click();
    await page.getByRole("menuitem", { name: "Try again" }).first().click();
    await expect(page.getByRole("group", { name: "Answer version 2 of 2" })).toBeVisible();
    await waitDone(page);
    const again = await imgSize(page, prompt);
    expect(again.w).toBeGreaterThan(again.h);
  });

  test("F06-H3 a follow-up like 'make it warmer' edits the last image and keeps its shape", async ({ page }) => {
    await tool(page, "Create an image");
    await page.getByRole("button", { name: /^Image shape: Square/ }).click();
    await page.getByRole("menuitem", { name: "Portrait" }).click();
    await send(page, "a cap on a wooden table");
    await waitDone(page);
    await expect(assistantArticles(page).last().getByRole("img")).toBeVisible();

    await send(page, "make it warmer, golden hour light");
    await waitDone(page);
    const last = assistantArticles(page).last();
    await expect(last).toContainText("the edited image");
    await expect(last.getByRole("img", { name: "make it warmer, golden hour light" })).toBeVisible();
    const edited = await imgSize(page, "make it warmer, golden hour light");
    expect(edited.h).toBeGreaterThan(edited.w);

    // A question about the image gets a text answer, not another image.
    await send(page, "what colours are in it?");
    await waitDone(page);
    await expect(assistantArticles(page).last().getByRole("img")).toHaveCount(0);
  });

  test("F06-H4 an attached photo is edited, not replaced", async ({ page }) => {
    await pickFiles(page, [{ name: "shoot.png", mimeType: "image/png", buffer: PNG }]);
    await expect(page.getByRole("list", { name: "Attachments" }).getByRole("listitem").filter({ hasText: "shoot.png" })).toContainText("ready");
    await tool(page, "Create an image");
    await send(page, "turn this into a poster with a bold title");
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("the edited image");
  });
});

test.describe("S06 Think longer", () => {
  test("TH-H1 think longer shows a reasoning summary, and Try again thinks longer too", async ({ page, a11y }) => {
    await signIn(page);
    await page.goto("/");
    await tool(page, "Think longer");
    const chip = page.getByRole("button", { name: "Think longer on. Turn off" });
    await expect(chip).toBeVisible();
    await a11y("composer with think longer");
    await send(page, "Plan a three-week product launch");
    await waitDone(page);
    await expect(chip).toHaveCount(0);
    const answer = assistantArticles(page).last();
    const summary = answer.getByText("Thought process");
    await expect(summary).toBeVisible();
    await expect(answer.getByText("Demo reasoning summary")).toBeHidden();
    await summary.click();
    await expect(answer.getByText("Demo reasoning summary")).toBeVisible();
    await a11y("reasoning summary open");

    await page.getByRole("button", { name: "Try again" }).last().click();
    await page.getByRole("menuitem", { name: "Try again" }).first().click();
    await expect(page.getByRole("group", { name: "Answer version 2 of 2" })).toBeVisible();
    await waitDone(page);
    await expect(assistantArticles(page).last().getByText("Thought process")).toBeVisible();

    // Without it, the demo model doesn't show a reasoning summary.
    await send(page, "Thanks, now a shorter version");
    await waitDone(page);
    await expect(assistantArticles(page).last().getByText("Thought process")).toHaveCount(0);
  });

  test("TH-N1 think longer and image mode don't mix", async ({ page }) => {
    await signIn(page);
    await page.goto("/");
    await tool(page, "Create an image");
    await page.getByRole("button", { name: "Add files and tools" }).click();
    await expect(page.getByRole("menuitem", { name: "Think longer" })).toHaveCount(0);
    await page.keyboard.press("Escape");
  });
});

test.describe("Read aloud, recordings and storage", () => {
  test.beforeEach(async ({ page }) => signIn(page));

  test("RA-H1 read an answer aloud, and stop", async ({ page, a11y }) => {
    await page.goto("/");
    await send(page, "Give me two tips for a product photo");
    await waitDone(page);
    const toolbar = page.getByRole("toolbar", { name: "Answer actions" }).last();
    const speech = page.waitForResponse((r) => /\/api\/messages\/[^/]+\/speech\?part=0$/.test(r.url()));
    await toolbar.getByRole("button", { name: "Read aloud" }).click();
    const res = await speech;
    expect(res.status()).toBe(200);
    expect(Number(res.headers()["x-speech-parts"])).toBeGreaterThanOrEqual(1);
    // The demo voice is a short silent clip: it plays, then the button comes back.
    await expect(toolbar.getByRole("button", { name: "Read aloud" })).toBeVisible({ timeout: 10_000 });
    await a11y("answer actions with read aloud");

    await toolbar.getByRole("button", { name: "Read aloud" }).click();
    const stopBtn = toolbar.getByRole("button", { name: "Stop reading" });
    if (await stopBtn.isVisible().catch(() => false)) await stopBtn.click();
    await expect(toolbar.getByRole("button", { name: "Read aloud" })).toBeVisible();
  });

  test("RA-N1 an answer that doesn't exist can't be read aloud", async ({ page }) => {
    const res = await page.request.get("/api/messages/00000000-0000-4000-8000-000000000000/speech?part=0");
    expect(res.status()).toBe(404);
  });

  test("AU-H1 an uploaded recording gets a transcript the chat can read", async ({ page }) => {
    await page.goto("/");
    await pickFiles(page, [{ name: "voice-note.webm", mimeType: "audio/webm", buffer: Buffer.from("not really audio, the stand-in only checks the form") }]);
    await expect(page.getByRole("list", { name: "Attachments" }).getByRole("listitem").filter({ hasText: "voice-note.webm" })).toContainText("ready");
    const [row] = await sql`select extracted_text from files where name = 'voice-note.webm' order by created_at desc limit 1`;
    expect(row.extracted_text).toContain("Transcript of the recording voice-note.webm");
    expect(row.extracted_text).toContain("Drop the black fitted on Friday at noon.");
  });

  test("S11-H2 Library shows storage used against the quota", async ({ page, a11y }) => {
    await page.goto("/library");
    const bar = page.getByRole("progressbar", { name: "Storage" });
    await expect(bar).toBeVisible();
    await expect(page.getByText(/of 20 GB used$/)).toBeVisible();
    expect(Number(await bar.getAttribute("aria-valuenow"))).toBeGreaterThanOrEqual(0);
    await a11y("S11 library with storage");
  });
});
