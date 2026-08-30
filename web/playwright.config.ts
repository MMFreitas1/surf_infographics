import { defineConfig, devices } from "@playwright/test";

/**
 * UI verification. This is how a developer — or an agent helping debug — gets eyes on
 * the running app: screenshots plus every console error, page exception and failed
 * request, written to `verification/` as readable artifacts.
 */
export default defineConfig({
  testDir: "./tests/verify",
  outputDir: "./verification/artifacts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "verification/report.json" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "pnpm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
