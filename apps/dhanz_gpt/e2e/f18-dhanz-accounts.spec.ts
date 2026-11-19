import { test, expect } from "./fixtures";
import { sql } from "./db";
import type { Page } from "@playwright/test";

// F18 Sign in with a DHANZ AI account (AUTH_MODE=dhanz), against the stand-in DHANZ API on :4010.
// The app under test here is the same build on :3101.
const APP = "http://localhost:3101";
const DZ = "http://localhost:4010/dhanz";
const ANA = { email: "ana@dhanzai.test", password: "correct horse 1", id: "6c0a4d8e-1111-4a5b-9c1d-0000000000a1" };
const TOM = { email: "tom@dhanzai.test", password: "correct horse 2", id: "6c0a4d8e-2222-4a5b-9c1d-0000000000b2" };
const EVE = { email: "eve@dhanzai.test", password: "correct horse 3", id: "6c0a4d8e-3333-4a5b-9c1d-0000000000c3" };

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  await sql`update platform_settings set value = 'personal' where key = 'signup_mode'`;
  await sql`delete from auth.users where email like '%@dhanzai.test'`;
  await sql`delete from workspaces w where name like '%''s workspace' and not exists (select 1 from memberships m where m.workspace_id = w.id)`;
});
test.afterAll(async () => {
  await sql`delete from auth.users where email like '%@dhanzai.test'`;
  await sql`update platform_settings set value = 'domain' where key = 'signup_mode'`;
});

async function signIn(page: Page, who: { email: string; password: string }) {
  await page.goto(`${APP}/login`);
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}
const dzLog = async (page: Page) => ((await (await page.request.get(`${DZ}/__log`)).json()).calls as { path: string; outcome: string }[]);
/** Make the next request re-check the session with DHANZ (normally every 5 minutes). */
const forceRecheck = (userId: string) => sql`update dhanz_sessions set checked_at = now() - interval '1 hour' where user_id = ${userId}`;

