# ADR-0001: Record architecture decisions

**Status:** accepted · 2026-08-28

## Context
This is a multi-phase build with several one-way doors (source format, storage, detector design).
Decisions made in one session must survive into the next without re-litigation.

## Decision
Record every load-bearing decision as a numbered ADR in `docs/adr/`. An ADR is immutable once
accepted; a reversal is a new ADR that supersedes it.

## Consequences
Cheap to write, and it makes `CLAUDE.md`'s "flag it and ask before acting" rule enforceable —
there is a specific document to point at.
