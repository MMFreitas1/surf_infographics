"""Local-first persistence: SQLite metadata plus Parquet stage payloads (ADR-0004)."""

from surf.store.repo import (
    INGEST_CODE_VERSION,
    SAMPLES_STAGE,
    SCHEMA_VERSION,
    ActivityRepository,
    StoreError,
    samples_from_parquet,
    samples_to_parquet,
)

__all__ = [
    "INGEST_CODE_VERSION",
    "SAMPLES_STAGE",
    "SCHEMA_VERSION",
    "ActivityRepository",
    "StoreError",
    "samples_from_parquet",
    "samples_to_parquet",
]
