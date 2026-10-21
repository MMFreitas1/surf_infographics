/**
 * The geometry behind the Session screen's four charts, with no DOM in sight.
 *
 * Hand-rolled rather than drawn with Observable Plot, which stays where it is useful — the
 * labelling trace panel, where the scales are the point. These four cards are specified as
 * exact geometry in the handover: a `0 0 400 168` box, a baseline at `y=132`, grid lines at
 * 24 / 78 / 132, a 2.2px stroke. Plot would generate its own scales and its own SVG and we
 * would spend the PR fighting it back into the design, and it `replaceChildren`s the node it
 * owns, which cost us a React overlay once already (PLAN.md).
 *
 * Pure functions returning numbers, so the numbers can be asserted. A chart tested by
 * looking at it is a chart that drifts.
 */

export interface Point {
  x: number;
  y: number;
}

export interface Bar {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * The box the per-wave and per-block series are drawn into, from the prototype.
 *
 * `left`/`right` leave room for the axis captions; the three grid rows are 54 apart and the
 * last of them *is* the baseline, which is why it is drawn twice — once faint as a grid
 * line, once solid in `--ink-800`.
 */
export const SERIES = {
  left: 34,
  right: 396,
  top: 24,
  baseline: 132,
  rows: 3,
  rowGap: 54,
} as const;

const SPAN = SERIES.right - SERIES.left; // 362
const DEPTH = SERIES.baseline - SERIES.top; // 108

/**
 * The Velocidade box: a fixed 0–40 km/h axis across the full 400 units.
 *
 * Fixed rather than fitted to the session, so two sessions can be compared by eye and so a
 * 74.8 km/h artefact of the kind Phase 5 convicted lands in a labelled overflow bin instead
 * of silently rescaling the whole chart around itself.
 */
export const SPEED = { max: 40, width: 400, baseline: 118, height: 94 } as const;

/** Where the i-th of n points sits. Half a slot in from each end, so bars have room. */
export function seriesX(index: number, count: number): number {
  return SERIES.left + ((index + 0.5) / count) * SPAN;
}

/** The three horizontal rules, the last of which the baseline sits on. */
export function gridLines(): number[] {
  return Array.from({ length: SERIES.rows }, (_, row) => SERIES.top + row * SERIES.rowGap);
}

/**
 * The top of the y axis: the largest value with headroom above it, never zero.
 *
 * A session where every block caught the same number of waves would otherwise divide by
 * zero, and one where none did would too. Both are real sessions.
 */
export function headroom(values: number[], factor: number): number {
  const max = Math.max(0, ...values);
  return max > 0 ? max * factor : 1;
}

/** Values to points, floor pinned at zero: a block with no waves belongs on the baseline. */
export function seriesPoints(values: number[], top: number): Point[] {
  return values.map((value, index) => ({
    x: seriesX(index, values.length),
    y: SERIES.baseline - (value / top) * DEPTH,
  }));
}

/** Bars under the same scale, centred on their point and half a slot wide. */
export function seriesBars(values: number[], top: number): Bar[] {
  const width = (SPAN / values.length) * 0.5;
  return seriesPoints(values, top).map((point) => ({
    x: point.x - width / 2,
    y: point.y,
    width,
    height: SERIES.baseline - point.y,
  }));
}

export function linePath(points: Point[]): string {
  if (points.length === 0) return "";
  return `M${points.map((p) => `${round(p.x)},${round(p.y)}`).join(" L ")}`;
}

/** The line, dropped to the baseline at both ends and closed. */
export function areaPath(points: Point[], baseline: number = SERIES.baseline): string {
  if (points.length === 0) return "";
  const first = points[0] as Point;
  const last = points[points.length - 1] as Point;
  return `${linePath(points)} L${round(last.x)},${baseline} L${round(first.x)},${baseline} Z`;
}

export function speedX(kmh: number): number {
  return (kmh / SPEED.max) * SPEED.width;
}

export interface Histogram {
  /** One bar per bin that fits under 40 km/h. */
  bars: Bar[];
  /** Everything at or beyond 40 km/h, in one bar, or null when there is nothing out there. */
  overflow: (Bar & { seconds: number }) | null;
}

/**
 * The measured distribution: L6's own bins, placed on the fixed axis.
 *
 * Re-binning here would be the browser computing a statistic, which is the one thing the
 * metrics contract exists to stop. Bins are in m/s because the pipeline is SI; the axis is
 * km/h because the design is. Anything from 40 km/h up is collected into a single bar that
 * says how many seconds it holds, rather than being dropped — a reading that fast is either
 * the best wave of the year or an artefact, and both deserve to be visible.
 */
export function histogram(edgesMs: number[], counts: number[]): Histogram {
  const bars: Bar[] = [];
  let overflowSeconds = 0;
  let peak = Math.max(0, ...counts);
  if (peak === 0) peak = 1;

  for (const [bin, seconds] of counts.entries()) {
    const lo = (edgesMs[bin] ?? 0) * 3.6;
    const hi = (edgesMs[bin + 1] ?? lo) * 3.6;
    if (lo >= SPEED.max) {
      overflowSeconds += seconds;
      continue;
    }
    const height = (seconds / peak) * (SPEED.height + 14);
    const x = speedX(lo);
    bars.push({
      x: x + 1,
      y: SPEED.baseline - height,
      width: Math.max(1, speedX(Math.min(hi, SPEED.max)) - x - 2),
      height,
    });
  }

  if (overflowSeconds === 0) return { bars, overflow: null };
  const height = (overflowSeconds / peak) * (SPEED.height + 14);
  return {
    bars,
    overflow: {
      x: speedX(SPEED.max) - 17,
      y: SPEED.baseline - height,
      width: 17,
      height,
      seconds: overflowSeconds,
    },
  };
}

/** One decimal is the resolution of a 400-unit viewBox; more is noise in the DOM. */
function round(value: number): string {
  return value.toFixed(1);
}
