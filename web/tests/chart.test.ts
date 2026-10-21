import { describe, expect, it } from "vitest";
import {
  areaPath,
  gridLines,
  headroom,
  histogram,
  linePath,
  MINI,
  miniTrack,
  SERIES,
  SPEED,
  seriesBars,
  seriesPoints,
  seriesX,
  speedX,
} from "@/lib/chart";

/**
 * Known answers, not an eyeball (CLAUDE.md). Every number here is the handover's own
 * geometry worked out by hand: a chart checked by looking at it is a chart that drifts a
 * pixel per PR until it is no longer the design.
 */
describe("the series box", () => {
  it("places three points where the prototype places them", () => {
    expect(seriesX(0, 3)).toBeCloseTo(94.333, 3);
    expect(seriesX(1, 3)).toBeCloseTo(215.0, 3);
    expect(seriesX(2, 3)).toBeCloseTo(335.667, 3);
  });

  it("keeps half a slot of margin at each end, whatever the count", () => {
    for (const n of [1, 2, 6, 11, 40]) {
      expect(seriesX(0, n)).toBeGreaterThan(SERIES.left);
      expect(seriesX(n - 1, n)).toBeLessThan(SERIES.right);
    }
  });

  it("draws three rules, the last of them the baseline", () => {
    expect(gridLines()).toEqual([24, 78, 132]);
    expect(gridLines().at(-1)).toBe(SERIES.baseline);
  });

  it("gives bars half the slot they sit in", () => {
    const [bar] = seriesBars([1, 1, 1], 1);
    expect(bar?.width).toBeCloseTo(60.333, 3);
  });
});

describe("a plotted series", () => {
  it("puts the top value at the top rule and a zero on the baseline", () => {
    const points = seriesPoints([0, 10], 10);
    expect(points[0]?.y).toBe(SERIES.baseline);
    expect(points[1]?.y).toBe(SERIES.top);
  });

  it("scales everything else in between", () => {
    expect(seriesPoints([5], 10)[0]?.y).toBe(78);
  });

  it("leaves headroom above the largest value", () => {
    expect(headroom([2, 3, 1], 1.14)).toBeCloseTo(3.42, 6);
  });

  it("does not divide by a session that caught nothing", () => {
    expect(headroom([0, 0], 1.14)).toBe(1);
    expect(seriesPoints([0, 0], headroom([0, 0], 1.14)).every((p) => p.y === 132)).toBe(true);
  });

  it("writes the path the design asks for", () => {
    const points = seriesPoints([5, 10], 10);
    expect(linePath(points)).toBe("M124.5,78.0 L 305.5,24.0");
    expect(areaPath(points)).toBe("M124.5,78.0 L 305.5,24.0 L305.5,132 L124.5,132 Z");
  });

  it("has nothing to draw for an empty series", () => {
    expect(linePath([])).toBe("");
    expect(areaPath([])).toBe("");
  });

  it("sits a bar on the baseline, not floating above it", () => {
    const [bar] = seriesBars([4], 4);
    expect((bar?.y ?? 0) + (bar?.height ?? 0)).toBe(SERIES.baseline);
  });
});

describe("the speed axis", () => {
  it("is fixed at 0 to 40 km/h across the full box", () => {
    expect(speedX(0)).toBe(0);
    expect(speedX(20)).toBe(200);
    expect(speedX(SPEED.max)).toBe(SPEED.width);
  });
});

describe("the measured distribution", () => {
  it("places L6's own bins on the fixed axis", () => {
    const { bars, overflow } = histogram([0, 5, 10], [2, 4]);
    expect(overflow).toBeNull();
    expect(bars).toHaveLength(2);
    expect(bars[0]).toEqual({ x: 1, y: 64, width: 178, height: 54 });
    expect(bars[1]).toEqual({ x: 181, y: 10, width: 178, height: 108 });
  });

  it("collects everything past 40 km/h into one bar that says how much it holds", () => {
    const { bars, overflow } = histogram([0, 11.5, 12], [5, 3]);
    expect(bars).toHaveLength(1);
    expect(overflow?.seconds).toBe(3);
    expect(overflow?.x).toBe(speedX(SPEED.max) - 17);
    expect(overflow?.height).toBeCloseTo(64.8, 6);
  });

  it("clamps a bin that straddles the end of the axis", () => {
    const { bars } = histogram([0, 11.5], [5]);
    expect((bars[0]?.x ?? 0) + (bars[0]?.width ?? 0)).toBeLessThanOrEqual(SPEED.width);
  });

  it("draws a flat floor rather than dividing by an empty session", () => {
    const { bars } = histogram([0, 5], [0]);
    expect(bars[0]?.height).toBe(0);
  });
});

describe("a wave profile thumbnail", () => {
  // Synthetic degrees, never a real session's: this repo is public.
  const leg = (n: number, observed: boolean, lat = 0) =>
    Array.from({ length: n }, (_, i) => ({ t: i, observed, lat, lon: i * 0.0001 }));

  it("has nothing to draw for a wave with no samples", () => {
    expect(miniTrack([])).toEqual({ paths: [], start: null });
  });

  it("fills the box it is given, inset and centred", () => {
    const { paths, start } = miniTrack(leg(5, true));
    expect(paths).toHaveLength(1);
    expect(start).toEqual({ x: MINI.inset, y: MINI.height / 2 });
    // A due-east ride spans the full inner width and nothing vertically.
    expect(paths[0]?.d).toBe("M4.0,15.0 L 17.0,15.0 L 30.0,15.0 L 43.0,15.0 L 56.0,15.0");
  });

  it("keeps the measured and the estimated apart", () => {
    const rows = [...leg(3, true), ...leg(3, false).map((r) => ({ ...r, t: r.t + 3 }))];
    const { paths } = miniTrack(rows);
    expect(paths.map((p) => p.series)).toEqual(["measured", "estimated"]);
  });

  it("bridges the two so they meet rather than leaving a gap", () => {
    const rows = [...leg(3, true), ...leg(3, false).map((r) => ({ ...r, t: r.t + 3 }))];
    const { paths } = miniTrack(rows);
    const lastMeasured = paths[0]?.d.split(" L ").at(-1);
    const firstEstimated = paths[1]?.d.slice(1).split(" L ")[0];
    expect(firstEstimated).toBe(lastMeasured);
  });

  it("scales each wave to itself, so a short ride is not drawn as a small one", () => {
    const short = miniTrack(leg(3, true));
    const long = miniTrack(leg(40, true));
    expect(short.paths[0]?.d.split(" L ").at(-1)).toBe(long.paths[0]?.d.split(" L ").at(-1));
  });

  it("still draws a wave the watch saw at a single point", () => {
    const { paths, start } = miniTrack([{ t: 0, observed: true, lat: 0, lon: 0 }]);
    expect(start).toEqual({ x: MINI.width / 2, y: MINI.height / 2 });
    expect(paths[0]?.d).toBe("M30.0,15.0");
  });
});
