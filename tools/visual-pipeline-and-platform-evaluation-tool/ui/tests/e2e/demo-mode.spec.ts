import { expect, test } from "@playwright/test";

test.describe("Demo mode", () => {
  test("opens the demo mode landing screen", async ({ page }) => {
    await page.goto("/demo");

    await expect(
      page.getByRole("heading", {
        name: /Intel.*Visual Pipeline and Platform Evaluation Tool.*ViPPET/i,
      }),
    ).toBeVisible();

    await expect(page.getByRole("button", { name: /^Exit$/i })).toBeVisible();
  });

  test("Exit button returns the user to the dashboard", async ({ page }) => {
    await page.goto("/demo");

    await page.getByRole("button", { name: /^Exit$/i }).click();

    await expect(page).toHaveURL(/\/(?:$|#)/);
  });
});
