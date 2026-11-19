import { test, expect, signIn, waitDone, send, newChat } from "./fixtures";

async function createLink(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await page.getByRole("button", { name: "Create link" }).click();
  const url = await page.getByLabel("Link", { exact: true }).inputValue();
  expect(url).toMatch(/\/s\/[0-9a-f]{32}$/);
  return url;
}

test.describe("F05 Share a conversation", () => {
  test.beforeEach(async ({ page }) => signIn(page));

  test("F05-H1 create a link and open it", async ({ page, context, a11y }) => {
    await newChat(page, "Write captions for the drop");
    const url = await createLink(page);
    await a11y("share dialog");
    const view = await context.newPage();
    await view.goto(url);
    await expect(view.getByText("Shared by Dante")).toBeVisible();
    await expect(view.getByRole("heading", { level: 1 })).toContainText("Write captions for the drop");
    await a11y("S30 shared page");
  });

  test("F05-E1 update the link after new messages", async ({ page, context }) => {
    await newChat(page, "First question");
    const url = await createLink(page);
    await page.keyboard.press("Escape");
    await send(page, "Second question about hang tags");
    await waitDone(page);
    await page.getByRole("button", { name: "Share", exact: true }).click();
    await expect(page.getByText("This chat has new messages since you shared it.")).toBeVisible();
    await page.getByRole("button", { name: "Update link" }).click();
    await expect(page.getByText("This chat has new messages since you shared it.")).toHaveCount(0);
    const view = await context.newPage();
    await view.goto(url);
    await expect(view.getByText("Second question about hang tags")).toBeVisible();
  });

  test("F05-E2 signed-out viewer signs in and lands on the link", async ({ page, browser }) => {
    await newChat(page, "Shared to a signed-out viewer");
    const url = await createLink(page);
    const ctx = await browser.newContext();
    const anon = await ctx.newPage();
    await anon.goto(url);
    await expect(anon).toHaveURL(/\/login\?next=/);
    await anon.getByLabel("Work email").fill("maya@rodrech.com");
    await anon.getByRole("button", { name: "Sign in" }).click();
    await expect(anon.getByText("Shared by Dante")).toBeVisible();
    await ctx.close();
  });

  test("F05-E3 a deleted link stops working", async ({ page, context }) => {
    await newChat(page, "Link to delete");
    const url = await createLink(page);
    await page.getByRole("button", { name: "Delete link" }).click();
    await expect(page.getByRole("button", { name: "Create link" })).toBeVisible();
    const view = await context.newPage();
    await view.goto(url);
    await expect(view.getByText("This link doesn't work")).toBeVisible();
  });

  test("F05-N1 temporary chats can't be shared", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Temporary chat" }).click();
    await send(page, "Private idea");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(page.getByRole("button", { name: "Share", exact: true })).toHaveCount(0);
    const id = page.url().split("/c/")[1];
    expect((await page.request.post(`/api/conversations/${id}/share`)).status()).toBe(400);
  });
});
