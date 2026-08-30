import { mkdir, writeFile } from "node:fs/promises";
import { expect, type Page, test } from "@playwright/test";

const OUT = "verification";
const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

/** Everything the browser complained about during one page visit. */
interface PageDiagnostics {
  url: string;
  consoleErrors: string[];
  consoleWarnings: string[];
  pageErrors: string[];
  failedRequests: string[];
}

function watch(page: Page, path: string): PageDiagnostics {
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

  return diag;
}

async function visit(page: Page, path: string) {
  const diag = watch(page, path);
  await page.goto(path, { waitUntil: "networkidle" });
  return diag;
}

async function record(page: Page, diag: PageDiagnostics, title: string) {
  await mkdir(OUT, { recursive: true });
  const slug = title.replace(/\W+/g, "-").toLowerCase();
  await page.screenshot({ path: `${OUT}/${slug}.png`, fullPage: true });
  await writeFile(`${OUT}/${slug}.json`, `${JSON.stringify(diag, null, 2)}\n`);
}

function clean(diag: PageDiagnostics) {
  expect(diag.pageErrors, "uncaught exceptions in the page").toEqual([]);
  expect(diag.consoleErrors, "console errors").toEqual([]);
  expect(diag.failedRequests, "failed network requests").toEqual([]);
}

/** The first stored session, or null when the API is down or empty. */
async function firstActivity(): Promise<string | null> {
  try {
    const response = await fetch(`${API}/activities`);
    if (!response.ok) return null;
    const rows = (await response.json()) as { activity_id: string }[];
    return rows[0]?.activity_id ?? null;
  } catch {
    return null;
  }
}

test("session list renders without browser errors", async ({ page }, testInfo) => {
  const diag = await visit(page, "/");
  await record(page, diag, testInfo.title);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Surf Infographics");
  clean(diag);
});

test("a session can be scrubbed and a wave marked", async ({ page }, testInfo) => {
  // deck.gl is loaded lazily and, in dev, compiled on first request. That is slow the first
  // time and instant afterwards, so the wait is generous rather than the assertions weak.
  test.setTimeout(180_000);
  const SLOW = { timeout: 90_000 };

  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const diag = await visit(page, `/label/${activityId}`);

  // Every panel drawn, including the one deck.gl renders.
  await expect(page.getByRole("heading", { name: "Speed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cross-shore velocity" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Position uncertainty" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Track" })).toBeVisible(SLOW);
  await expect(page.locator("canvas").first()).toBeVisible(SLOW);

  // The blind stretches have to be visible as stretches, or a labeller marks through one.
  const surface = page.locator(".drag-surface").first();
  await expect(page.locator(".band-blind").first()).toBeVisible();
  expect(await page.locator(".band-blind").count()).toBeGreaterThan(0);

  // Candidates stay hidden until a blind pass exists — ADR-0012, seen from the outside.
  await expect(page.locator(".band-candidate")).toHaveCount(0);

  // Drag across the trace: it becomes a draft, with its measured fraction stated.
  const box = await surface.boundingBox();
  if (!box) throw new Error("the drag surface has no box");
  await page.mouse.move(box.x + box.width * 0.4, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.45, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();

  await expect(page.locator(".draft")).toHaveCount(1);
  await expect(page.locator(".draft .coverage")).toContainText("actually measured");
  await expect(page.locator(".band-draft").first()).toBeVisible();

  await record(page, diag, testInfo.title);
  clean(diag);
});
