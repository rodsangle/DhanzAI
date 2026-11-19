import { test, expect, signIn, composer, waitDone, assistantArticles } from "./fixtures";
import { fillDailyUsage, sql, tempUser } from "./db";

const ready = (page: import("@playwright/test").Page) => expect(page.getByRole("button", { name: /^Test / }).filter({ visible: true })).toBeVisible();

// F17 Composer tools: slash commands (S05).
test.describe("F17 Slash commands", () => {
  test("F17-H1 /image turns on image mode and keeps the rest of the message empty", async ({ page, a11y }) => {
    const u = await tempUser("slash");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    await composer(page).click();
    await page.keyboard.type("/ima");
    const list = page.getByRole("listbox", { name: "Commands" });
    await expect(list.getByRole("option", { name: /Create an image/ })).toBeVisible();
    await a11y("composer slash commands");
    await page.keyboard.press("Enter");
    await expect(composer(page)).toHaveValue("");
    await expect(page.getByRole("button", { name: "Image mode on. Turn off" })).toBeVisible();
    await expect(composer(page)).toHaveAttribute("placeholder", "Describe the image: subject, style, setting");
  });

  test("F17-H2 /search by keyword, and keyboard: arrows move, Escape closes", async ({ page }) => {
    const u = await tempUser("slash");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    await composer(page).click();
    await page.keyboard.type("/");
    const list = page.getByRole("listbox", { name: "Commands" });
    const options = list.getByRole("option");
    await expect(options.first()).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
    await expect(composer(page)).toHaveValue("/");
    await composer(page).fill("");
    await page.keyboard.type("/sear");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Web search on. Turn off" })).toBeVisible();
  });

  test("F17-H3 /<assistant name> opens that assistant; /<project> opens the project", async ({ page }) => {
    await signIn(page);
    await page.goto("/");
    await expect(page.getByRole("button", { name: /^Dante/ }).filter({ visible: true })).toBeVisible();
    await composer(page).click();
    await page.keyboard.type("/copy");
    const list = page.getByRole("listbox", { name: "Commands" });
    await list.getByRole("option", { name: /^Copywriter Assistant$/ }).click();
    await expect(page).toHaveURL(/\/assistants\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { level: 1, name: "Copywriter" })).toBeVisible();

    // Projects: make one, then open it with "/".
    const name = `Slash drop ${Date.now()}`;
    const res = await page.request.post("/api/projects", { data: { name } });
    expect(res.ok()).toBeTruthy();
    const { id } = await res.json();
    await page.goto("/");
    await composer(page).click();
    await page.keyboard.type("/slash dr");
    await list.getByRole("option", { name: `${name} Project` }).click();
    await expect(page).toHaveURL(new RegExp(`/project/${id}$`));
  });

  test("F17-E1 a slash later in the message is just text; unknown command shows no list", async ({ page }) => {
    const u = await tempUser("slash");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    await composer(page).click();
    await page.keyboard.type("compare 50/50 split /image");
    await expect(page.getByRole("listbox", { name: "Commands" })).toBeHidden();
    await composer(page).fill("");
    await page.keyboard.type("/zzzz");
    await expect(page.getByRole("listbox", { name: "Commands" })).toBeHidden();
    // Enter with no list open sends the text as a normal message.
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(assistantArticles(page)).toHaveCount(1);
  });
});

