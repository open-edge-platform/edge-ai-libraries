import type { Page } from "@playwright/test";

export const mockDemoApi = async (page: Page) => {
  for (const endpoint of ["devices", "models", "pipelines", "videos"]) {
    await page.route(`**/api/v1/${endpoint}`, async (route) => {
      const body =
        endpoint === "pipelines"
          ? JSON.stringify([
              {
                id: "demo-pipeline",
                name: "Demo pipeline",
                description: "Pipeline used by the demo smoke tests.",
                source: "PREDEFINED",
                type: "vision",
                variants: [],
                created_at: "2026-01-01T00:00:00Z",
                modified_at: "2026-01-01T00:00:00Z",
              },
            ])
          : "[]";

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    });
  }
};
