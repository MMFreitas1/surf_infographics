/**
 * Turning a track into something drawable, without lying about it.
 *
 * Roughly half of a surf session has no GPS fix, and L1 estimates a position for every one
 * of those seconds anyway (ADR-0010). Drawn as one continuous line, an estimated stretch is
 * indistinguishable from a measured one — and a labeller would mark an interpolated stretch
 * believing they saw it. Everything here exists to keep the two apart: `withRuns` splits a
 * series where its provenance changes so the halves can be drawn differently, and
 * `spansWhere` finds the stretches worth shading.
 *
 * All of it is pure, so it is testable without a browser.
 */

/** Anything with a time and a provenance. Both tracks the API serves qualify. */
export interface Observed {
  t: number;
  observed: boolean;
}

/** A half-open interval of session time, in the same seconds the API speaks. */
export interface Span {
  t_start: number;
  t_end: number;
}

/** One plotted point, tagged with which path it belongs to and how to draw it. */
export type RunPoint<T> = T & {
  run: number;
  series: "measured" | "estimated";
  bridge: boolean;
};

/**
 * Split a series into runs of like provenance, and tag each point with its run.
 *
 * Plot draws one path per `z` value, so the run index is what lets a measured stretch be a
 * solid line and an estimated one a dashed line in the same chart.
 *
 * Each run after the first starts with a copy of the previous run's last point — a bridge —
 * so consecutive runs meet instead of leaving a gap that reads as "the watch stopped here".
 * The copy keeps its own truthful `observed` value and is marked `bridge`, so nothing
 * downstream can mistake it for a second measurement of that instant.
 */
export function withRuns<T extends Observed>(rows: readonly T[]): RunPoint<T>[] {
  const out: RunPoint<T>[] = [];
  let run = 0;

  rows.forEach((row, i) => {
    const previous = rows[i - 1];
    if (previous !== undefined && previous.observed !== row.observed) {
      run += 1;
      out.push({
        ...previous,
        run,
        series: row.observed ? "measured" : "estimated",
        bridge: true,
      });
    }
    out.push({
      ...row,
      run,
      series: row.observed ? "measured" : "estimated",
      bridge: false,
    });
  });

  return out;
}

/**
 * The stretches where provenance matches `want`, as spans.
 *
 * A span runs to the start of the next sample, so shading covers the second it describes
 * rather than stopping at the instant it was sampled. The final span is extended by the
 * series' own cadence for the same reason.
 */
export function spansWhere<T extends Observed>(rows: readonly T[], want: boolean): Span[] {
  const spans: Span[] = [];
  let start: number | null = null;

  rows.forEach((row) => {
    const matches = row.observed === want;
    if (matches && start === null) start = row.t;
    if (!matches && start !== null) {
      spans.push({ t_start: start, t_end: row.t });
      start = null;
    }
  });

  if (start !== null) {
    spans.push({ t_start: start, t_end: (rows[rows.length - 1]?.t ?? start) + cadence(rows) });
  }
  return spans;
}

/** The series' own sample spacing, as the median step. Falls back to 1 Hz, as L3 does. */
export function cadence(rows: readonly { t: number }[]): number {
  if (rows.length < 2) return 1;
  const steps: number[] = [];
  for (let i = 1; i < rows.length; i += 1) {
    const step = (rows[i]?.t ?? 0) - (rows[i - 1]?.t ?? 0);
    if (step > 0) steps.push(step);
  }
  if (steps.length === 0) return 1;
  steps.sort((a, b) => a - b);
  return steps[Math.floor(steps.length / 2)] ?? 1;
}

/** A drag has no direction: whichever end came first, the span reads forward. */
export function orderSpan(a: number, b: number): Span {
  return a <= b ? { t_start: a, t_end: b } : { t_start: b, t_end: a };
}

/** Keep a span inside the session. A drag off the edge of the chart is still a real intent. */
export function clampSpan(span: Span, domain: readonly [number, number]): Span {
  const [lo, hi] = domain;
  return {
    t_start: Math.min(Math.max(span.t_start, lo), hi),
    t_end: Math.min(Math.max(span.t_end, lo), hi),
  };
}

/** Whether two spans share any time at all. */
export function overlaps(a: Span, b: Span): boolean {
  return a.t_start < b.t_end && b.t_start < a.t_end;
}