// S05 usage state: warn before the daily cap.
test.describe("F17 Usage warning", () => {
  test("F17-H4 no warning with plenty left; a warning near the cap that stays dismissed today", async ({ page, a11y }) => {
    const u = await tempUser("usage");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    await expect(page.getByText(/left today/)).toBeHidden();

    await fillDailyUsage(u.id, "message", 493); // 7 of 500 left: under the 100 warning line
    await page.reload();
    await ready(page);
    const banner = page.getByRole("status").filter({ hasText: "7 messages left today" });
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("You've used 493 of today's 500");
    await a11y("usage warning");
    await banner.getByRole("button", { name: "Dismiss" }).click();
    await expect(banner).toBeHidden();
    await page.reload();
    await ready(page);
    await expect(page.getByText(/messages left today/)).toBeHidden();
  });

  test("F17-H5 the count goes down as you send; one left reads in the singular", async ({ page }) => {
    const u = await tempUser("usage");
    await signIn(page, u.email);
    await fillDailyUsage(u.id, "message", 498);
    await page.goto("/");
    await ready(page);
    await expect(page.getByText("2 messages left today")).toBeVisible();
    await composer(page).fill("Short tagline for a black fitted");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(page.getByText("1 message left today")).toBeVisible();
  });

  test("F17-H6 images: warning only in image mode; at the image cap, chat still works", async ({ page }) => {
    const u = await tempUser("usage");
    await signIn(page, u.email);
    await fillDailyUsage(u.id, "image", 100);
    await page.goto("/");
    await ready(page);
    await expect(page.getByText(/today's images/)).toBeHidden();
    await composer(page).click();
    await page.keyboard.type("/image");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert").filter({ hasText: "You've made today's images" })).toBeVisible();
    await expect(composer(page)).toBeEnabled();
  });
});

// S05 dictation: speech to text into the composer.
async function speechCalls(page: import("@playwright/test").Page) {
  const log = await (await page.request.get("http://localhost:4010/__log")).json();
  return (log.calls as { path: string; model?: string; filename?: string; type?: string; auth?: string }[]).filter((c) => c.path === "/v1/audio/transcriptions");
}

test.describe("F17 Dictation", () => {
  test("F17-H7 record, finish, and the words land in the composer (added to what's there)", async ({ page, context, a11y }) => {
    await context.grantPermissions(["microphone"]);
    const before = (await speechCalls(page)).length;
    const u = await tempUser("dict");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    await composer(page).fill("Note:");
    await page.getByRole("button", { name: "Dictate" }).click();
    const bar = page.getByRole("group", { name: "Dictation" });
    await expect(bar).toBeVisible();
    await expect(bar).toContainText("0:01", { timeout: 5_000 });
    await expect(page.getByRole("button", { name: "Send message" })).toBeHidden();
    await a11y("composer dictating");
    await bar.getByRole("button", { name: "Finish dictation" }).click();
    await expect(composer(page)).toHaveValue("Note: Drop the black fitted on Friday at noon.");
    await expect(page.getByRole("button", { name: "Dictate" })).toBeVisible();
    const calls = (await speechCalls(page)).slice(before);
    expect(calls).toHaveLength(1);
    expect(calls[0].model).toBe("gpt-transcribe");
    expect(calls[0].type).toMatch(/^audio\/webm/);
    expect(calls[0].auth).toBe("Bearer test-openai");
    // Nothing kept: no file row for the recording.
    const [{ n }] = await sql`select count(*)::int as n from files where owner_id = ${u.id}`;
    expect(n).toBe(0);
    const [{ q }] = await sql`select coalesce(sum(quantity), 0)::int as q from usage_events where user_id = ${u.id} and metric = 'voice_second'`;
    expect(q).toBeGreaterThanOrEqual(1);
  });

  test("F17-E2 cancel throws the recording away; a blocked microphone explains what to do", async ({ page, context }) => {
    await context.grantPermissions(["microphone"]);
    const u = await tempUser("dict");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    const before = (await speechCalls(page)).length;
    await page.getByRole("button", { name: "Dictate" }).click();
    await page.getByRole("group", { name: "Dictation" }).getByRole("button", { name: "Cancel dictation" }).click();
    await expect(page.getByRole("button", { name: "Dictate" })).toBeVisible();
    await expect(composer(page)).toHaveValue("");
    await page.waitForTimeout(500);
    expect((await speechCalls(page)).length).toBe(before);

    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("blocked", "NotAllowedError"));
    });
    await page.reload();
    await ready(page);
    await page.getByRole("button", { name: "Dictate" }).click();
    await expect(page.getByText("Microphone access is blocked. Allow it in your browser's site settings, then try again.").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Dictate" })).toBeEnabled();
  });

  test("F17-N1 the speech endpoint needs sign-in, real audio, and a sane size", async ({ page, request }) => {
    const anon = await request.post("/api/transcribe", { multipart: { audio: { name: "a.webm", mimeType: "audio/webm", buffer: Buffer.from("x") } } });
    expect(anon.status()).toBe(401);
    const u = await tempUser("dict");
    await signIn(page, u.email);
    const notAudio = await page.request.post("/api/transcribe", { multipart: { audio: { name: "a.txt", mimeType: "text/plain", buffer: Buffer.from("hello") } } });
    expect(notAudio.status()).toBe(415);
    const empty = await page.request.post("/api/transcribe", { multipart: { seconds: "3" } });
    expect(empty.status()).toBe(400);
    const big = await page.request.post("/api/transcribe", { multipart: { audio: { name: "a.webm", mimeType: "audio/webm", buffer: Buffer.alloc(25 * 1024 * 1024) } } });
    expect(big.status()).toBe(413);
    const ok = await page.request.post("/api/transcribe", { multipart: { audio: { name: "a.webm", mimeType: "audio/webm", buffer: Buffer.from("fake-audio") }, seconds: "2" } });
    expect(ok.status()).toBe(200);
    expect((await ok.json()).text).toBe("Drop the black fitted on Friday at noon.");
  });
});
