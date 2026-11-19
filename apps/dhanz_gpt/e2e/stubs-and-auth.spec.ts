import { test, expect, signIn } from "./fixtures";

test("STUB-1 later-release screens load cleanly", async ({ page, a11y }) => {
  await signIn(page);
  for (const path of ["/research", "/work", "/sites"]) {
    await page.goto(path);
    await expect(page.getByText(/is on the way/)).toBeVisible();
    await a11y(`stub ${path}`);
  }
  // Built since: the old app-detail links go to the Apps page.
  await page.goto("/apps/google-drive");
  await expect(page).toHaveURL(/\/apps$/);
});

test("X-2 a non-member email is refused", async ({ page, a11y }) => {
  await page.goto("/login");
  await a11y("S02 login");
  await page.getByLabel("Work email").fill("someone@gmail.com");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("isn't part of this workspace")).toBeVisible();
});

test("X-3 sign-in never redirects off-site", async ({ context }) => {
  for (const next of ["//evil.example", "https://evil.example", "/\\evil.example", "/\t/evil.example", "/%2F%2Fevil.example", "javascript:alert(1)"]) {
    await context.clearCookies();
    // A fresh page each time, so one sign-in's redirect can't still be loading when the next starts.
    const page = await context.newPage();
    await page.goto(`/login?next=${encodeURIComponent(next)}`);
    await page.getByLabel("Work email").fill("dante@rodrech.com");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));
    expect(new URL(page.url()).host, `next=${next}`).toBe("localhost:3100");
    // A same-site path that doesn't exist, like /%2F%2Fevil.example, lands on our own 404: still on-site.
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.close();
  }
});

test("X-4 signed-out visitors are sent to sign in", async ({ page }) => {
  for (const path of ["/", "/library", "/c/00000000-0000-4000-8000-000000000000", "/project/x"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
});

test("X-5 HTML and scripts in a message render as text", async ({ page }) => {
  await signIn(page);
  let dialogs = 0;
  page.on("dialog", async (d) => {
    dialogs++;
    await d.dismiss();
  });
  await page.goto("/");
  const payload = `<img src=x onerror="alert(1)"> <script>alert(2)</script> [link](javascript:alert(3))`;
  await page.getByLabel("Message Dhanz GPT").filter({ visible: true }).fill(payload);
  await page.getByLabel("Message Dhanz GPT").filter({ visible: true }).press("Enter");
  await expect(page).toHaveURL(/\/c\//);
  await expect(page.getByText(payload)).toBeVisible();
  await page.waitForTimeout(1500);
  expect(dialogs).toBe(0);
  expect(await page.locator("article img[src='x']").count()).toBe(0);
});

test("A11Y-1 the loading state of the chat list passes axe", async ({ page, a11y }) => {
  await signIn(page);
  await page.route("**/api/conversations", async (r) => {
    await new Promise((res) => setTimeout(res, 3000));
    await r.continue();
  });
  await page.goto("/");
  await expect(page.getByRole("status", { name: "Loading chats" }).or(page.locator('[aria-label="Loading chats"]'))).toBeVisible();
  await a11y("sidebar loading");
});