/**
 * What fraction of a span the watch actually saw.
 *
 * The same question `WaveCandidate.position_coverage` answers on the server, asked here of
 * an interval a person just drew — so the UI can tell them, before they save it, that they
 * have marked a stretch the watch was blind through.
 */
export function coverageOf<T extends Observed>(rows: readonly T[], span: Span): number {
  const during = rows.filter((row) => row.t >= span.t_start && row.t < span.t_end);
  if (during.length === 0) return 0;
  return during.filter((row) => row.observed).length / during.length;
}

/** Session-relative clock, as m:ss. Absolute unix seconds mean nothing to a labeller. */
export function formatClock(t: number, start: number): string {
  const seconds = Math.max(0, Math.round(t - start));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

/** A duration, for reading back what was just marked. */
export function formatDuration(seconds: number): string {
  return `${seconds.toFixed(1)}s`;
}

/** One point on the ground, as deck.gl wants it: longitude first. */
export type LngLat = [number, number];

/** Metres per degree of latitude. Close enough everywhere; the error is under 1%. */
const M_PER_DEG_LAT = 111_320;

/**
 * Ground distance between two points, in metres.
 *
 * Equirectangular rather than haversine on purpose: a surf session spans a few hundred
 * metres, where the two agree to far better than the GPS noise, and this one is cheap enough
 * to run over every second of a 3790-sample track on every render.
 */
export function metresBetween(a: LngLat, b: LngLat): number {
  const midLat = ((a[1] + b[1]) / 2) * (Math.PI / 180);
  const dx = (b[0] - a[0]) * M_PER_DEG_LAT * Math.cos(midLat);
  const dy = (b[1] - a[1]) * M_PER_DEG_LAT;
  return Math.hypot(dx, dy);
}

/**
 * Chop a path into dashes, measured on the ground.
 *
 * The design's three states are solid / **dashed translucent** / absence, and a dash is the
 * only one of the three that a stroke colour alone cannot carry — at a glance, a fainter
 * continuous line still reads as a line someone drew from measurements.
 *
 * Done here rather than with `@deck.gl/extensions`' `PathStyleExtension` because that is a
 * new core dependency and this is twenty lines. Dashes are spaced by **metres travelled**,
 * not by sample index: an estimated stretch where the surfer sat still would otherwise
 * bunch every dash into one spot, which is exactly where the uncertainty is largest and the
 * drawing should be clearest.
 */
export function dashPath(path: readonly LngLat[], dashM: number, gapM: number): LngLat[][] {
  if (path.length < 2 || dashM <= 0 || gapM <= 0) return path.length > 1 ? [[...path]] : [];

  // A micron. Distances here accumulate over thousands of segments, so a boundary that
  // should land exactly on the final point lands a few femtometres past it instead --
  // which splits off a zero-length dash and makes 100 m of 10-on-10-off come out as six
  // dashes rather than five. Comparing with a tolerance is what stops the arithmetic from
  // inventing a mark that has no length.
  const EPS = 1e-6;

  const dashes: LngLat[][] = [];
  let current: LngLat[] = [path[0] as LngLat];
  let drawing = true;
  let remaining = dashM;

  for (let i = 1; i < path.length; i += 1) {
    let from = path[i - 1] as LngLat;
    const to = path[i] as LngLat;
    let segment = metresBetween(from, to);

    // A single second can span several dashes when the surfer is moving fast, so this
    // consumes the segment piece by piece rather than assuming one boundary per step.
    while (segment > remaining + EPS) {
      const ratio = remaining / segment;
      const split: LngLat = [
        from[0] + (to[0] - from[0]) * ratio,
        from[1] + (to[1] - from[1]) * ratio,
      ];
      if (drawing) {
        current.push(split);
        dashes.push(current);
        current = [];
      } else {
        current = [split];
      }
      drawing = !drawing;
      segment -= remaining;
      remaining = drawing ? dashM : gapM;
      from = split;
    }

    remaining -= segment;
    if (drawing) current.push(to);
  }

  if (drawing && current.length > 1) dashes.push(current);
  // A dash with no length draws nothing and costs a layer entry; drop it rather than ship
  // it. Belt and braces with EPS above, because the two failure modes differ: that one
  // prevents the split, this one catches a degenerate run however it arose.
  return dashes.filter(
    (dash) => dash.length > 1 && metresBetween(dash[0] as LngLat, dash.at(-1) as LngLat) > EPS,
  );
}
