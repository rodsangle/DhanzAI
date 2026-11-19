import { test, expect, signIn, assistantArticles, waitDone, send } from "./fixtures";

test("F06-H1 image mode makes an image that shows up everywhere", async ({ page, a11y }) => {
  await signIn(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Add files and tools" }).click();
  await page.getByRole("menuitem", { name: "Create an image" }).click();
  await expect(page.getByRole("button", { name: "Image mode on. Turn off" })).toBeVisible();
  const prompt = "a black snapback on wet concrete at night";
  await send(page, prompt);
  await waitDone(page);
  const img = assistantArticles(page).last().getByRole("img", { name: prompt });
  await expect(img).toBeVisible();
  expect(await img.evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth > 0)).toBeTruthy();
  await page.goto("/images");
  await expect(page.getByRole("img", { name: prompt })).toBeVisible();
  await a11y("S13 images");
  await page.goto("/library");
  await expect(page.getByText("Generated").first()).toBeVisible();
  await a11y("S11 library");
});
