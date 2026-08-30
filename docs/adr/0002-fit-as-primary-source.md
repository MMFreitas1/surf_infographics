# ADR-0002: FIT is the primary source; GPX/TCX are degraded tiers

**Status:** accepted · 2026-08-28 · *the bootstrap-label rationale below was reversed by [ADR-0008](0008-no-third-party-derived-data.md)*

## Context
Garmin Connect's GPX export omits every record that lacked a GPS fix. Measured on the reference
session: FIT has 3790 records, the GPX has 1849. The GPX therefore discards 51% of the session,
including heart rate and cumulative distance that were recorded perfectly well.

The FIT additionally carries the Connect IQ app's per-second wave fields (`waveplot`,
`waveplot2`) and session summary (`wavenum`, lefts/rights, detector thresholds).

> **Superseded in part.** At the time this was written those fields were intended as bootstrap
> labels. ADR-0008 reversed that: they are derived from the same GPS stream we already hold, so
> they carry that app's errors and no information. They remain a reason FIT is richer than GPX —
> they are not a reason we read it. Ingest skips them by size without decoding (ADR-0009).

## Decision
Ingest targets FIT. GPX and TCX are supported as explicitly *degraded* tiers, tagged in the
canonical model with a `fidelity` field, and surfaced as such in the UI.

## Consequences
- We must write and maintain a FIT decoder. Developer-field *resolution* turned out to be
  unnecessary: the block is skipped by its declared size (ADR-0009).
- Sessions ingested from GPX cannot support the full metric set. The UI must not pretend otherwise.
- See `docs/data-findings.md` §1.
