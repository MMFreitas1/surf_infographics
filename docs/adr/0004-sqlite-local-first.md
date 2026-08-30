# ADR-0004: SQLite plus a Parquet stage cache

**Status:** accepted · 2026-08-28

## Context
Single user, roughly 200 sessions a year at ~4000 samples each. That is a few million rows
total — small. The app must run fully offline on localhost with no operational burden.

## Decision
SQLite for metadata, wave events and labels. Parquet files under `data/cache/` for cached
pipeline stage outputs, keyed by `sha256(input_hash, params, code_version)`.

## Consequences
- Zero-ops, single file to back up, trivially inspectable.
- Rejected Postgres (needs a server for no benefit at this scale) and DuckDB (Parquet already
  covers the columnar need without a second engine).
- If this ever becomes multi-user, this ADR is the first thing to revisit.
