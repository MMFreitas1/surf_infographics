"""Activity persistence: SQLite for metadata, Parquet for samples (ADR-0004).

The split follows `docs/architecture.md`: SQLite holds what we query and join --
activities, blind windows, and labels once Phase 4 exists -- while a session's samples are
the L0 stage output and go through the same content-addressed `StageCache` as every later
stage. So the samples of an ingest are cached exactly like the output of a smoother, and
the activities row just remembers the key.

What the store deliberately does *not* own is the identity of the stage that produced that
payload. Its name, code version, params and serialisation live with the stage itself, in
`surf.ingest.stage`; the caller runs the stage and hands `save` the key its output landed
under. A store that also defined what L0 *is* would have had every later stage copying the
pattern instead of inheriting it.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from surf.ingest import stage as l0
from surf.models import Activity, ActivitySummary, BlindCause, BlindWindow, Fidelity
from surf.pipeline import StageCache

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    """The store is in a state we will not paper over."""


class ActivityRepository:
    """Reads and writes activities. Owns one SQLite connection for the app's lifetime."""

    def __init__(self, db_path: Path, cache: StageCache) -> None:
        self._cache = cache
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # FastAPI runs sync endpoints on a threadpool, so the connection is shared across
        # threads and every write is serialised by the lock below.
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        with self._db:
            self._db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            if self._db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
                self._db.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
                )

    def close(self) -> None:
        """Release the connection."""
        self._db.close()

    @property
    def schema_version(self) -> int:
        """The version stamped in the database file."""
        return int(self._db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0])

    def id_for_digest(self, source_sha256: str) -> str | None:
        """The activity already ingested from these exact bytes, if there is one."""
        row = self._db.execute(
            "SELECT activity_id FROM activities WHERE source_sha256 = ?", (source_sha256,)
        ).fetchone()
        return None if row is None else str(row["activity_id"])

    def save(
        self, activity: Activity, *, source_sha256: str, samples_key: str, ingested_at: float
    ) -> str:
        """Index an activity whose L0 payload is already cached. Returns the activity id.

        ``samples_key`` comes from running the ingest stage: the payload is written by the
        pipeline, and this row records where it went.
        """
        positioned = sum(1 for sample in activity.samples if sample.has_position)
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO activities (
                    activity_id, source_sha256, sport, start_time, fidelity, device,
                    source_file, sample_count, positioned_count, duration_s, blind_seconds,
                    samples_key, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity.activity_id,
                    source_sha256,
                    activity.sport,
                    activity.start_time,
                    activity.fidelity.value,
                    activity.device,
                    activity.source_file,
                    len(activity.samples),
                    positioned,
                    activity.duration_s,
                    activity.blind_seconds,
                    samples_key,
                    ingested_at,
                ),
            )
            # REPLACE above cascades the old windows away; insert the current set.
            self._db.execute(
                "DELETE FROM blind_windows WHERE activity_id = ?", (activity.activity_id,)
            )
            self._db.executemany(
                "INSERT INTO blind_windows (activity_id, seq, t_start, t_end, cause) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (activity.activity_id, seq, window.t_start, window.t_end, window.cause.value)
                    for seq, window in enumerate(activity.blind_windows)
                ],
            )
        return activity.activity_id

    def _blind_windows(self, activity_id: str) -> list[BlindWindow]:
        rows = self._db.execute(
            "SELECT t_start, t_end, cause FROM blind_windows WHERE activity_id = ? ORDER BY seq",
            (activity_id,),
        ).fetchall()
        return [
            BlindWindow(t_start=row["t_start"], t_end=row["t_end"], cause=BlindCause(row["cause"]))
            for row in rows
        ]

    def get(self, activity_id: str) -> Activity | None:
        """The full activity, samples included, or None when it is not stored."""
        row = self._db.execute(
            "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if row is None:
            return None
        payload = self._cache.get(l0.NAME, row["samples_key"])
        if payload is None:
            # Metadata without its samples. Returning an empty session would report a
            # cache miss as a session with nothing in it.
            msg = f"samples for activity {activity_id} are missing from the stage cache"
            raise StoreError(msg)
        return Activity(
            activity_id=row["activity_id"],
            sport=row["sport"],
            start_time=row["start_time"],
            fidelity=Fidelity(row["fidelity"]),
            samples=l0.samples_from_parquet(payload),
            blind_windows=self._blind_windows(activity_id),
            device=row["device"],
            source_file=row["source_file"],
        )

    def summaries(self, limit: int = 100) -> list[ActivitySummary]:
        """Stored activities, newest session first, without their samples."""
        rows = self._db.execute(
            "SELECT * FROM activities ORDER BY start_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_summary_of(row) for row in rows]

    def delete(self, activity_id: str) -> bool:
        """Remove an activity and its windows. The cached samples stay: it is a cache."""
        with self._lock, self._db:
            cursor = self._db.execute(
                "DELETE FROM activities WHERE activity_id = ?", (activity_id,)
            )
        return cursor.rowcount > 0


def _summary_of(row: Any) -> ActivitySummary:
    """Build a summary straight from the stored columns, with no samples read."""
    count = int(row["sample_count"])
    return ActivitySummary(
        activity_id=row["activity_id"],
        sport=row["sport"],
        start_time=row["start_time"],
        fidelity=Fidelity(row["fidelity"]),
        device=row["device"],
        source_file=row["source_file"],
        sample_count=count,
        duration_s=row["duration_s"],
        position_coverage=(int(row["positioned_count"]) / count) if count else 0.0,
        blind_seconds=row["blind_seconds"],
        ingested_at=row["ingested_at"],
    )
