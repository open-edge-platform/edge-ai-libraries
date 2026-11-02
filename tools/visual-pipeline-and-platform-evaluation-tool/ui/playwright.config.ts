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
 *
 * Set `PLAYWRIGHT_WEB_SERVER=1` (what CI does) to let Playwright serve the
 * production bundle itself via `vite preview` instead of requiring an already
 * running UI. No backend is involved in that mode.
 */
const useWebServer = process.env.PLAYWRIGHT_WEB_SERVER === "1";
const previewPort = Number(process.env.PLAYWRIGHT_PREVIEW_PORT ?? 4173);

const baseURL =
  process.env.PLAYWRIGHT_BASE_URL ??
  (useWebServer ? `http://localhost:${previewPort}` : "http://localhost");

const crossBrowserDir = "tests/e2e/cross-browser/**";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [
        ["github"],
        ["list"],
        ["html", { open: "never" }],
        ["junit", { outputFile: "test-results/junit.xml" }],
        ["json", { outputFile: "test-results/report.json" }],
      ]
    : [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: useWebServer
    ? {
        command: `npm run preview -- --port ${previewPort} --strictPort`,
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        stdout: "pipe",
        stderr: "pipe",
      }
    : undefined,
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
