import { test, expect, signIn, composer, articles, assistantArticles, userArticles, waitDone, send, newChat, noHorizontalOverflow, ready } from "./fixtures";
import { sql, tempUser, fillDailyUsage, countUserMessages } from "./db";

test.describe("F01 Ask and iterate", () => {
  test.beforeEach(async ({ page }) => signIn(page));

  test("F01-H1 send, stream, URL and sidebar title", async ({ page, a11y }) => {
    await page.goto("/");
    await a11y("S03 home");
    await send(page, "Write three captions for the FW26 snapback drop");
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    await expect(page).toHaveURL(/\/c\/[0-9a-f-]{36}$/);
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("Three options");
    await expect(page.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /Write three captions for the FW26/ })).toBeVisible();
    await a11y("S04 conversation");
  });

  test("F01-H6 math renders, prices stay text", async ({ page, a11y }) => {
    await newChat(page, "What's the formula for gross margin?");
    const answer = assistantArticles(page).last();
    await expect(answer.locator("math")).toHaveCount(3);
    await expect(answer.locator(".katex-display")).toHaveCount(1);
    await expect(answer).toContainText("sells at $45 and costs $12");
    await expect(answer.locator(".katex-error")).toHaveCount(0);
    await a11y("S04 math answer");
  });

  test("F01-H7 current questions search the web and cite sources", async ({ page, a11y }) => {
    await newChat(page, "What are the latest headwear trends?");
    const answer = assistantArticles(page).last();
    const cite = answer.getByRole("link", { name: "Source 1: example.com" });
    await expect(cite).toHaveAttribute("href", "https://example.com/demo/what-are-the-latest-headwear-trends");
    await expect(cite).toHaveAttribute("target", "_blank");
    const sources = answer.getByRole("list", { name: "Sources" });
    await expect(sources.getByRole("link", { name: /^1 Sample result: What are the latest headwear trends/ })).toBeVisible();
    await expect(sources.getByRole("link", { name: /^2 Sample result: streetwear headwear report/ })).toBeVisible();
    await a11y("S04 answer with web sources");
  });

  test("F01-H8 web search turned on from the + menu, for one message", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Add files and tools" }).click();
    await page.getByRole("menuitem", { name: "Search the web" }).click();
    await expect(page.getByRole("button", { name: "Web search on. Turn off" })).toBeVisible();
    await expect(composer(page)).toHaveAttribute("placeholder", "What should I look up?");
    // Image mode and search mode don't stack.
    await page.getByRole("button", { name: "Add files and tools" }).click();
    await page.getByRole("menuitem", { name: "Create an image" }).click();
    await expect(page.getByRole("button", { name: "Web search on. Turn off" })).toHaveCount(0);
    await page.getByRole("button", { name: "Add files and tools" }).click();
    await page.getByRole("menuitem", { name: "Search the web" }).click();
    await send(page, "Snapback colourways for spring");
    await waitDone(page);
    await expect(assistantArticles(page).last().getByRole("link", { name: "Source 1: example.com" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Web search on. Turn off" })).toHaveCount(0);
    // The next message doesn't search unless asked.
    await send(page, "Make it shorter");
    await waitDone(page);
    await expect(assistantArticles(page).last().getByRole("list", { name: "Sources" })).toHaveCount(0);
  });

  test("X-9 a shared link keeps web citations and sources", async ({ page }) => {
    const id = await newChat(page, "Search for the latest cap drops this week");
    const res = await page.request.post(`/api/conversations/${id}/share`);
    const { slug } = await res.json();
    await page.goto(`/s/${slug}`);
    await expect(page.getByRole("link", { name: "Source 1: example.com" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Sources" }).getByRole("link")).toHaveCount(2);
  });

  test("F01-H2 regenerate makes a version and the choice persists", async ({ page }) => {
    await newChat(page, "Draft hang tag copy for the black snapback");
    await page.getByRole("button", { name: "Try again" }).last().click();
    await page.getByRole("menuitem", { name: "Try again" }).first().click();
    await expect(page.getByRole("group", { name: "Answer version 2 of 2" })).toBeVisible();
    await waitDone(page);
    await page.getByRole("group", { name: "Answer version 2 of 2" }).getByRole("button", { name: "Previous version" }).click();
    await expect(page.getByRole("group", { name: "Answer version 1 of 2" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("group", { name: "Answer version 1 of 2" })).toBeVisible();
  });

  test("F01-H3 editing a message creates a new version of the question", async ({ page }) => {
    await newChat(page, "Write three captions for the beanie");
    await userArticles(page).first().hover();
    await page.getByRole("button", { name: "Edit message" }).first().click();
    await page.getByLabel("Edit message").fill("Write three captions for the bone fitted cap");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByRole("group", { name: "Message version 2 of 2" })).toBeVisible();
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("fitted");
  });

  test("F01-H4 stop keeps a partial answer", async ({ page }) => {
    await newChat(page, "Hello");
    await send(page, "/slow plan the launch steps for friday");
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    await page.waitForTimeout(1200);
    await page.getByRole("button", { name: "Stop answering" }).click();
    await expect(assistantArticles(page).last().getByText("Stopped")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  });

  test("F01-H5 model choice applies and persists", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /^Model:/ }).click();
    await page.getByRole("menuitemcheckbox", { name: /^Deep/ }).click();
    await send(page, "Plan a launch checklist");
    await waitDone(page);
    await expect(assistantArticles(page).last().getByRole("toolbar")).toContainText("Deep");
    await page.reload();
    await expect(page.getByRole("button", { name: /^Model: Deep/ })).toBeVisible();
  });

  test("F01-E1 empty or whitespace input can't be sent", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
    await composer(page).fill("   \n  ");
    await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
    await composer(page).press("Enter");
    await expect(page).toHaveURL("/");
  });

  test("F01-E2 very long typed input sends and wraps", async ({ page }) => {
    await page.goto("/");
    const long = "streetwear ".repeat(550); // ~6,000 chars typed via fill (not a paste)
    await composer(page).fill(long);
    await composer(page).press("Enter");
    await expect(page).toHaveURL(/\/c\//);
    await waitDone(page);
    await expect(userArticles(page).first()).toContainText("streetwear streetwear");
    expect(await noHorizontalOverflow(page)).toBeTruthy();
  });

  test("F01-E3 emoji and accents survive titles, bubbles and search", async ({ page }) => {
    await newChat(page, "Écris 3 légendes 🧢 pour le café");
    await expect(userArticles(page).first()).toContainText("Écris 3 légendes 🧢 pour le café");
    await expect(page.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: /Écris 3 légendes 🧢/ })).toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByLabel("Search chats, projects and files").fill("légendes");
    await expect(page.getByRole("option", { name: /Écris 3 légendes/ }).first()).toBeVisible();
  });

  test("F01-E4 double Enter creates one message", async ({ page }) => {
    await page.goto("/");
    await composer(page).fill("Only once please");
    await composer(page).press("Enter");
    await composer(page).press("Enter");
    await expect(page).toHaveURL(/\/c\//);
    await waitDone(page);
    const id = page.url().split("/c/")[1];
    expect(await countUserMessages(id)).toBe(1);
  });

  test("F01-E5 two tabs on one chat", async ({ page, context }) => {
    const id = await newChat(page, "Tab test");
    const b = await context.newPage();
    await b.goto(`/c/${id}`);
    await expect(assistantArticles(b)).toHaveCount(1);
    await page.bringToFront();
    await send(page, "/slow write a launch plan");
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    // Sending from B while A's answer is running is refused with a clear reason.
    await b.bringToFront();
    await send(b, "Me too");
    await expect(b.getByText(/Wait for the current answer to finish/)).toBeVisible();
    // Switching back to B a bit later shows A's exchange (refetch on focus is throttled to 5 s).
    await page.getByRole("button", { name: "Stop answering" }).click();
    await waitDone(page);
    await b.waitForTimeout(5500);
    await b.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(assistantArticles(b)).toHaveCount(2, { timeout: 15_000 });
  });

  test("F01-E15 two sends to one chat at the same instant: one answer, one refusal", async ({ page }) => {
    const id = await newChat(page, "Race test");
    const before = await countUserMessages(id);
    for (let round = 0; round < 3; round++) {
      const post = (text: string) =>
        page.request.post("/api/chat", { data: { conversation_id: id, text, model: "claude-sonnet-5-5" } }).then(async (r) => {
          const status = r.status();
          await r.body().catch(() => null); // drain the stream
          return status;
        });
      const statuses = (await Promise.all([post(`/slow first ${round}`), post(`/slow second ${round}`)])).sort();
      expect(statuses, `round ${round}`).toEqual([200, 409]);
    }
    expect(await countUserMessages(id)).toBe(before + 3);
    // Every user message hangs off an assistant answer (no second version of a question was created).
    const [{ n }] = await sql`select count(*)::int as n from messages m join messages p on p.id = m.parent_id
      where m.conversation_id = ${id} and m.role = 'user' and p.role <> 'assistant'`;
    expect(n).toBe(0);
  });

  test("F01-E6 reload mid-answer resumes", async ({ page }) => {
    await newChat(page, "Hello");
    await send(page, "/slow make a plan for the lookbook shoot");
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    await page.waitForTimeout(1200);
    await page.reload();
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    await waitDone(page, 60_000);
    await expect(assistantArticles(page).last()).toContainText("dated checklist");
  });

  test("F01-E7 back button mid-answer", async ({ page }) => {
    const id = await newChat(page, "Hello");
    await send(page, "/slow make a plan for the restock");
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    await page.getByRole("navigation", { name: "Chats" }).getByRole("link", { name: "Lookbook shot list" }).click();
    await expect(page).not.toHaveURL(new RegExp(id));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(id));
    await waitDone(page, 60_000);
    await expect(assistantArticles(page).last()).toContainText("dated checklist");
  });

  test("F01-E8 offline send shows an error and keeps the text", async ({ page, context, allowConsole }) => {
    allowConsole(/ERR_INTERNET_DISCONNECTED/);
    await newChat(page, "Hello");
    await context.setOffline(true);
    await send(page, "This should not be lost");
    await expect(page.getByRole("alert").filter({ hasText: "Message not sent" })).toBeVisible();
    await expect(composer(page)).toHaveValue("This should not be lost");
    await context.setOffline(false);
    await composer(page).press("Enter");
    await waitDone(page);
    await expect(userArticles(page).last()).toContainText("This should not be lost");
  });

  test("F01-E9 expired session sends you to sign in", async ({ page, context }) => {
    await newChat(page, "Hello");
    const url = page.url();
    await context.clearCookies();
    await send(page, "Are you still there?");
    await expect(page).toHaveURL(/\/login\?next=/, { timeout: 15_000 });
    expect(decodeURIComponent(page.url())).toContain(new URL(url).pathname);
  });

  test("F01-E10 slow network shows Sending and creates one message", async ({ page }) => {
    await page.goto("/");
    await page.route("**/api/chat", async (r) => {
      await new Promise((res) => setTimeout(res, 1500));
      await r.continue();
    });
    await composer(page).fill("Slow network test");
    await composer(page).press("Enter");
    await expect(page.getByText("Sending")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toHaveCount(0);
    await expect(page).toHaveURL(/\/c\//, { timeout: 20_000 });
    await waitDone(page);
    expect(await countUserMessages(page.url().split("/c/")[1])).toBe(1);
  });

  test("F01-E12 keyboard only", async ({ page }) => {
    await page.goto("/");
    await ready(page);
    // First Tab lands on "Skip to content"; from there the composer is a few Tabs away.
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
    await page.keyboard.press("Enter");
    let reached = false;
    for (let i = 0; i < 6 && !reached; i++) {
      await page.keyboard.press("Tab");
      reached = await page.evaluate(() => document.activeElement?.tagName === "TEXTAREA");
    }
    expect(reached, "composer within 6 Tabs of the skip link").toBeTruthy();
    await page.keyboard.type("Write captions for the cap");
    await page.keyboard.press("Enter");
    await waitDone(page);
    await composer(page).focus();
    await page.keyboard.type("/slow plan the shoot");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Stop answering" })).toBeVisible();
    await page.waitForTimeout(800);
    await composer(page).focus();
    await page.keyboard.press("Escape");
    await expect(assistantArticles(page).last().getByText("Stopped")).toBeVisible();
    await composer(page).focus();
    await page.keyboard.press("ArrowUp");
    await expect(page.getByRole("textbox", { name: "Edit message" })).toBeFocused();
  });

  test("F01-E13 thread semantics for screen readers", async ({ page }) => {
    await newChat(page, "Write captions");
    await expect(userArticles(page)).toHaveCount(1);
    await expect(assistantArticles(page)).toHaveCount(1);
    const unnamed = await page.evaluate(() =>
      [...document.querySelectorAll("button")].filter((b) => (b as HTMLElement).offsetParent && !(b.getAttribute("aria-label") || b.textContent?.trim())).length,
    );
    expect(unnamed, "every visible button has a name").toBe(0);
  });

  test("F01-N1 model error then retry", async ({ page }) => {
    await newChat(page, "Hello");
    await send(page, "/fail write captions for the beanie");
    await expect(page.getByText("This answer didn't finish.")).toBeVisible();
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("group", { name: "Answer version 2 of 2" })).toBeVisible();
    await waitDone(page);
  });

  test("F01-N3 chat deleted in another tab", async ({ page, context }) => {
    const id = await newChat(page, "Soon deleted");
    const other = await context.newPage();
    const del = await other.request.delete(`/api/conversations/${id}`);
    expect(del.ok()).toBeTruthy();
    await send(page, "Anyone home?");
    await expect(page.getByText(/doesn't exist|not found/i).first()).toBeVisible();
  });

  test("F01-N4 teammate can't post into someone else's project chat", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "FW26 drop" }).click();
    const maya = page.getByRole("link", { name: /Drop day checklist/ });
    await expect(maya).toBeVisible();
    await maya.click();
    await expect(page.getByText("This chat belongs to a teammate")).toBeVisible();
    const id = page.url().split("/c/")[1];
    const res = await page.request.post("/api/chat", { data: { conversation_id: id, text: "sneaky" } });
    expect(res.status()).toBe(403);
  });
});

