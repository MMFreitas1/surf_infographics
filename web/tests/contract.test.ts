import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  Activity,
  ActivitySummary,
  AuditReport,
  AuditSource,
  BlindWindow,
  CleanReport,
  NotSurfingReason,
  NotSurfingWindow,
  RejectedFix,
  RejectionReason,
  Sample,
  SessionWindow,
} from "@/lib/schema";

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

/**
 * The Phase 5 cleaning contract. Same two-sided check: `api/tests/test_contract_parity.py`
 * holds this fixture to the Pydantic models, this holds it to the Zod schemas, and a field
 * added on one side only fails in exactly one of the two files.
 */
const cleaningPath = new URL("../../evals/goldens/cleaning_contract_v1.json", import.meta.url)
  .pathname;
const cleaning = JSON.parse(readFileSync(cleaningPath, "utf8"));

describe("cleaning contract", () => {
  it("parses as a CleanReport", () => {
    const report = CleanReport.parse(cleaning.report);
    expect(report.rejections).toHaveLength(RejectionReason.options.length);
    expect(report.enabled).toBe(true);
  });

  it("carries exactly the fields the CleanReport schema declares", () => {
    expect(Object.keys(cleaning.report).sort()).toEqual(Object.keys(CleanReport.shape).sort());
  });

  it("carries exactly the fields the RejectedFix schema declares", () => {
    const expected = Object.keys(RejectedFix.shape).sort();
    for (const rejected of cleaning.report.rejections) {
      expect(Object.keys(rejected).sort()).toEqual(expected);
    }
  });

  it("never carries a coordinate, because this repo is public", () => {
    for (const rejected of cleaning.report.rejections) {
      expect(rejected).not.toHaveProperty("lat");
      expect(rejected).not.toHaveProperty("lon");
    }
  });

  it("knows every reason the API can send", () => {
    const sent = new Set(cleaning.report.rejections.map((r: { reason: string }) => r.reason));
    expect([...sent].sort()).toEqual([...RejectionReason.options].sort());
  });

  it("only lets a demotion move coverage", () => {
    const report = CleanReport.parse(cleaning.report);
    const demoted = report.rejections.filter((r) => r.effect === "demoted_to_blind").length;
    expect(report.fixes_before - report.fixes_after).toBe(demoted);
    expect(report.coverage_after).toBeLessThan(report.coverage_before);
  });

  it("still reports the counts when the cleaner was switched off", () => {
    const disabled = CleanReport.parse(cleaning.disabled);
    expect(disabled.enabled).toBe(false);
    expect(disabled.rejections).toEqual([]);
    expect(disabled.coverage_after).toBe(disabled.coverage_before);
  });
});

/**
 * The Phase 5 audit contract. Same two-sided check as above: adding a field on one side
 * only fails in exactly one of these two files.
 */
const auditPath = new URL("../../evals/goldens/audit_contract_v1.json", import.meta.url).pathname;
const audit = JSON.parse(readFileSync(auditPath, "utf8"));

describe("audit contract", () => {
  it("parses as an AuditReport", () => {
    const report = AuditReport.parse(audit.report);
    expect(report.not_surfing).toHaveLength(NotSurfingReason.options.length);
    expect(report.decided).toBe(true);
  });

  it("carries exactly the fields the AuditReport schema declares", () => {
    expect(Object.keys(audit.report).sort()).toEqual(Object.keys(AuditReport.shape).sort());
  });

  it("carries exactly the fields the SessionWindow and NotSurfingWindow schemas declare", () => {
    const windowFields = Object.keys(SessionWindow.shape).sort();
    for (const window of audit.report.windows) {
      expect(Object.keys(window).sort()).toEqual(windowFields);
    }
    const excludedFields = Object.keys(NotSurfingWindow.shape).sort();
    for (const excluded of audit.report.not_surfing) {
      expect(Object.keys(excluded).sort()).toEqual(excludedFields);
    }
  });

  it("never carries a coordinate in the digest", () => {
    for (const window of audit.report.windows) {
      expect(window).not.toHaveProperty("lat");
      expect(window).not.toHaveProperty("lon");
      expect(window).not.toHaveProperty("bearing");
    }
  });

  it("knows every reason and every source the API can send", () => {
    const reasons = new Set(audit.report.not_surfing.map((w: { reason: string }) => w.reason));
    const sources = new Set(audit.report.not_surfing.map((w: { source: string }) => w.source));
    expect([...reasons].sort()).toEqual([...NotSurfingReason.options].sort());
    expect([...sources].sort()).toEqual([...AuditSource.options].sort());
  });

  it("keeps a window with no fix null rather than zero", () => {
    const report = AuditReport.parse(audit.report);
    const blind = report.windows.find((w) => w.coverage === 0);
    expect(blind?.speed_max_ms).toBeNull();
    expect(blind?.odometer_rate_ms).toBeNull();
  });

  it("separates the recording from the session", () => {
    const report = AuditReport.parse(audit.report);
    expect(report.surfing_t_start).toBeGreaterThan(report.t_start);
    expect(report.surfing_t_end).toBeLessThan(report.t_end);
    expect(report.surfing_s).toBeLessThan(report.t_end - report.t_start);
  });

  it("says plainly when it could not tell", () => {
    const undecided = AuditReport.parse(audit.undecided);
    expect(undecided.decided).toBe(false);
    expect(undecided.not_surfing).toEqual([]);
    expect(undecided.excluded_s).toBe(0);
  });
});
