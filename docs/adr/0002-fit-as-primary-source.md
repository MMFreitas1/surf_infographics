# ADR-0002: FIT is the primary source; GPX/TCX are degraded tiers

**Status:** accepted · 2026-08-28

## Context
Garmin Connect's GPX export omits every record that lacked a GPS fix. Measured on the reference
session: FIT has 3790 records, the GPX has 1849. The GPX therefore discards 51% of the session,
including heart rate and cumulative distance that were recorded perfectly well.

The FIT additionally carries the Connect IQ app's per-second wave fields (`waveplot`,
`waveplot2`) and session summary (`wavenum`, lefts/rights, detector thresholds) — our bootstrap labels.

## Decision
Ingest targets FIT. GPX and TCX are supported as explicitly *degraded* tiers, tagged in the
canonical model with a `fidelity` field, and surfaced as such in the UI.

## Consequences
- We must write and maintain a FIT decoder, including developer-field resolution.
- Sessions ingested from GPX cannot support the full metric set. The UI must not pretend otherwise.
- See `docs/data-findings.md` §1.