test.describe("F01 with a fresh person", () => {
  test("F01-N2 daily message limit", async ({ page }) => {
    const u = await tempUser("limit");
    await fillDailyUsage(u.id, "message", 500);
    await signIn(page, u.email);
    await page.goto("/");
    await expect(composer(page)).toBeDisabled();
    await expect(composer(page)).toHaveAttribute("placeholder", /today's message limit/);
    const res = await page.request.post("/api/chat", { data: { text: "hi" } });
    expect(res.status()).toBe(429);
  });

  test("F01-E14 time zone: a new chat is under Today in Auckland", async ({ browser }) => {
    const ctx = await browser.newContext({ timezoneId: "Pacific/Auckland" });
    const page = await ctx.newPage();
    await signIn(page);
    await newChat(page, "Auckland time check");
    const today = page.getByRole("navigation", { name: "Chats" }).locator("section", { has: page.getByRole("heading", { name: "Today" }) });
    await expect(today.getByRole("link", { name: /Auckland time check/ })).toBeVisible();
    await ctx.close();
  });
});

test.describe("F01 at 390px", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("F01-E11 mobile send and actions", async ({ page, a11y }) => {
    await signIn(page);
    await newChat(page, "Write three captions for the cap");
    expect(await noHorizontalOverflow(page)).toBeTruthy();
    await expect(page.getByRole("button", { name: "Copy" }).last()).toBeVisible();
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(page.getByRole("dialog", { name: "Menu" })).toBeVisible();
    await a11y("S07 mobile drawer");
  });
});
