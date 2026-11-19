import { test, expect, signIn, ready } from "./fixtures";

const search = (page: import("@playwright/test").Page) => page.getByLabel("Search chats, projects and files");

test.describe("F04 Find an old chat", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto("/");
    await ready(page);
  });

  test("F04-H1 ⌘K, type, Enter opens the chat", async ({ page, a11y }) => {
    await page.keyboard.press("Control+k");
    await search(page).fill("round 3");
    await expect(page.getByRole("option", { name: /Hang tag copy, round 3/ }).first()).toBeVisible();
    await a11y("S08 search");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/c\//);
    await expect(page.getByRole("link", { name: "Hang tag copy, round 3" })).toHaveAttribute("aria-current", "page");
  });

  test("F04-E1 % and _ are literal, not wildcards", async ({ page }) => {
    for (const q of ["%", "_", "%_%"]) {
      const res: { title: string; snippet?: string }[] = await (await page.request.get(`/api/search?q=${encodeURIComponent(q)}`)).json();
      for (const r of res) expect(`${r.title} ${r.snippet ?? ""}`, `result for ${q}`).toContain(q === "%_%" ? "%_" : q);
    }
  });

  test("F04-E2 no results", async ({ page }) => {
    await page.keyboard.press("Control+k");
    await search(page).fill("zzqxv");
    await expect(page.getByText("Nothing matches “zzqxv”.")).toBeVisible();
  });

  test("F04-E3 archive, undo, archive, restore", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Chats" });
    const row = nav.getByRole("listitem").filter({ hasText: "Shopify product descriptions" });
    await row.hover();
    await row.getByRole("button", { name: /Options for/ }).click();
    await page.getByRole("menuitem", { name: "Archive" }).click();
    await expect(nav.getByRole("link", { name: "Shopify product descriptions" })).toHaveCount(0);
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(nav.getByRole("link", { name: "Shopify product descriptions" })).toBeVisible();
    await row.hover();
    await row.getByRole("button", { name: /Options for/ }).click();
    await page.getByRole("menuitem", { name: "Archive" }).click();
    await expect(nav.getByRole("link", { name: "Shopify product descriptions" })).toHaveCount(0);
    await page.getByRole("button", { name: /Dante/ }).click();
    await page.getByRole("menuitem", { name: "Settings" }).click();
    await page.getByRole("tab", { name: "Data controls" }).click();
    await page.getByRole("button", { name: "Restore" }).first().click();
    await page.keyboard.press("Escape");
    await expect(nav.getByRole("link", { name: "Shopify product descriptions" })).toBeVisible();
  });

  test("F04-N1 a teammate's search can't see private chats", async ({ browser }) => {
    const ctx = await browser.newContext();
    const p2 = await ctx.newPage();
    await signIn(p2, "maya@rodrech.com");
    await p2.goto("/");
    await ready(p2);
    await p2.keyboard.press("Control+k");
    await search(p2).fill("outreach");
    await expect(p2.getByText("Nothing matches “outreach”.")).toBeVisible();
    await ctx.close();
  });
});
