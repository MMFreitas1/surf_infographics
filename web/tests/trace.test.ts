import { describe, expect, it } from "vitest";
import {
  cadence,
  clampSpan,
  coverageOf,
  formatClock,
  orderSpan,
  overlaps,
  spansWhere,
  withRuns,
} from "@/lib/trace";

const series = (flags: boolean[]) => flags.map((observed, i) => ({ t: i, observed }));

describe("withRuns", () => {
  it("keeps one run when provenance never changes", () => {
    const points = withRuns(series([true, true, true]));
    expect(points).toHaveLength(3);
    expect(new Set(points.map((p) => p.run))).toEqual(new Set([0]));
    expect(points.every((p) => p.series === "measured")).toBe(true);
  });

  it("starts a new run wherever a fix is lost or regained", () => {
    const points = withRuns(series([true, true, false, false, true]));
    expect(points.filter((p) => !p.bridge).map((p) => p.run)).toEqual([0, 0, 1, 1, 2]);
  });

  it("bridges each boundary so the two paths meet instead of leaving a gap", () => {
    const points = withRuns(series([true, false]));
    const bridge = points.filter((p) => p.bridge);
    expect(bridge).toHaveLength(1);
    // The dashed run begins at the last measured instant, so the line is continuous...
    expect(bridge[0]?.t).toBe(0);
    expect(bridge[0]?.run).toBe(1);
    // ...but the copy never claims to be a measurement of that second.
    expect(bridge[0]?.observed).toBe(true);
    expect(bridge[0]?.series).toBe("estimated");
  });

  it("draws an all-blind session as one estimated run, not as nothing", () => {
    const points = withRuns(series([false, false, false]));
    expect(points).toHaveLength(3);
    expect(points.every((p) => p.series === "estimated")).toBe(true);
  });

  it("handles a session that starts and ends without a fix", () => {
    const points = withRuns(series([false, true, false]));
    expect(points.filter((p) => !p.bridge).map((p) => p.series)).toEqual([
      "estimated",
      "measured",
      "estimated",
    ]);
    expect(points.filter((p) => p.bridge)).toHaveLength(2);
  });

  it("is empty for an empty series rather than throwing", () => {
    expect(withRuns([])).toEqual([]);
  });
});

describe("spansWhere", () => {
  it("finds the blind stretches", () => {
    expect(spansWhere(series([true, false, false, true]), false)).toEqual([
      { t_start: 1, t_end: 3 },
    ]);
  });

  it("closes a trailing span with the series' own cadence", () => {
    expect(spansWhere(series([true, false, false]), false)).toEqual([{ t_start: 1, t_end: 3 }]);
  });

  it("covers the whole session when nothing was ever seen", () => {
    expect(spansWhere(series([false, false]), false)).toEqual([{ t_start: 0, t_end: 2 }]);
  });

  it("finds nothing when there is nothing to find", () => {
    expect(spansWhere(series([true, true]), false)).toEqual([]);
    expect(spansWhere([], false)).toEqual([]);
  });
});

describe("cadence", () => {
  it("reads the series' own spacing", () => {
    expect(cadence([{ t: 0 }, { t: 5 }, { t: 10 }])).toBe(5);
  });

  it("falls back to 1 Hz when there is nothing to measure", () => {
    expect(cadence([])).toBe(1);
    expect(cadence([{ t: 3 }])).toBe(1);
  });

  it("ignores non-advancing steps", () => {
    expect(cadence([{ t: 0 }, { t: 0 }, { t: 1 }, { t: 2 }])).toBe(1);
  });
});

describe("spans drawn by hand", () => {
  it("reads a backwards drag forwards", () => {
    expect(orderSpan(90, 10)).toEqual({ t_start: 10, t_end: 90 });
    expect(orderSpan(10, 90)).toEqual({ t_start: 10, t_end: 90 });
  });

  it("keeps a drag off the edge inside the session", () => {
    expect(clampSpan({ t_start: -40, t_end: 4000 }, [0, 100])).toEqual({
      t_start: 0,
      t_end: 100,
    });
  });

  it("knows whether two spans touch", () => {
    expect(overlaps({ t_start: 0, t_end: 10 }, { t_start: 9, t_end: 20 })).toBe(true);
    expect(overlaps({ t_start: 0, t_end: 10 }, { t_start: 10, t_end: 20 })).toBe(false);
  });
});

describe("coverageOf", () => {
  it("reports how much of a marked span the watch actually saw", () => {
    const rows = series([true, true, false, false]);
    expect(coverageOf(rows, { t_start: 0, t_end: 4 })).toBe(0.5);
    expect(coverageOf(rows, { t_start: 0, t_end: 2 })).toBe(1);
    expect(coverageOf(rows, { t_start: 2, t_end: 4 })).toBe(0);
  });

  it("reports zero for a span with no samples in it at all", () => {
    expect(coverageOf(series([true]), { t_start: 50, t_end: 60 })).toBe(0);
  });
});

describe("formatClock", () => {
  it("counts from the start of the session, not from 1970", () => {
    expect(formatClock(1787937820 + 75, 1787937820)).toBe("1:15");
    expect(formatClock(1787937820, 1787937820)).toBe("0:00");
  });

  it("never shows negative time", () => {
    expect(formatClock(0, 100)).toBe("0:00");
  });
});
