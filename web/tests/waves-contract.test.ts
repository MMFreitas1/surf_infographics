import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { SessionVerdict, WaveVerdict } from "@/lib/schema";

/**
 * The other half of the wave-verdict contract. `api/tests/test_contract_parity.py` reads this
 * same fixture and holds the Pydantic models to it; here it is held to the Zod schemas.
 *
 * What is being defended is not only the field list. `/waves` is the one route that answers
 * rather than proposes, and the promises that come with a count -- an unresolved candidate is
 * never a wave, coverage survives onto every verdict, no model is named unless one ran -- are
 * exactly the ones a screen would quietly break.
 */
const contractPath = new URL("../../evals/goldens/waves_contract_v1.json", import.meta.url)
  .pathname;
const contract = JSON.parse(readFileSync(contractPath, "utf8"));

describe("wave verdict contract", () => {
  it("parses as a SessionVerdict", () => {
    const verdict = SessionVerdict.parse(contract);
    expect(verdict.wave_count).toBe(2);
    expect(verdict.proposed_count).toBe(4);
  });

  it("carries exactly the fields the SessionVerdict schema declares", () => {
    expect(Object.keys(contract).sort()).toEqual(Object.keys(SessionVerdict.shape).sort());
  });

  it("carries exactly the fields the WaveVerdict schema declares", () => {
    const expected = Object.keys(WaveVerdict.shape).sort();
    for (const row of contract.verdicts) {
      expect(Object.keys(row).sort()).toEqual(expected);
    }
  });

  it("covers every tier that can decide a candidate", () => {
    const tiers = new Set(contract.verdicts.map((v: { decided_by: string }) => v.decided_by));
    expect(tiers).toContain("rule");
    expect(tiers).toContain("unresolved");
  });

  it("never counts an unresolved candidate as a wave", () => {
    const verdict = SessionVerdict.parse(contract);
    for (const row of verdict.verdicts) {
      if (row.decided_by === "unresolved") expect(row.is_wave).toBe(false);
    }
    expect(verdict.wave_count).toBe(verdict.verdicts.filter((v) => v.is_wave).length);
  });

  it("keeps a wave the watch never saw, with its coverage intact", () => {
    const verdict = SessionVerdict.parse(contract);
    const blind = verdict.verdicts.filter((v) => v.position_coverage === 0);

    expect(blind.length).toBeGreaterThan(0);
    expect(blind.some((v) => v.is_wave)).toBe(true);
  });

  it("gives every verdict a reason a person can argue with", () => {
    for (const row of SessionVerdict.parse(contract).verdicts) {
      expect(row.reason.length).toBeGreaterThan(0);
    }
  });

  it("names no model when none decided anything", () => {
    const verdict = SessionVerdict.parse(contract);
    expect(verdict.model).toBe("");
    expect(verdict.adjudicated).toBe(0);
  });

  it("rejects a strength outside its scale", () => {
    expect(() => WaveVerdict.parse({ ...contract.verdicts[0], strength: 1.4 })).toThrow();
  });

  it("rejects a tier it does not know", () => {
    expect(() => WaveVerdict.parse({ ...contract.verdicts[0], decided_by: "vibes" })).toThrow();
  });
});
