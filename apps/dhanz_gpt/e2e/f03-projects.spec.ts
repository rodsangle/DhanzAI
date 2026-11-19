import fs from "node:fs";
import path from "node:path";
import { test, expect, signIn, composer, assistantArticles, waitDone, send, noHorizontalOverflow } from "./fixtures";

async function createProject(page: import("@playwright/test").Page, name: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Project name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/project\//);
  return page.url().split("/project/")[1];
}

const firstLine = async (page: import("@playwright/test").Page) =>
  (await assistantArticles(page).last().innerText()).replace("Assistant said:", "").trim().split("\n").find((l) => l.trim())!;

test.describe("F03 Projects", () => {
  test("F03-E4 double-clicking Create makes one project", async ({ page }) => {
    await signIn(page);
    await page.goto("/");
    await page.getByRole("button", { name: "New project" }).click();
    await page.getByLabel("Project name").fill("Double click test");
    await page.getByRole("button", { name: "Create project" }).dblclick();
    await expect(page).toHaveURL(/\/project\//);
    const all = await (await page.request.get("/api/projects")).json();
    expect(all.filter((p: { name: string }) => p.name === "Double click test")).toHaveLength(1);
  });

  test.beforeEach(async ({ page }) => signIn(page));

  test("F03-H1 create a project with instructions and chat in it", async ({ page, a11y }) => {
    await createProject(page, "SS27 campaign");
    await a11y("S09 empty project");
    await page.getByRole("button", { name: /^Instructions/ }).click();
    await page.getByLabel("Instructions").fill("Always answer in lowercase. Audience: skaters.");
    await a11y("S10 project settings");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Project saved", { exact: true })).toBeVisible();
    await send(page, "Write A Plan For The Lookbook");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    const line = await firstLine(page);
    expect(line).toBe(line.toLowerCase());
    await expect(page.getByRole("link", { name: "in SS27 campaign" })).toBeVisible();
  });

  test("F03-H2 move a chat into a project", async ({ page }) => {
    await page.goto("/");
    const row = page.getByRole("navigation", { name: "Chats" }).getByRole("listitem").filter({ hasText: "Influencer outreach email" });
    await row.hover();
    await row.getByRole("button", { name: /Options for/ }).click();
    await page.getByRole("menuitem", { name: "Move to project" }).hover();
    await page.getByRole("menuitem", { name: "Hang tags & packaging" }).click();
    await expect(page.getByText("Moved to Hang tags & packaging", { exact: true })).toBeVisible();
    await page.getByRole("link", { name: "Hang tags & packaging" }).click();
    // The project page lists it (the sidebar may still show it until its list refreshes).
    await expect(page.locator("#main").getByRole("link", { name: /Influencer outreach email/ })).toBeVisible();
  });

  test("F03-H3 project files reach the project's chats", async ({ page }) => {
    await createProject(page, "Files project");
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add files", exact: true }).click();
    await (await chooser).setFiles([{ name: "brand-guide.md", mimeType: "text/markdown", buffer: Buffer.from("# Guide\nNo emojis.") }]);
    await expect(page.getByRole("link", { name: "brand-guide.md" })).toBeVisible();
    await send(page, "Write captions");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("brand-guide.md");
  });

  test("F03-H4 a long PDF in a project is read by the parts that match the question", async ({ page }) => {
    test.setTimeout(90_000);
    await createProject(page, "Supplier docs");
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add files", exact: true }).click();
    await (await chooser).setFiles(path.join(__dirname, "files", "supplier-manual.pdf"));
    await expect(page.getByRole("link", { name: "supplier-manual.pdf" })).toBeVisible({ timeout: 30_000 });
    await send(page, "Which embroidery thread do we use for the logo?");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("Madeira Polyneon 1147 in bone");
  });

  test("F03-H5 a Word document in a project reaches its chats", async ({ page }) => {
    await createProject(page, "Holiday");
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add files", exact: true }).click();
    await (await chooser).setFiles(path.join(__dirname, "files", "holiday-brief.docx"));
    await expect(page.getByRole("link", { name: "holiday-brief.docx" })).toBeVisible();
    await send(page, "Draft the launch email");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    await expect(assistantArticles(page).last()).toContainText("holiday-brief.docx");
  });

  test("F03-E1 a 60-character name truncates cleanly", async ({ page }) => {
    const name = "Fall Winter 2026 headwear drop with collab partners and more";
    expect(name.length).toBe(60);
    await createProject(page, name);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(name);
    expect(await noHorizontalOverflow(page)).toBeTruthy();
    await page.getByRole("button", { name: /^Instructions/ }).click();
    await expect(page.getByLabel("Name")).toHaveValue(name);
  });

  test("F03-E2 names over 120 characters are refused", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "New project" }).click();
    await page.getByLabel("Project name").fill("x".repeat(130));
    await expect(page.getByLabel("Project name")).toHaveValue("x".repeat(120));
    const res = await page.request.post("/api/projects", { data: { name: "y".repeat(121) } });
    expect(res.status()).toBe(400);
  });

  test("F03-E3 empty name can't be created", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "New project" }).click();
    await expect(page.getByRole("button", { name: "Create project" })).toBeDisabled();
    await page.getByLabel("Project name").fill("   ");
    await expect(page.getByRole("button", { name: "Create project" })).toBeDisabled();
  });

  test("F03-N1 a viewer sees View only and no composer", async ({ page, browser }) => {
    const id = await createProject(page, "Viewer test");
    const members = await (await page.request.get("/api/members")).json();
    const maya = members.find((m: { email: string }) => m.email === "maya@rodrech.com");
    expect((await page.request.post(`/api/projects/${id}/members`, { data: { user_id: maya.id, role: "viewer" } })).ok()).toBeTruthy();
    const ctx = await browser.newContext();
    const p2 = await ctx.newPage();
    await signIn(p2, "maya@rodrech.com");
    await p2.goto(`/project/${id}`);
    await expect(p2.getByText("View only")).toBeVisible();
    await expect(composer(p2)).toHaveCount(0);
    await ctx.close();
  });

  test("F03-N2 deleting a project deletes its chats", async ({ page }) => {
    await createProject(page, "Short-lived");
    await send(page, "A chat that will go");
    await expect(page).toHaveURL(/\/c\//, { timeout: 15_000 });
    await waitDone(page);
    const chatId = page.url().split("/c/")[1];
    await page.getByRole("link", { name: "in Short-lived" }).click();
    await page.getByRole("button", { name: "Project options" }).click();
    await page.getByRole("menuitem", { name: "Delete project…" }).click();
    await page.getByRole("button", { name: "Delete project", exact: true }).click();
    await expect(page.getByText("This also deletes 1 chat")).toBeVisible();
    await page.getByRole("button", { name: "Delete project and chats" }).click();
    await expect(page).toHaveURL("/");
    expect((await page.request.get(`/api/conversations/${chatId}`)).status()).toBe(404);
  });

  test("F03-N3 a teammate can't open an unshared project", async ({ page, browser }) => {
    const projects = await (await page.request.get("/api/projects")).json();
    const tags = projects.find((p: { name: string }) => p.name === "Hang tags & packaging");
    const ctx = await browser.newContext();
    const p2 = await ctx.newPage();
    await signIn(p2, "maya@rodrech.com");
    await p2.goto(`/project/${tags.id}`);
    await expect(p2.getByText("Project not found")).toBeVisible();
    await ctx.close();
  });
});
