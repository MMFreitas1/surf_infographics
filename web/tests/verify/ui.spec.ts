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

test("the session screen renders its count and its absences", async ({ page }, testInfo) => {
  // Same reasoning as the scrub spec: a cold dev server compiles this route on first
  // request, and the fonts are fetched and self-hosted at build time.
  test.setTimeout(180_000);
  const SLOW = { timeout: 90_000 };

  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const diag = await visit(page, `/session/${activityId}`);

  // The hero is the reason PR 0 existed: one number, committed to by the pipeline.
  const hero = page.locator(".hero-value");
  await expect(hero).toBeVisible(SLOW);
  await expect(hero).toHaveText(/^\d+$/, SLOW);

  // The three panels this PR can fill honestly.
  await expect(page.locator(".panel-ink")).toBeVisible();
  await expect(page.locator(".coverage-bar")).toBeVisible();

  // The two it cannot. Absence is a designed state and must actually be drawn, not
  // omitted — a missing panel and an unavailable one say different things.
  expect(await page.locator(".panel-absent").count()).toBeGreaterThanOrEqual(2);

  // "Proposed" is stated once, in the banner, and nowhere else on the screen.
  await expect(page.locator(".method-banner")).toBeVisible();

  await record(page, diag, testInfo.title);
  clean(diag);
});

test("the four chart cards draw what the pipeline measured", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const SLOW = { timeout: 90_000 };

  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  // The same figures the cards are drawn from, straight from the route. The point of the
  // check is that the screen renders *these* and derives nothing of its own.
  const metrics = (await (await fetch(`${API}/activities/${activityId}/metrics`)).json()) as {
    cadence: unknown[];
    returns: unknown[];
    wave_count: number;
    ride_speed: { n_seconds: number; mean_ms: number } | null;
  };

  const diag = await visit(page, `/session/${activityId}`);
  await expect(page.locator(".card-grid .chart-card")).toHaveCount(4, SLOW);

  // Distância: a headline and a split that fills the bar.
  await expect(page.locator(".chart-value")).toHaveText(/\d/, SLOW);
  await expect(page.locator(".split-swim").first()).toBeVisible();
  await expect(page.locator(".split-ride").first()).toBeVisible();

  // Cadência: one dot per block the pipeline bucketed, no more and no fewer.
  await expect(page.locator(".cadence-line")).toBeVisible();
  await expect(page.locator(".chart-dot:not(.chart-dot-amber)")).toHaveCount(
    metrics.cadence.length,
  );

  // Velocidade: the measured bars, with the mean drawn over them rather than instead
  // of them. A bell would be a drawing of two numbers; these are the seconds.
  expect(await page.locator(".speed-bar").count()).toBeGreaterThan(0);
  if (metrics.ride_speed) {
    // A vertical line has no width, so `toBeVisible` would call it hidden. Assert where
    // it landed instead, which is the better check anyway: the mean is drawn at the mean.
    const x = await page.locator(".speed-mean").getAttribute("x1");
    expect(Number(x)).toBeCloseTo(((metrics.ride_speed.mean_ms * 3.6) / 40) * 400, 1);
    const speedCard = page.locator(".chart-card").filter({ has: page.locator(".speed-bar") });
    await expect(speedCard.locator(".chart-note")).toContainText(
      String(metrics.ride_speed.n_seconds),
    );
  }

  // Retorno: a bar and a dot per paddle back out.
  await expect(page.locator(".return-bar")).toHaveCount(metrics.returns.length);
  await expect(page.locator(".chart-dot-amber")).toHaveCount(metrics.returns.length);

  // /waves and /metrics are the same reading of the same session, and the screen must
  // not be the place that first disagrees: the hero and the speed card's sample both
  // count the waves L5 settled.
  await expect(page.locator(".hero-value")).toHaveText(String(metrics.wave_count));

  await record(page, diag, testInfo.title);
  clean(diag);
});

test("a wave profile draws its own ride and opens it on the track", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const SLOW = { timeout: 90_000 };

  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const metrics = (await (await fetch(`${API}/activities/${activityId}/metrics`)).json()) as {
    waves: { index: number; position_coverage: number }[];
  };

  const diag = await visit(page, `/session/${activityId}`);

  // One card per settled wave. The grid is a view of L5's answer, not a second opinion
  // about it, so it cannot hold more cards or fewer.
  const cards = page.locator(".flip-card");
  await expect(cards).toHaveCount(metrics.waves.length, SLOW);

  // Coverage is the card's opacity: a ride the watch barely saw is barely there. Check
  // the extremes against the figures rather than the look of it.
  const worst = metrics.waves.reduce((a, b) => (b.position_coverage < a.position_coverage ? b : a));
  const best = metrics.waves.reduce((a, b) => (b.position_coverage > a.position_coverage ? b : a));
  if (worst.position_coverage < best.position_coverage) {
    const opacity = async (index: number) =>
      Number(
        await page
          .locator(".profile-slot", { has: page.getByText(String(index).padStart(2, "0")) })
          .locator(".flip-front")
          .evaluate((el) => getComputedStyle(el).opacity),
      );
    expect(await opacity(worst.index)).toBeLessThan(await opacity(best.index));
  }

  // The ride is drawn from the track, and an estimated stretch is dashed there as it is
  // on the big map (ADR-0010).
  expect(await page.locator(".profile-measured, .profile-estimated").count()).toBeGreaterThan(0);

  // Opening a wave isolates it above. Not a link to the Onda screen — that waits on
  // Phases 6 and 7, and a card that navigates nowhere is worse than one that shows you
  // the ride.
  await expect(page.locator(".selection-callout")).toHaveCount(0);
  await cards.first().click();
  await expect(page.locator(".selection-callout")).toBeVisible(SLOW);
  await expect(page.locator(".flip-card-selected")).toHaveCount(1);

  await record(page, diag, testInfo.title);
  clean(diag);
});

