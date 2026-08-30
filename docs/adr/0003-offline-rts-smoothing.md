# ADR-0003: Offline RTS smoothing with propagated confidence

**Status:** accepted · 2026-08-28

## Context
Finite-differencing raw positions produces physically impossible speeds — 11 segments above
20 m/s and a maximum of 109 m/s (392 km/h) on the reference session. Integrating that noise
inflates total distance by 55% versus the watch's own figure.

Device-side filters run online: they only ever see the past. We are strictly offline and hold
the entire session, so we can also run backward.

## Decision
L1 runs a Kalman filter with a constant-velocity-plus-acceleration model and a physical prior
(sustained speed capped at ~12 m/s), followed by a **Rauch–Tung–Striebel backward smoother**.
Every emitted sample carries a confidence derived from the posterior covariance, GPS availability
and proximity to a blind window. Confidence propagates through every downstream stage.

L2 then rotates into a shore-relative frame (cross-shore / alongshore) estimated per session,
so features are spot-independent.

## Consequences
- Strictly more accurate than anything the watch can produce. This is the product's technical edge.
- The pipeline is offline-only. No real-time mode, ever — do not add one without a new ADR.
- Blind windows are first-class objects. We never interpolate across one and call it measured.
