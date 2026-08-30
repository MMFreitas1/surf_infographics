import { mkdir, writeFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const OUT = "verification";

/** Everything the browser complained about during one page visit. */
interface PageDiagnostics {
  url: string;
  consoleErrors: string[];
  consoleWarnings: string[];
  pageErrors: string[];
  failedRequests: string[];
}

async function visit(page: import("@playwright/test").Page, path: string) {
  const diag: PageDiagnostics = {
    url: path,
    consoleErrors: [],
    consoleWarnings: [],
    pageErrors: [],
    failedRequests: [],
  };

  page.on("console", (msg) => {
    if (msg.type() === "error") diag.consoleErrors.push(msg.text());
    if (msg.type() === "warning") diag.consoleWarnings.push(msg.text());
  });
  page.on("pageerror", (err) => diag.pageErrors.push(`${err.name}: ${err.message}`));
  page.on("requestfailed", (req) => {
    diag.failedRequests.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`);
  });

  await page.goto(path, { waitUntil: "networkidle" });
  return diag;
}

test("home page renders without browser errors", async ({ page }, testInfo) => {
  const diag = await visit(page, "/");

  await mkdir(OUT, { recursive: true });
  const slug = testInfo.title.replace(/\W+/g, "-").toLowerCase();
  await page.screenshot({ path: `${OUT}/${slug}.png`, fullPage: true });
  await writeFile(`${OUT}/${slug}.json`, `${JSON.stringify(diag, null, 2)}\n`);

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Surf Infographics");

  expect(diag.pageErrors, "uncaught exceptions in the page").toEqual([]);
  expect(diag.consoleErrors, "console errors").toEqual([]);
  expect(diag.failedRequests, "failed network requests").toEqual([]);
});
