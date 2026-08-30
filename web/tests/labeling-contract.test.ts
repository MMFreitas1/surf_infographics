import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  FramedSample,
  LabelPass,
  SessionCandidates,
  SessionFrame,
  SessionTrack,
  SmoothedSample,
  StoredLabel,
  WaveCandidate,
} from "@/lib/schema";

/**
 * The Phase 4 half of the contract check. `api/tests/test_contract_parity.py` reads this
 * same fixture and holds the Pydantic models to it; here it is held to the Zod schemas.
 * A field added on one side only fails in exactly one of the two files.
 */
const contractPath = new URL("../../evals/goldens/labeling_contract_v1.json", import.meta.url)
  .pathname;
const contract = JSON.parse(readFileSync(contractPath, "utf8"));

describe("labeling contract", () => {
  it("parses as a SessionTrack", () => {
    const track = SessionTrack.parse(contract.track);
    expect(track.smoothed).toHaveLength(track.framed.length);
    expect(track.frame.reliable).toBe(true);
  });

  it("parses as a SessionCandidates", () => {
    const proposed = SessionCandidates.parse(contract.candidates);
    expect(proposed.candidates).toHaveLength(2);
  });

  it("parses as labels and passes", () => {
    expect(contract.labels.map((l: unknown) => StoredLabel.parse(l).label_id)).toHaveLength(3);
    expect(contract.passes.map((p: unknown) => LabelPass.parse(p).kind)).toEqual([
      "blind",
      "assisted",
    ]);
  });

  it("carries exactly the fields each schema declares", () => {
    const cases: [Record<string, unknown>[], Record<string, unknown>][] = [
      [contract.track.smoothed, SmoothedSample.shape],
      [contract.track.framed, FramedSample.shape],
      [contract.candidates.candidates, WaveCandidate.shape],
      [contract.labels, StoredLabel.shape],
      [contract.passes, LabelPass.shape],
      [[contract.track.frame, contract.candidates.frame], SessionFrame.shape],
      [[contract.track], SessionTrack.shape],
      [[contract.candidates], SessionCandidates.shape],
    ];
    for (const [rows, shape] of cases) {
      const expected = Object.keys(shape).sort();
      for (const row of rows) {
        expect(Object.keys(row).sort()).toEqual(expected);
      }
    }
  });

  it("keeps the measured/estimated line visible in the data the UI receives", () => {
    const track = SessionTrack.parse(contract.track);
    const seen = track.smoothed.find((s) => s.observed);
    const blind = track.smoothed.find((s) => !s.observed);

    expect(seen).toBeDefined();
    expect(blind).toBeDefined();
    // An invented second always has a position — that is the trap ADR-0010 exists for.
    expect(blind?.lat).not.toBeNull();
    // ...so the only honest way to draw it differently is these two numbers.
    expect(blind!.position_sigma_m).toBeGreaterThan(seen!.position_sigma_m);
    expect(blind!.confidence).toBeLessThan(seen!.confidence);
  });

  it("only counts unassisted human labels as truth", () => {
    const labels = contract.labels.map((l: unknown) => StoredLabel.parse(l));
    const assisted = labels.filter((l: StoredLabel) => l.source === "human_assisted");
    const human = labels.filter((l: StoredLabel) => l.source === "human");

    expect(assisted.length).toBeGreaterThan(0);
    expect(assisted.every((l: StoredLabel) => l.counts_as_truth)).toBe(false);
    expect(human.every((l: StoredLabel) => l.counts_as_truth)).toBe(true);
  });

  it("keeps a superseded label in the record rather than removing it", () => {
    const labels = contract.labels.map((l: unknown) => StoredLabel.parse(l));
    const correction = labels.find((l: StoredLabel) => l.supersedes !== null);
    expect(correction).toBeDefined();
    expect(labels.some((l: StoredLabel) => l.label_id === correction?.supersedes)).toBe(true);
  });
});
