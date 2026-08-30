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

export const LabelSource = z.enum(["human", "human_assisted", "ciq_bootstrap"]);
export type LabelSource = z.infer<typeof LabelSource>;

export const PassKind = z.enum(["blind", "assisted"]);
export type PassKind = z.infer<typeof PassKind>;

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

/**
 * One second of the L1 track: an estimate, never a measurement.
 *
 * `lat`/`lon` are non-null here — unlike on `Sample` — because an estimate exists even
 * where no fix did. `observed` is the only thing separating the two, so anything that
 * draws this has to draw the two states differently (ADR-0010).
 */
export const SmoothedSample = z.object({
  t: z.number(),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180),
  vx_ms: z.number(),
  vy_ms: z.number(),
  position_sigma_m: z.number().min(0),
  confidence: z.number().min(0).max(1),
  observed: z.boolean(),
  speed_ms: z.number(),
});
export type SmoothedSample = z.infer<typeof SmoothedSample>;

/** The same second rotated into the session's shore frame. A rotation adds no certainty. */
export const FramedSample = z.object({
  t: z.number(),
  cross_shore_m: z.number(),
  along_shore_m: z.number(),
  v_cross_ms: z.number(),
  v_along_ms: z.number(),
  confidence: z.number().min(0).max(1),
  observed: z.boolean(),
  speed_ms: z.number(),
});
export type FramedSample = z.infer<typeof FramedSample>;

/**
 * Where the shore is, for one session — and how much that estimate is worth.
 *
 * `reliable === false` means "we cannot tell where the shore is". That is an answer, and
 * the UI must render it as one rather than drawing a confident wrong bearing (ADR-0011).
 */
export const SessionFrame = z.object({
  shore_bearing_deg: z.number().min(0).max(360),
  coherence: z.number().min(0).max(1),
  reliable: z.boolean(),
  contributing_seconds: z.number().int().min(0),
  effective_seconds: z.number().min(0),
  origin_lat: z.number().min(-90).max(90),
  origin_lon: z.number().min(-180).max(180),
});
export type SessionFrame = z.infer<typeof SessionFrame>;

/** What the labeling UI draws a session from. The two tracks are index-aligned. */
export const SessionTrack = z.object({
  frame: SessionFrame,
  smoothed: z.array(SmoothedSample),
  framed: z.array(FramedSample),
});
export type SessionTrack = z.infer<typeof SessionTrack>;

/** L3's proposals, with the frame they were measured against. */
export const SessionCandidates = z.object({
  frame: SessionFrame,
  candidates: z.array(WaveCandidate),
});
export type SessionCandidates = z.infer<typeof SessionCandidates>;

/**
 * A label as the store holds it. Append-only: a correction is a new row naming the one it
 * replaces, and the replaced row stays exactly where it was (ADR-0006).
 */
export const StoredLabel = z.object({
  t_start: z.number(),
  t_end: z.number(),
  is_wave: z.boolean(),
  source: LabelSource.default("human"),
  verified: z.boolean().default(false),
  direction: RideDirection.default("unknown"),
  note: z.string().default(""),
  counts_as_truth: z.boolean(),
  label_id: z.string(),
  activity_id: z.string(),
  created_at: z.number(),
  supersedes: z.string().nullable().default(null),
});
export type StoredLabel = z.infer<typeof StoredLabel>;

/**
 * A completed sweep of one session. The blind pass is what unlocks the assisted one, so
 * the UI reads this rather than guessing from a label count (ADR-0012).
 */
export const LabelPass = z.object({
  activity_id: z.string(),
  kind: PassKind,
  completed_at: z.number(),
  label_count: z.number().int().min(0),
});
export type LabelPass = z.infer<typeof LabelPass>;

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
