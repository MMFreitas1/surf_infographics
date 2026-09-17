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

- ~~**The phase's Done-when is not met by Pass 1 alone.** Top speed falls 74.8 → 74.5 km/h…
  refusing a *stretch* is Pass 2's job.~~ **Superseded 2026-09-17 — see the amendment below.**
  Top speed now falls **74.8 → 54.1 km/h** and readings above 54 km/h fall **12 → 2**.
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

---

## Amendment · 2026-09-17 — `speed_vs_odometer_window`

**What the original decision missed.** `speed_vs_odometer` compares a reading to the odometer
step for *that one second*. At t+3248 the odometer itself jumped 11.38 m in that second, so
the two instruments corroborated each other and the 74.5 km/h reading was cleared. Two
channels agreeing is only evidence when they fail independently, and here they did not.

**The fix is containment, not another threshold.** A reading of *v* m/s asserts *v* metres of
travel inside one second, and that second lies inside any window containing it — so the
window cannot have covered less ground than the second claims. Over ±5 s the odometer at
t+3248 advanced **16.5 m** against the 20.7 m asserted. That is arithmetic; there is no ratio
to tune, and ±3 s, ±5 s and ±8 s all convict the same single reading.

It is surgical on the one real session we have: **exactly one** new rejection, and every
second of the genuine ride at t+1792…1798 is spared, where the odometer covers 82.5 m in
±5 s against 15.03 m/s asserted.

**A dead odometer is no longer treated as a witness.** A counter that never advances says
"you did not move" about every second of a session, and the original code would have believed
it and dropped every fast reading. Both odometer rules now require the counter to have moved
at least once, and fall back to the positions when it has not.

**What is left, and why it stays.** The top speed is now 54.1 km/h — still above a surfer's
25–35, and still not something cleaning may touch. It is a **real ride** where the odometer
corroborates ~9.7 m/s while the speed field reports 15.03: the watch over-reads by a
consistent ~1.6× across that whole ride. Nothing contradicts the reading, so nothing here
removes it. Which channel a wave metric should quote is a **calibration** question for Phase 7,
and recording it as such is the honest end of this decision rather than tuning a rule until
the number looks better.
