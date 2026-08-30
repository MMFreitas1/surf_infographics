# ADR-0011: The shore bearing comes from speed-weighted velocity, and states its own reliability

**Status:** accepted · 2026-08-30

## Context
A feature has to mean the same thing at every break (ADR-0003). "Travelled shoreward at
6 m/s for five seconds" is a statement about surfing; "travelled east" is a statement about
one beach. L2 needs the axis that turns the second into the first, estimated per session.

Three candidates were on the table:

- **Principal axis of the position cloud.** Purely geometric, and it infers direction from
  the *shape* of where the surfer sat rather than from where they travelled. A session that
  drifts along the beach elongates the cloud along the wrong axis, and PCA cannot tell
  shoreward from seaward without a separate tiebreak.
- **Bimodality of the heading histogram.** Rides one way, paddle-outs back; the axis joining
  the modes is cross-shore. Robust in principle, but it needs enough waves for two modes to
  separate, which is exactly the case that turns out to be hardest.
- **Speed-weighted velocity.** Every second votes for its own heading, weighted by speed.

Phase 2 left a constraint that rules out anything simpler. Smoothed top-end speed on the
real session swings 11.55 → 10.41 → 8.50 m/s as `measurement_noise_m` goes 3.0 → 5.0 → 8.0,
and the 3.0 m default is the *synthetic's* noise, not the watch's. Any rule keyed on an
absolute speed — "a ride is faster than X m/s" — would therefore be tuned to an assumed
noise level rather than to surfing.

## Decision
The shoreward unit vector is the normalised, speed-weighted sum of per-second headings:

```
w_i = confidence_i · |v_i|^k          k = speed_exponent, default 4.0
û   = normalise( Σ w_i · v̂_i )
```

Speed enters only as a *relative* weight between seconds of the same session, so scaling
every velocity by a constant leaves `û` exactly unchanged. That is a property, not a hope,
and `test_scaling_every_velocity_leaves_the_bearing_exactly_where_it_was` pins it to 1e-9.
Weighting by `confidence` as well means an estimated second inside a blind window carries
less of a vote than a measured one, as ADR-0010 requires.

Alongshore is `û` turned 90° to the left, making the pair right-handed. Cross-shore is
positive shoreward.

### The exponent is 4.0, and it was measured

Bearing error against the synthetic's known shore (due east), by wave count:

| waves | k=2.0 | k=3.0 | **k=4.0** | k=5.0 | k=6.0 |
|---|---|---|---|---|---|
| 1 | +154.3° | +67.3° | +24.3° | +16.8° | +14.3° |
| 2 | −172.3° | −41.8° | −13.0° | −9.5° | −8.2° |
| 3 | +3.8° | −1.4° | −3.2° | −4.3° | −5.1° |
| 8 | +1.0° | +0.2° | −0.5° | −1.3° | −2.0° |

At k=2 a one- or two-wave session comes out pointing **seaward** — sustained paddling
outweighs a couple of short rides, and the cross-shore sign inverts for everything
downstream. k=4 is where that collapses; past it the error curve is flat while the estimate
leans on ever fewer seconds.

### Reliability needs two guards, not one

`coherence` — the weighted mean resultant length, `|Σ w v̂| / Σ w` — catches votes that
disagree. It is not sufficient. Measured at k=4:

| session | coherence | effective seconds | bearing error |
|---|---|---|---|
| aimless drift, no rides | 0.07 | 271 | — |
| paddling out and back, no rides | 0.01 | 379 | — |
| **drift + one 6 m/s spike** | **0.90** | **1.25** | — |
| 1 wave | 0.44 | 11.8 | +24.3° |
| 2 waves | 0.24 | 51.1 | −13.0° |
| 3–12 waves | 0.89–0.96 | 13.8–65.0 | ≤ 3.6° |

A single fast second in an otherwise aimless session scores 0.90 coherence, because nearly
all the weight sits on that one second and it agrees with itself. Coherence cannot see
concentration. The Kish effective sample size, `(Σw)² / Σw²`, can: it reads 1.25 there and
13.8 or more on every genuinely rideable session.

So a frame is `reliable` only when **`coherence ≥ 0.85` and `effective_seconds ≥ 5.0`**.
Across the sweep those two guards accept exactly the sessions inside the 5° tolerance this
stage claims, and reject every session outside it.

An unreliable frame is still returned, with its numbers and `reliable=False`. It is not an
error and not a default bearing — it is the answer "we cannot tell where the shore is",
which on a flat day is the true one.

### L2 and L3 are separate stages
`docs/architecture.md` §3 lists frame and candidates separately and they stay that way. The
frame is cached once and reused while candidate thresholds are swept, which is the point of
the stage cache; a combined stage would re-estimate the bearing on every threshold change
and make the frame impossible to inspect on its own.

## Consequences
- Every downstream cross-shore feature inherits this axis, so `reliable=False` has to be
  honoured rather than ignored. A candidate built on an unreliable frame is not a wave
  measurement, and Phase 5 must not score it as one.
- `speed_exponent`, `min_coherence` and `min_effective_seconds` are all in L2's cache key, so
  a frame can never be served under a rule it was not computed under.
- The exponent was tuned on generated motion whose dropout is state-independent. The
  standing hypothesis — that GPS *recovers* during a ride — would, if true, make ride
  seconds both faster and better observed, which this estimator would weight up twice.
  Revisit k against human labels in Phase 4 before trusting it on a marginal session.
- Nothing here reads `Activity.blind_windows`; the per-second `confidence` already carries
  that fact at finer grain.
