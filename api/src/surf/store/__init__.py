"""Local-first persistence: SQLite metadata plus Parquet stage payloads (ADR-0004)."""

from surf.store.labels import LabelRepository
from surf.store.repo import SCHEMA_VERSION, ActivityRepository, StoreError, connect

__all__ = [
    "SCHEMA_VERSION",
    "ActivityRepository",
    "LabelRepository",
    "StoreError",
    "connect",
]
