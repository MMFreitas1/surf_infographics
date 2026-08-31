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
