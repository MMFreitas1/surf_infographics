# ADR-0006: Labels are append-only and never written by the pipeline

**Status:** accepted · 2026-08-28

## Context
"Detects waves reliably" is an empty claim without ground truth to measure against. Ground truth
is only trustworthy if derived data can never contaminate it.

## Decision
The `labels` table is append-only and is written **exclusively** by the human labeling UI.
No pipeline stage, detector or migration may write to it. Corrections are new rows that supersede
old ones; nothing is mutated or deleted.

Bootstrap labels imported from the Connect IQ fields are stored with `source='ciq_bootstrap'` and
`verified=false`, and are excluded from every evaluation metric until a human confirms them.

## Consequences
- Evaluation numbers mean what they say.
- Full audit trail of how judgment changed over time.
- Slightly more storage and a superseding query. Both are irrelevant at this scale.
