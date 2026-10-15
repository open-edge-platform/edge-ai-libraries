import { expect, test } from "@playwright/test";

/**
 * Cross-browser smoke suite.
 *
 * Runs on every project defined in `playwright.config.ts` (chromium, firefox,
 * webkit, chrome, msedge). Keep tests here shallow — the goal is to verify the
 * UI boots and renders on each engine/version, not to cover business logic.
 */
test.describe("Cross-browser smoke", () => {
  test("dashboard renders on every supported browser", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /^Pipelines$/i }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /^Resource utilization$/i }),
    ).toBeVisible();
  });

  test("demo mode renders on every supported browser", async ({ page }) => {
    await page.goto("/demo");

    await expect(
      page.getByRole("heading", {
        name: /Intel.*Visual Pipeline and Platform Evaluation Tool.*ViPPET/i,
      }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /^Exit$/i })).toBeVisible();
  });
});
