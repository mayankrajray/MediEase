/**
 * Playwright journeys against the running stack (docs/TESTING.md §3). Run with
 * `make e2e` after `make up && make seed`: it uses the official Playwright image,
 * whose browsers match @playwright/test (keep the two versions equal), on the
 * compose network, so nothing is installed on the host.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  // A flaky journey is a broken journey (docs/TESTING.md §2): no retries hide it.
  retries: 0,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  forbidOnly: process.env.CI !== undefined,
  reporter: [["list"], ["html", { outputFolder: "../playwright-report", open: "never" }]],
  outputDir: "../test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // The front-desk screen the clinic pages are designed for (apps/web/CLAUDE.md).
    viewport: { width: 1366, height: 768 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } } }],
});
