import { describe, expect, it } from "vitest";
import {
  cadence,
  clampSpan,
  coverageOf,
  dashPath,
  formatClock,
  metresBetween,
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

describe("metresBetween", () => {
  it("measures a degree of latitude at roughly 111 km", () => {
    expect(metresBetween([-9, 38], [-9, 39])).toBeCloseTo(111_320, -3);
  });

  it("shrinks a degree of longitude by the cosine of the latitude", () => {
    // At 38°N a degree of longitude is about 88 km, not 111.
    expect(metresBetween([-9, 38], [-8, 38])).toBeCloseTo(
      111_320 * Math.cos((38 * Math.PI) / 180),
      -3,
    );
  });

  it("is zero for a point against itself", () => {
    expect(metresBetween([-9, 38], [-9, 38])).toBe(0);
  });
});

describe("dashPath", () => {
  /** A straight run north from the synthetic origin, one point per metre. */
  const straight = (metres: number): [number, number][] =>
    Array.from({ length: metres + 1 }, (_, i) => [-9, 38 + i / 111_320] as [number, number]);

  it("splits a line into dashes of the length asked for", () => {
    const dashes = dashPath(straight(100), 10, 10);

    // 100 m alternating 10 on / 10 off is five dashes.
    expect(dashes).toHaveLength(5);
    for (const dash of dashes) {
      const length = dash
        .slice(1)
        .reduce((sum, p, i) => sum + metresBetween(dash[i] as [number, number], p), 0);
      expect(length).toBeCloseTo(10, 0);
    }
  });

  it("leaves gaps between them", () => {
    const dashes = dashPath(straight(100), 10, 10);
    for (let i = 1; i < dashes.length; i += 1) {
      const previousEnd = dashes[i - 1]?.at(-1) as [number, number];
      const nextStart = dashes[i]?.[0] as [number, number];
      expect(metresBetween(previousEnd, nextStart)).toBeCloseTo(10, 0);
    }
  });

  it("spaces dashes by ground distance, not by sample count", () => {
    // Twenty seconds sitting still then twenty metres of travel. Dashing by index would put
    // every dash in the first spot -- which is exactly where the surfer did not move.
    const still: [number, number][] = Array.from({ length: 20 }, () => [-9, 38]);
    const moving = straight(20);
    const dashes = dashPath([...still, ...moving], 5, 5);

    expect(dashes.length).toBeGreaterThan(1);
    expect(dashes.length).toBeLessThanOrEqual(3);
  });

  it("returns the whole path when the dash length is not usable", () => {
    expect(dashPath(straight(10), 0, 5)).toEqual([straight(10)]);
    expect(dashPath(straight(10), 5, 0)).toEqual([straight(10)]);
  });

  it("draws nothing from a path with no length", () => {
    expect(dashPath([], 5, 5)).toEqual([]);
    expect(dashPath([[-9, 38]], 5, 5)).toEqual([]);
  });

  it("handles a segment longer than several dashes at once", () => {
    // One 100 m step: a fast ride between two seconds. The loop must not assume one
    // boundary per segment.
    const leap: [number, number][] = [
      [-9, 38],
      [-9, 38 + 100 / 111_320],
    ];
    expect(dashPath(leap, 10, 10)).toHaveLength(5);
  });
});