test("the basemap layers tick on and off and carry their own credit", async ({
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const SLOW = { timeout: 90_000 };

  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const served = (await (await fetch(`${API}/basemap`)).json()) as {
    layers: { id: string; attribution: string; default: boolean }[];
  };

  const diag = await visit(page, `/session/${activityId}`);
  const ticks = page.locator(".layer-tick input");
  await expect(ticks).toHaveCount(served.layers.length, SLOW);

  // What the API says opens ticked is what opens ticked. Two copies of that answer is how
  // the control and the map come to disagree about what is on screen.
  for (const [index, layer] of served.layers.entries()) {
    await expect(ticks.nth(index)).toBeChecked({ checked: layer.default });
  }

  // Attribution is a licence condition, and maplibre renders it only for sources a visible
  // layer uses — so ticking a layer off has to take its credit with it.
  const offIndex = served.layers.findIndex((layer) => !layer.default);
  const credit = page.locator(".maplibregl-ctrl-attrib-inner");
  if (offIndex >= 0) {
    const off = served.layers[offIndex] as (typeof served.layers)[number];
    await expect(credit).not.toContainText(off.attribution, SLOW);
    await ticks.nth(offIndex).check();
    await expect(credit).toContainText(off.attribution, SLOW);
  }

  // The strength slider belongs to the one layer that covers what is under it, so it is
  // there when that layer is and gone when it is not.
  const imageryIndex = served.layers.findIndex((layer) => layer.id === "imagery");
  await expect(page.locator(".layer-blend input")).toHaveCount(1);
  await ticks.nth(imageryIndex).uncheck();
  await expect(page.locator(".layer-blend input")).toHaveCount(0);

  await record(page, diag, testInfo.title);
  clean(diag);
});

test("the method banner dismisses and stays dismissed", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const diag = await visit(page, `/session/${activityId}`);
  const banner = page.locator(".method-banner");
  await expect(banner).toBeVisible({ timeout: 90_000 });

  await banner.getByRole("button").click();
  await expect(banner).toHaveCount(0);

  // It is stored per browser, so a reload must not bring it back.
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator(".hero-value")).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".method-banner")).toHaveCount(0);

  await record(page, diag, testInfo.title);
  clean(diag);
});

test("the track map draws the session and plays it back", async ({ page }, testInfo) => {
  // deck.gl is code-split and compiled on first request in dev: slow once, instant after.
  test.setTimeout(180_000);
  const SLOW = { timeout: 90_000 };

  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const diag = await visit(page, `/session/${activityId}`);

  await expect(page.locator(".map-card")).toBeVisible(SLOW);
  await expect(page.locator(".map-body canvas").first()).toBeVisible(SLOW);

  // The legend names the states the track draws. The imagery credit is a licence condition
  // and a map without it is a breach on screen.
  await expect(page.locator(".map-legend")).toBeVisible();
  // The credit is maplibre's own, rendered from each source's attribution field, so it
  // appears exactly when that layer does and follows the ticks (ADR-0019, ADR-0021).
  //
  // It names **DGT**, not Esri. ADR-0021 moved imagery to DGT's OrtoSat 2023 under CC BY
  // 4.0 and left Esri as the relief layer alone, which is off by default -- so this
  // assertion went stale in #67 and this suite has been red since, unnoticed, because
  // `make check` runs lint, typecheck, test and evals but not `verify`.
  await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText("Território");

  // The ribbon and the blind rail are separate rows on purpose: a wave and a blind window
  // are not alternatives. Both must actually be drawn.
  expect(await page.locator(".ribbon-wave").count()).toBeGreaterThan(0);
  expect(await page.locator(".blind-span").count()).toBeGreaterThan(0);

  // Sit spots: the legend key only appears when there are peaks to key, so its presence is
  // the cheapest honest proof that L1.5 reached the screen (the marks themselves are WebGL
  // and not queryable from here).
  await expect(page.locator(".key-sit")).toBeVisible();

  // Playback moves the clock.
  const clock = page.locator(".clock");
  const before = await clock.textContent();
  await page.locator(".play-button").click();
  await expect(clock).not.toHaveText(before ?? "", { timeout: 20_000 });
  await page.locator(".play-button").click();

  await record(page, diag, testInfo.title);
  clean(diag);
});

test("selecting a wave isolates it and says how it was decided", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const activityId = await firstActivity();
  test.skip(activityId === null, "no ingested session — start the API and post an activity");

  const diag = await visit(page, `/session/${activityId}`);
  await expect(page.locator(".map-card")).toBeVisible({ timeout: 90_000 });

  await page.locator(".ribbon-wave").first().click();

  const callout = page.locator(".selection-callout");
  await expect(callout).toBeVisible();
  // The verdict's own reason, carried through unchanged from the pipeline.
  await expect(page.locator(".selection-reason")).not.toBeEmpty();
  await expect(page.locator(".selection-meta")).toContainText(/%/);

  await page.locator(".button-ghost").click();
  await expect(callout).toHaveCount(0);

  await record(page, diag, testInfo.title);
  clean(diag);
});
