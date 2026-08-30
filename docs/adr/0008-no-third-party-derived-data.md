# ADR-0008: The pipeline consumes no third-party derived data

**Status:** accepted · 2026-08-29

## Context
The reference FIT carries developer fields written by a Connect IQ surf app: per-second
`waveplot`/`waveplot2`, and a session summary of wave count, lefts, rights and thresholds.
Phase 0 initially imported those 16 segments as weak bootstrap labels.

That was the wrong call. **Those values are derived from the same GPS stream we already
hold.** They therefore carry no information we cannot compute ourselves, while carrying
that app's errors — which are demonstrable: three of its detections have no GPS position
at all, and several rest on a speed reading latched while the fix was lost. Seeding our
ground truth with them would import their failure modes into ours.

## Decision
The pipeline consumes **only** first-party recorded signal: timestamps, position, speed,
heart rate, distance, temperature and device metadata.

- Developer fields are not read by `ingest/`. Decoding them stays in `research/` as a spike.
- No bootstrap labels. Ground truth comes from human labelling in Phase 4.
- Until then the eval gate runs on `surf.synthetic` — a seeded, physically plausible
  session whose wave intervals are known exactly, containing no personal location data.

The findings *about* that app remain in `docs/data-findings.md` as motivation for the
project. Documenting a competitor's failure is not the same as depending on its output.

## Consequences
- Phase 4 labelling starts from raw signal, which is slower than correcting a prior guess
  but does not inherit anyone else's mistakes.
- The eval gate works from day one via the synthetic fixture, before any human label exists.
- Reverse-engineering their fields remains available if a specific question ever needs it,
  but that would be research, not a runtime dependency.