test.describe("F18 DHANZ AI accounts", () => {
  test("F18-H1 sign in with email and password; own workspace; the page explains where accounts come from", async ({ page, a11y }) => {
    await page.goto(`${APP}/login`);
    await expect(page.getByRole("heading", { name: "Sign in to Dhanz GPT" })).toBeVisible();
    await expect(page.getByText("Use your DHANZ AI account.")).toBeVisible();
    await expect(page.getByLabel("Work email")).toBeHidden(); // no demo sign-in in this mode
    await a11y("S02 DHANZ sign-in");
    await signIn(page, ANA);
    await expect(page).toHaveURL(`${APP}/`);
    await expect(page.getByRole("button", { name: /^Ana Dhanz/ }).filter({ visible: true })).toBeVisible();

    const [ws] = await sql`select w.name, m.role from memberships m join workspaces w on w.id = m.workspace_id where m.user_id = ${ANA.id}`;
    expect(ws.name).toBe("Ana Dhanz's workspace");
    expect(ws.role).toBe("owner");
    const [s] = await sql`select count(*)::int as n from dhanz_sessions where user_id = ${ANA.id}`;
    expect(s.n).toBe(1);
    // Tokens are stored sealed, never as text.
    const [raw] = await sql`select encode(refresh_token, 'escape') as t from dhanz_sessions where user_id = ${ANA.id}`;
    expect(raw.t).not.toContain("dz-rt-");
    // Demo sign-in is switched off.
    expect((await page.request.post(`${APP}/api/auth/dev-login`, { data: { email: "dante@rodrech.com" } })).status()).toBe(404);
  });

  test("F18-H2 two-step: authenticator code (a wrong one first), and the emailed-code variant", async ({ page }) => {
    await signIn(page, TOM);
    await expect(page.getByText("Enter the code from your authenticator app, or a recovery code.")).toBeVisible();
    await page.getByLabel("Code").fill("000000");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("That code didn't work. Check it and try again, or start over.")).toBeVisible();
    await page.getByLabel("Code").fill("123456");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(`${APP}/`);
    await expect(page.getByRole("button", { name: /^Tom Two-Step/ }).filter({ visible: true })).toBeVisible();

    const other = await page.context().browser()!.newContext();
    const p2 = await other.newPage();
    await signIn(p2, EVE);
    await expect(p2.getByText("Enter the code we emailed to e***@dhanzai.test.")).toBeVisible();
    await p2.getByRole("button", { name: "Start over" }).click();
    await expect(p2.getByLabel("Password")).toBeVisible();
    await other.close();
  });

  test("F18-N1 wrong password, unverified email, and nothing leaks between accounts", async ({ page, browser }) => {
    await signIn(page, { email: ANA.email, password: "nope" });
    await expect(page.getByText("That email and password don't match a DHANZ AI account.")).toBeVisible();
    await signIn(page, { email: "new@dhanzai.test", password: "correct horse 4" });
    await expect(page.getByText("Verify your email in DHANZ AI first, then sign in here.")).toBeVisible();
    const [{ n }] = await sql`select count(*)::int as n from auth.users where email = 'new@dhanzai.test'`;
    expect(n).toBe(0);

    // Two accounts: separate workspaces, so neither appears in the other's share list.
    await signIn(page, ANA);
    await expect(page).toHaveURL(`${APP}/`);
    const ctx = await browser.newContext();
    const tom = await ctx.newPage();
    await signIn(tom, TOM);
    await tom.getByLabel("Code").fill("123456");
    await tom.getByRole("button", { name: "Continue" }).click();
    await expect(tom).toHaveURL(`${APP}/`);
    const members = (await (await page.request.get(`${APP}/api/members`)).json()) as { email: string }[];
    expect(members.map((m) => m.email)).toEqual([ANA.email]);
    await ctx.close();
  });

  test("F18-E1 signing out everywhere in DHANZ AI ends the Dhanz GPT session at the next check", async ({ page }) => {
    await signIn(page, ANA);
    await expect(page).toHaveURL(`${APP}/`);
    expect((await page.request.get(`${APP}/api/me`)).status()).toBe(200);
    await page.request.post(`${DZ}/__signout?email=${ANA.email}`);
    // Still fine until the next check (every 5 minutes)...
    expect((await page.request.get(`${APP}/api/me`)).status()).toBe(200);
    const sid = (await page.context().cookies(APP)).find((c) => c.name === "dg_sid")!.value;
    await forceRecheck(ANA.id);
    expect((await page.request.get(`${APP}/api/me`)).status()).toBe(401);
    // This browser's session is gone (the account's other sessions go the same way when next used).
    const [{ n }] = await sql`select count(*)::int as n from auth.sessions where id = ${sid}`;
    expect(n).toBe(0);
    await page.goto(`${APP}/`);
    await expect(page).toHaveURL(/\/login/);
  });

  test("F18-E2 expired DHANZ tokens refresh once, even with many requests at the same moment", async ({ page }) => {
    await signIn(page, ANA);
    await expect(page).toHaveURL(`${APP}/`);
    await page.request.post(`${DZ}/__expire`);
    await forceRecheck(ANA.id);
    const before = (await dzLog(page)).length;
    const results = await Promise.all(Array.from({ length: 6 }, () => page.request.get(`${APP}/api/me`)));
    expect(results.map((r) => r.status())).toEqual([200, 200, 200, 200, 200, 200]);
    const after = (await dzLog(page)).slice(before);
    expect(after.filter((c) => c.outcome === "refreshed")).toHaveLength(1);
    expect(after.filter((c) => c.outcome === "refresh-refused")).toHaveLength(0);
    // And the new tokens work at the next check.
    await forceRecheck(ANA.id);
    expect((await page.request.get(`${APP}/api/me`)).status()).toBe(200);
  });

  test("F18-E3 signing out here ends the DHANZ session too; deleting the account removes its workspace", async ({ page }) => {
    await signIn(page, ANA);
    await expect(page).toHaveURL(`${APP}/`);
    const before = (await dzLog(page)).length;
    expect((await page.request.post(`${APP}/api/auth/signout`)).ok()).toBeTruthy();
    expect((await dzLog(page)).slice(before).some((c) => c.path === "/api/v1/auth/logout")).toBeTruthy();
    expect((await page.request.get(`${APP}/api/me`)).status()).toBe(401);

    await signIn(page, ANA);
    await expect(page).toHaveURL(`${APP}/`);
    const [ws] = await sql`select workspace_id from memberships where user_id = ${ANA.id}`;
    const del = await page.request.delete(`${APP}/api/account`, { data: { confirm: "DELETE" } });
    expect(del.ok(), await del.text()).toBeTruthy();
    const [{ users }] = await sql`select count(*)::int as users from auth.users where id = ${ANA.id}`;
    const [{ spaces }] = await sql`select count(*)::int as spaces from workspaces where id = ${ws.workspace_id}`;
    expect(users).toBe(0);
    expect(spaces).toBe(0);
  });
});
