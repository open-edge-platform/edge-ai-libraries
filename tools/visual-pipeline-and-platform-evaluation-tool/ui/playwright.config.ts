import { defineConfig, devices } from "@playwright/test";

/**
 * ViPPET UI end-to-end tests.
 *
 * Base URL is taken from `PLAYWRIGHT_BASE_URL` (env). Default is `http://localhost`
 * which matches the Nginx-served UI from `make run`. For a local Vite dev server
 * use `PLAYWRIGHT_BASE_URL=http://localhost:5173`.
 *
 * Project layout:
 * - `chromium` — default project, runs ALL tests (regular smoke + cross-browser).
 * - Other projects (`firefox`, `webkit`, `chrome`, `msedge`) run ONLY tests inside
 *   `tests/e2e/cross-browser/`, so the browser-compatibility suite is opt-in per project.
 *
 * The `chrome` and `msedge` projects use `channel` — they run against the version
 * of Google Chrome / Microsoft Edge installed on the machine, which is how we
 * exercise different real-world browser versions. `chromium`, `firefox` and
 * `webkit` use the engine version bundled with this Playwright release.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost";

const crossBrowserDir = "tests/e2e/cross-browser/**";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      testMatch: crossBrowserDir,
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      testMatch: crossBrowserDir,
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "chrome",
      testMatch: crossBrowserDir,
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
    {
      name: "msedge",
      testMatch: crossBrowserDir,
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
  ],
});
