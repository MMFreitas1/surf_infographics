import { describe, expect, it } from "vitest";
import { Activity, certaintyOf, Sample } from "@/lib/schema";

describe("Sample", () => {
  it("accepts a sample with no GPS fix — half a real session looks like this", () => {
    const s = Sample.parse({ t: 1, hr_bpm: 110, has_position: false });
    expect(s.lat).toBeNull();
    expect(s.hr_bpm).toBe(110);
  });

  it("rejects an impossible latitude", () => {
    expect(() => Sample.parse({ t: 1, lat: 91, lon: 0, has_position: true })).toThrow();
  });

  it("rejects a negative speed", () => {
    expect(() => Sample.parse({ t: 1, speed_ms: -1, has_position: false })).toThrow();
  });
});

describe("Activity", () => {
  it("parses a minimal payload with defaults applied", () => {
    const a = Activity.parse({
      activity_id: "24151923839",
      sport: "surfing",
      start_time: 0,
      fidelity: "fit",
      duration_s: 3789,
      position_coverage: 0.488,
      blind_seconds: 1942,
    });
    expect(a.samples).toEqual([]);
    expect(a.fidelity).toBe("fit");
    expect(a.position_coverage).toBeCloseTo(0.488);
  });

  it("rejects an unknown fidelity tier", () => {
    expect(() =>
      Activity.parse({
        activity_id: "x",
        sport: "surfing",
        start_time: 0,
        fidelity: "csv",
        duration_s: 0,
        position_coverage: 0,
        blind_seconds: 0,
      }),
    ).toThrow();
  });
});

describe("certaintyOf", () => {
  it("calls a candidate with no position coverage blind, whatever its score", () => {
    expect(certaintyOf({ score: 0.99, position_coverage: 0 })).toBe("blind");
  });

  it("calls an unscored candidate uncertain", () => {
    expect(certaintyOf({ score: null, position_coverage: 0.8 })).toBe("uncertain");
  });

  it("calls the ambiguous band uncertain", () => {
    expect(certaintyOf({ score: 0.5, position_coverage: 0.8 })).toBe("uncertain");
  });

  it("resolves confident scores at both ends", () => {
    expect(certaintyOf({ score: 0.9, position_coverage: 0.8 })).toBe("detected");
    expect(certaintyOf({ score: 0.05, position_coverage: 0.8 })).toBe("detected");
  });
});
