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
  /**
   * Assertions get a generous window because this suite runs against `next dev`, where a
   * route is compiled the first time it is asked for.
   *
   * This is the second half of the flake PLAN.md recorded on 2026-09-17, and the first fix
   * for it -- raising `navigationTimeout` below -- was incomplete. `page.goto` then waits
   * happily for the compile, returns, and hands the *first assertion* a page that is still
   * hydrating with only Playwright's 5 s default to find anything in it. Caught by the
   * label spec failing cold and passing warm on the very next run, which is exactly the
   * shape of the original report.
   */
  expect: { timeout: 30_000 },
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    /**
     * Playwright's navigation default is 30 s, and a cold `next dev` compiles a route on
     * first request: the scrub spec took 25.1 s against that ceiling and 4.0 s once warm.
     * It failed once and passed on every rerun, which is the worst kind of failure -- a
     * verification harness that cries wolf is worse than none (PLAN.md, "Found by the loop").
     *
     * The per-test timeout was never the problem; `ui.spec.ts` has set 180 s since PR #20.
     * `visit()` calls `page.goto(..., waitUntil: "networkidle")`, and this is the ceiling
     * that was actually being hit.
     */
    navigationTimeout: 120_000,
    actionTimeout: 30_000,
  },
  webServer: {
    command: "pnpm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
