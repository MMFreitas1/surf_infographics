/**
 * Runtime contracts at the API boundary.
 *
 * These mirror `api/src/surf/models.py`. If one side changes, the other must change in
 * the same PR — the schema test is what catches drift.
 *
 * Note that `lat`, `lon` and `speedMs` are nullable by design: roughly half of a real
 * surf session has no GPS fix. See docs/data-findings.md.
 */
import { z } from "zod";

export const Fidelity = z.enum(["fit", "tcx", "gpx"]);
export type Fidelity = z.infer<typeof Fidelity>;

export const BlindCause = z.enum(["no_fix", "missing_record", "unknown"]);
export type BlindCause = z.infer<typeof BlindCause>;

export const LabelSource = z.enum(["human", "ciq_bootstrap"]);
export type LabelSource = z.infer<typeof LabelSource>;

export const RideDirection = z.enum(["left", "right", "straight", "unknown"]);
export type RideDirection = z.infer<typeof RideDirection>;

export const Sample = z.object({
  t: z.number(),
  lat: z.number().min(-90).max(90).nullable().default(null),
  lon: z.number().min(-180).max(180).nullable().default(null),
  speed_ms: z.number().min(0).nullable().default(null),
  hr_bpm: z.number().int().min(20).max(250).nullable().default(null),
  temp_c: z.number().nullable().default(null),
  distance_m: z.number().min(0).nullable().default(null),
  confidence: z.number().min(0).max(1).default(1),
  has_position: z.boolean(),
});
export type Sample = z.infer<typeof Sample>;

export const BlindWindow = z.object({
  t_start: z.number(),
  t_end: z.number(),
  cause: BlindCause.default("unknown"),
  duration_s: z.number(),
});
export type BlindWindow = z.infer<typeof BlindWindow>;

export const WaveCandidate = z.object({
  t_start: z.number(),
  t_end: z.number(),
  features: z.record(z.string(), z.number()).default({}),
  score: z.number().min(0).max(1).nullable().default(null),
  direction: RideDirection.default("unknown"),
  position_coverage: z.number().min(0).max(1).default(0),
  duration_s: z.number(),
});
export type WaveCandidate = z.infer<typeof WaveCandidate>;

export const Activity = z.object({
  activity_id: z.string(),
  sport: z.string(),
  start_time: z.number(),
  fidelity: Fidelity,
  samples: z.array(Sample).default([]),
  blind_windows: z.array(BlindWindow).default([]),
  device: z.string().default(""),
  source_file: z.string().default(""),
  duration_s: z.number(),
  position_coverage: z.number(),
  blind_seconds: z.number(),
});
export type Activity = z.infer<typeof Activity>;

/**
 * An activity without its samples, as `GET /activities` returns them.
 *
 * A projection, not a second shape: every field means what it means on `Activity`. The
 * list endpoint must not ship thousands of samples per row, and an `Activity` with an
 * empty `samples` array would read as "this session recorded nothing".
 */
export const ActivitySummary = z.object({
  activity_id: z.string(),
  sport: z.string(),
  start_time: z.number(),
  fidelity: Fidelity,
  device: z.string().default(""),
  source_file: z.string().default(""),
  sample_count: z.number().int().min(0),
  duration_s: z.number(),
  position_coverage: z.number().min(0).max(1),
  blind_seconds: z.number().min(0),
  ingested_at: z.number(),
});
export type ActivitySummary = z.infer<typeof ActivitySummary>;

export const Health = z.object({
  status: z.literal("ok"),
  version: z.string(),
});
export type Health = z.infer<typeof Health>;

/**
 * How a wave candidate should be presented. The three states must stay distinguishable
 * all the way to the pixels — see the honesty rules in CLAUDE.md.
 */
export type Certainty = "detected" | "uncertain" | "blind";

export function certaintyOf(
  candidate: Pick<WaveCandidate, "score" | "position_coverage">,
): Certainty {
  if (candidate.position_coverage === 0) return "blind";
  if (candidate.score === null) return "uncertain";
  if (candidate.score >= 0.85) return "detected";
  if (candidate.score < 0.15) return "detected";
  return "uncertain";
}
