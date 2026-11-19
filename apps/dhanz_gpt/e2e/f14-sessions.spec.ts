import { test, expect, signIn } from "./fixtures";
import { sql, tempUser } from "./db";
import type { Browser } from "@playwright/test";

const PHONE_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const WINDOWS_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0";

async function otherDevice(browser: Browser, email: string, userAgent: string) {
  const ctx = await browser.newContext({ userAgent });
  const page = await ctx.newPage();
  await signIn(page, email);
  return { ctx, page };
}

async function openSecurity(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /^Test / }).filter({ visible: true }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await page.getByRole("tab", { name: "Security" }).click();
}

// F14 Account: S28 per-device sessions.
test.describe("F14 Signed-in devices", () => {
  test("F14-H6 lists each device, this one first; signing one out ends it on its next request", async ({ page, browser, a11y }) => {
    const u = await tempUser("sess");
    await signIn(page, u.email);
    const phone = await otherDevice(browser, u.email, PHONE_UA);
    const pc = await otherDevice(browser, u.email, WINDOWS_UA);

    await openSecurity(page);
    const list = page.getByRole("list", { name: "Signed-in devices" });
    await expect(list.getByRole("listitem")).toHaveCount(3);
    await expect(list.getByRole("listitem").first()).toContainText("This device");
    await expect(list).toContainText("Safari on iPhone");
    await expect(list).toContainText("Edge on Windows");
    await expect(list).toContainText("127.0.x.x");
    await a11y("S28 signed-in devices");

    // Phone works before, not after.
    expect((await phone.page.request.get("/api/me")).status()).toBe(200);
    await list.getByRole("listitem").filter({ hasText: "Safari on iPhone" }).getByRole("button", { name: /^Sign out Safari on iPhone/ }).click();
    await expect(page.getByText("Signed out Safari on iPhone").first()).toBeVisible();
    await expect(list.getByRole("listitem")).toHaveCount(2);
    expect((await phone.page.request.get("/api/me")).status()).toBe(401);
    await phone.page.goto("/");
    await expect(phone.page).toHaveURL(/\/login/);

    // The PC and this device are untouched.
    expect((await pc.page.request.get("/api/me")).status()).toBe(200);
    expect((await page.request.get("/api/me")).status()).toBe(200);
    await phone.ctx.close();
    await pc.ctx.close();
  });

  test("F14-H7 sign out other devices keeps this one", async ({ page, browser }) => {
    const u = await tempUser("sess");
    await signIn(page, u.email);
    const a = await otherDevice(browser, u.email, PHONE_UA);
    const b = await otherDevice(browser, u.email, WINDOWS_UA);
    await openSecurity(page);
    await page.getByRole("button", { name: "Sign out other devices" }).click();
    await expect(page.getByText("Signed out 2 other devices").first()).toBeVisible();
    const list = page.getByRole("list", { name: "Signed-in devices" });
    await expect(list.getByRole("listitem")).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Sign out other devices" })).toBeHidden();
    expect((await a.page.request.get("/api/me")).status()).toBe(401);
    expect((await b.page.request.get("/api/me")).status()).toBe(401);
    expect((await page.request.get("/api/me")).status()).toBe(200);
    await a.ctx.close();
    await b.ctx.close();
  });

  test("F14-N3 can't end someone else's session or your own from the list; sign out ends only this device", async ({ page, browser }) => {
    const me = await tempUser("sess");
    const other = await tempUser("sess");
    await signIn(page, me.email);
    const theirs = await otherDevice(browser, other.email, PHONE_UA);
    const [theirSession] = await sql`select id from auth.sessions where user_id = ${(await sql`select id from auth.users where email = ${other.email}`)[0].id}`;
    // Someone else's session: not found, and it keeps working.
    expect((await page.request.delete(`/api/account/sessions/${theirSession.id}`)).status()).toBe(404);
    expect((await theirs.page.request.get("/api/me")).status()).toBe(200);
    // Your own current session: refused (that's what Sign out is for).
    const mine = (await (await page.request.get("/api/account/sessions")).json()) as { id: string; current: boolean }[];
    expect(mine).toHaveLength(1);
    expect(mine[0].current).toBe(true);
    expect((await page.request.delete(`/api/account/sessions/${mine[0].id}`)).status()).toBe(400);
    expect((await page.request.delete(`/api/account/sessions/not-a-uuid`)).status()).toBe(404);
    // Normal sign-out ends this session only.
    const second = await otherDevice(browser, me.email, WINDOWS_UA);
    expect((await page.request.post("/api/auth/signout")).ok()).toBeTruthy();
    const [{ n }] = await sql`select count(*)::int as n from auth.sessions where user_id = ${me.id}`;
    expect(n).toBe(1);
    expect((await second.page.request.get("/api/me")).status()).toBe(200);
    await theirs.ctx.close();
    await second.ctx.close();
  });
});
