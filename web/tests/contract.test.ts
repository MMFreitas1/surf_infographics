import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { Activity, ActivitySummary, BlindWindow, Sample } from "@/lib/schema";

/**
 * The other half of the contract check. `api/tests/test_contract_parity.py` reads this same
 * fixture and holds the Pydantic models to it; here it is held to the Zod schemas. A field
 * added on one side only fails in one of the two files.
 */
const contractPath = new URL("../../evals/goldens/activity_contract_v1.json", import.meta.url)
  .pathname;
const contract = JSON.parse(readFileSync(contractPath, "utf8"));

describe("API contract", () => {
  it("parses as an Activity", () => {
    const activity = Activity.parse(contract.activity);
    expect(activity.activity_id).toBe("contract-v1");
    expect(activity.samples).toHaveLength(4);
  });

  it("parses as an ActivitySummary", () => {
    expect(ActivitySummary.parse(contract.summary).sample_count).toBe(4);
  });

  it("carries exactly the fields the Activity schema declares", () => {
    expect(Object.keys(contract.activity).sort()).toEqual(Object.keys(Activity.shape).sort());
  });

  it("carries exactly the fields the Sample schema declares", () => {
    const expected = Object.keys(Sample.shape).sort();
    for (const sample of contract.activity.samples) {
      expect(Object.keys(sample).sort()).toEqual(expected);
    }
  });

  it("carries exactly the fields the BlindWindow schema declares", () => {
    const expected = Object.keys(BlindWindow.shape).sort();
    for (const window of contract.activity.blind_windows) {
      expect(Object.keys(window).sort()).toEqual(expected);
    }
  });

  it("carries exactly the fields the ActivitySummary schema declares", () => {
    expect(Object.keys(contract.summary).sort()).toEqual(Object.keys(ActivitySummary.shape).sort());
  });

  it("keeps an absent measurement null, so the UI can tell it from a zero", () => {
    const activity = Activity.parse(contract.activity);
    const blind = activity.samples.find((s) => !s.has_position);
    expect(blind?.lat).toBeNull();
    expect(blind?.speed_ms).toBeNull();
    expect(activity.samples[0]?.distance_m).toBe(0);
  });
});
