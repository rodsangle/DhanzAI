import { test as base, expect, type Page, type BrowserContext } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Every test fails on:
 *  - a browser console error (expected 4xx "Failed to load resource" lines are allowed: they're API refusals the UI handles),
 *  - any 5xx response,
 *  - an axe WCAG 2.1 A/AA violation on screens checked with `a11y()`.
 */
const ALLOWED = [/Failed to load resource: the server responded with a status of 4\d\d/];

type Fixtures = { problems: string[]; allowConsole: (re: RegExp) => void; a11y: (label: string) => Promise<void> };

export const test = base.extend<Fixtures>({
  problems: [
    async ({ context }, use) => {
      const problems: string[] = [];
      const allowed = [...ALLOWED];
      (context as BrowserContext & { __allowed?: RegExp[] }).__allowed = allowed;
      const watch = (p: Page) => {
        p.on("console", (m) => {
          if (m.type() === "error" && !allowed.some((re) => re.test(m.text()))) problems.push(`console: ${m.text()}`);
        });
        p.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
      };
      context.pages().forEach(watch);
      context.on("page", watch);
      context.on("response", (r) => {
        if (r.status() >= 500) problems.push(`${r.status()} ${r.request().method()} ${r.url()}`);
      });
      await use(problems);
      expect(problems, "console errors / 5xx responses / a11y violations").toEqual([]);
    },
    { auto: true },
  ],
  allowConsole: async ({ context }, use) => {
    await use((re) => (context as BrowserContext & { __allowed?: RegExp[] }).__allowed!.push(re));
  },
  a11y: async ({ page, problems }, use) => {
    await use(async (label) => {
      const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      for (const v of res.violations) problems.push(`axe ${label}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(" ")}`);
    });
  },
});
export { expect };

/* ------------------------------------------------------------------ helpers */

export async function signIn(page: Page, email = "dante@rodrech.com") {
  const res = await page.request.post("/api/auth/dev-login", { data: { email } });
  expect(res.ok(), `sign in as ${email}`).toBeTruthy();
}

// Next 16 keeps the previous route mounted but hidden, so always scope to what's visible.
export const composer = (page: Page) => page.getByLabel("Message Dhanz GPT").filter({ visible: true });
export const articles = (page: Page) => page.locator("article").filter({ visible: true });
export const assistantArticles = (page: Page) => articles(page).filter({ has: page.getByRole("heading", { name: "Assistant said:" }) });
export const userArticles = (page: Page) => articles(page).filter({ has: page.getByRole("heading", { name: "You said:" }) });

export async function waitDone(page: Page, timeout = 30_000) {
  await expect(page.getByRole("button", { name: "Stop answering" })).toHaveCount(0, { timeout });
  await page.waitForFunction(
    () => [...document.querySelectorAll('article[aria-busy="true"]')].filter((a) => (a as HTMLElement).offsetParent).length === 0,
    null,
    { timeout },
  );
  await expect(assistantArticles(page).last()).toBeVisible();
}

export async function send(page: Page, text: string) {
  await composer(page).fill(text);
  await composer(page).press("Enter");
}

export async function newChat(page: Page, text: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("What are we making today");
  await send(page, text);
  await expect(page).toHaveURL(/\/c\/[0-9a-f-]{36}$/, { timeout: 15_000 });
  await waitDone(page);
  return page.url().split("/c/")[1];
}

/** The app is interactive once the sidebar's chat list has rendered. */
export async function ready(page: Page) {
  await expect(page.getByRole("navigation", { name: "Chats" }).getByRole("link").first()).toBeVisible();
}

export async function noHorizontalOverflow(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}
