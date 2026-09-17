# ADR-0014: A rejected fix is demoted to blind, and the speed field is a second channel

**Status:** accepted · 2026-09-17

## Context
The reference session contains numbers no surfer produces. The raw position track jumps
**109 m/s** (392 km/h) between adjacent fixes, and the recorded `speed_ms` field peaks at
**74.8 km/h** against a surfer's 25–35. Phase 5 exists because nothing downstream is worth
drawing until those are gone: Phase 7 reports a top speed per wave, and it would report that.

Two measurements taken while planning changed what the cleaner had to be.

**The position rules do not fix the headline number.** L1 already gates fixes at
`max_speed_ms = 12.0` by inflating their measurement variance, so rejecting them upstream
moves the smoothed top speed from 11.55 to 11.56 m/s — nothing. PLAN.md assumed the
impossible fixes were what produced the 74.8 km/h reading. They are not.

**The 74.8 km/h lives in a different channel.** It sits in a cluster at +3195…3262 s where
the positions say the surfer was moving at ~1 m/s and heart rate reads ~110 — someone walking
up the beach with a watch reacquiring GPS. No amount of position differencing reaches it.

## Decision

### Rejection is a demotion, never a deletion
A refused fix keeps its row. `lat`, `lon` and `speed_ms` become `None`, `confidence` becomes
0.0, and the blind windows are redrawn — so the second becomes indistinguishable from one
where the wrist was underwater, which is what it always was. L1 then estimates it like any
other gap, and `observed=False` keeps the measured/estimated line intact (ADR-0010).

Deleting the row was rejected: it shortens the session and shifts every later second.
Silently keeping the fix and merely down-weighting it was rejected too — that is what L1
already does, and it leaves coverage counting seconds we do not believe.

### Two channels, and therefore two effects
| Effect | Rules | What it does |
|---|---|---|
| `demoted_to_blind` | `implied_speed`, `implied_acceleration`, `jump_and_return` | Position and speed cleared. Coverage falls |
| `speed_dropped` | `speed_vs_odometer`, `speed_vs_position`, `speed_impossible` | Only the speed cleared. Coverage unchanged |

A single effect was rejected in both directions. Demoting a whole fix over a bad speed
reading reports "we could not see" about a second the watch saw perfectly well; leaving a
contradicted speed in place leaves the artefact that started this. Coverage has to keep
meaning what it says in *both* directions, so the effect is recorded per rejection.

### The odometer is the strongest evidence we have
`distance_m` is present for all 3790 samples of the reference session — it survives the blind
half that positions do not. Speed field and odometer are the same device measuring the same
quantity twice, so a flat disagreement between them is physics rather than a tuned threshold.
On the session's one genuine fast ride the odometer reads 0.51–0.81 of the speed field;
across the artefact cluster it reads 0.00–0.18. The ratio threshold sits in that gap.
`speed_vs_position` is the fallback where no odometer exists (GPX), and it is weaker: it can
only fire where fixes bracket the second closely enough to contradict it.

### The removal ceiling is looser than L1's gate
L0.5 rejects implied speed above **18 m/s** while L1 gates at **12 m/s**, and the difference
is deliberate. L1 *softens* a suspect fix, so a false positive costs almost nothing. This
stage *removes* it, so a false positive destroys a measurement. Swept across five seeded
synthetic sessions where the true rides are known, 12 m/s demotes 3–7 genuine ride seconds
per session; 18 m/s demotes none on four of the five.

## Consequences

- **The phase's Done-when is not met by Pass 1 alone.** Top speed falls 74.8 → 74.5 km/h.
  Readings above 54 km/h fall 12 → 3, and the second-highest falls 74.7 → 54.1, but the
  single highest survives because all three channels agree it was fast. It is one second
  inside a stretch that is not surfing at all, and refusing a *stretch* is Pass 2's job. We
  ship Pass 1 saying that plainly rather than inventing a per-fix rule that would reach it.
- **`GET /activities/{id}` keeps serving the raw recording.** The store holds what the device
  wrote; the cleaner is a stage. `GET /activities/{id}/cleaning` is what reconciles the two,
  and the track's `observed` is what the rest of the app should believe.
- **Rejections carry no coordinates.** `t`, reason, effect, value, limit — nothing else. This
  repo is public and these records reach committed goldens; a lat/lon here would be a GPS
  trace in git. Pinned by a test on both sides of the contract.
- **Coverage on the reference session drops 48.79% → 48.13%.** That is the honest number and
  everything downstream should quote it.
- **`implied_acceleration` fires once and `jump_and_return` never** on the only real session
  we have. They are canonical artefact signatures and they ship, but their only meaningful
  coverage is an injected-artefact test. Nobody should read their presence as evidence they
  are earning their place until a second real session says so.
- **Every threshold is in the cache key**, so arguing with a number is a re-key and not a
  re-ingest — and invalidation travels down the chain, so no chart can be drawn from a track
  cleaned under a rule the confidence card no longer reports.
- Phase 6's shore-and-peaks decision, which PLAN.md reserved this number for, becomes
  **ADR-0015**.
