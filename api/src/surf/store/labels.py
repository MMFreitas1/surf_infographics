"""Ground-truth persistence: append-only, and the only writer is a person (ADR-0006).

Every other table in this project holds something a machine produced and can reproduce.
This one does not. A label is an hour of someone's attention, it cannot be recomputed, and
once it is gone the metrics that rest on it become unverifiable. So the operations here are
deliberately fewer than a repository usually has: append, read, and record that a pass
happened. There is no update and no delete, on purpose -- a correction is a new row naming
the row it replaces, which keeps both the current answer and the history of how it changed.

The blind/assisted split (ADR-0012) is enforced here rather than in the UI, because a rule
that only the front end knows is a rule that the next caller breaks.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from surf.models import LabelPass, LabelSource, PassKind, RideDirection, StoredLabel, WaveLabel
from surf.store.repo import StoreError, connect

SOURCE_OF_PASS = {
    PassKind.BLIND: LabelSource.HUMAN,
    PassKind.ASSISTED: LabelSource.HUMAN_ASSISTED,
}
"""Which provenance a sweep produces. A blind sweep sees no proposals, so its labels are
unanchored ``human`` truth; an assisted one sees L3 and is recorded as such (ADR-0012)."""


class LabelRepository:
    """Reads and appends labels. Owns one SQLite connection for the app's lifetime."""

    def __init__(self, db_path: Path) -> None:
        self._lock = threading.Lock()
        self._db = connect(db_path)

    def close(self) -> None:
        """Release the connection."""
        self._db.close()

    def append(
        self,
        activity_id: str,
        label: WaveLabel,
        *,
        created_at: float,
        supersedes: str | None = None,
    ) -> StoredLabel:
        """Add a label. Never updates an existing row, whatever ``supersedes`` says.

        ``created_at`` is passed in rather than read from the clock so that ordering is a
        fact the caller states and a test can control.
        """
        if supersedes is not None:
            self._require_own_label(activity_id, supersedes)

        stored = StoredLabel(
            label_id=uuid.uuid4().hex,
            activity_id=activity_id,
            created_at=created_at,
            supersedes=supersedes,
            t_start=label.t_start,
            t_end=label.t_end,
            is_wave=label.is_wave,
            source=label.source,
            verified=label.verified,
            direction=label.direction,
            note=label.note,
        )
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT INTO labels (label_id, activity_id, t_start, t_end, is_wave, "
                    "source, verified, direction, note, created_at, supersedes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        stored.label_id,
                        stored.activity_id,
                        stored.t_start,
                        stored.t_end,
                        int(stored.is_wave),
                        stored.source.value,
                        int(stored.verified),
                        stored.direction.value,
                        stored.note,
                        stored.created_at,
                        stored.supersedes,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            msg = f"cannot label activity {activity_id}: it is not stored"
            raise StoreError(msg) from exc
        return stored

    def for_activity(self, activity_id: str, *, current: bool = False) -> list[StoredLabel]:
        """Labels for one session, oldest first.

        ``current`` drops the rows a later label supersedes. The full list is still the
        record of what was judged and when; this is the view of what is judged *now*.
        """
        sql = (
            "SELECT * FROM labels WHERE activity_id = ? "
            "AND (? = 0 OR label_id NOT IN "
            "    (SELECT supersedes FROM labels WHERE supersedes IS NOT NULL "
            "     AND activity_id = ?)) "
            "ORDER BY created_at, label_id"
        )
        rows = self._db.execute(sql, (activity_id, int(current), activity_id)).fetchall()
        return [_label_of(row) for row in rows]

    def complete_pass(self, activity_id: str, kind: PassKind, *, completed_at: float) -> LabelPass:
        """Record that a sweep of this session finished.

        The count is read from the labels themselves rather than taken from the caller: it
        is a fact the store already knows, and a number the client supplies is a number the
        client can get wrong.

        An assisted pass without a blind one before it is refused. That ordering is the
        whole point of ADR-0012: the unanchored set has to exist first, or there is nothing
        to measure the anchored one against.
        """
        if kind is PassKind.ASSISTED and not self.has_pass(activity_id, PassKind.BLIND):
            msg = (
                f"activity {activity_id} has no blind pass yet. The assisted pass runs "
                f"second, so that an unanchored set of labels always exists (ADR-0012)."
            )
            raise StoreError(msg)

        completed = LabelPass(
            activity_id=activity_id,
            kind=kind,
            completed_at=completed_at,
            label_count=self.count_by_source(activity_id, SOURCE_OF_PASS[kind]),
        )
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT INTO label_passes (activity_id, kind, completed_at, label_count) "
                    "VALUES (?, ?, ?, ?)",
                    (activity_id, kind.value, completed_at, completed.label_count),
                )
        except sqlite3.IntegrityError as exc:
            msg = f"cannot record a pass over activity {activity_id}: it is not stored"
            raise StoreError(msg) from exc
        return completed

    def passes_for(self, activity_id: str) -> list[LabelPass]:
        """Every completed sweep of one session, oldest first."""
        rows = self._db.execute(
            "SELECT * FROM label_passes WHERE activity_id = ? ORDER BY completed_at",
            (activity_id,),
        ).fetchall()
        return [
            LabelPass(
                activity_id=row["activity_id"],
                kind=PassKind(row["kind"]),
                completed_at=row["completed_at"],
                label_count=int(row["label_count"]),
            )
            for row in rows
        ]

    def count_by_source(self, activity_id: str, source: LabelSource) -> int:
        """How many labels of one provenance this session carries, superseded rows included."""
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM labels WHERE activity_id = ? AND source = ?",
            (activity_id, source.value),
        ).fetchone()
        return int(row["n"])

    def has_pass(self, activity_id: str, kind: PassKind) -> bool:
        """Whether a sweep of this kind has been completed on this session."""
        row = self._db.execute(
            "SELECT 1 FROM label_passes WHERE activity_id = ? AND kind = ? LIMIT 1",
            (activity_id, kind.value),
        ).fetchone()
        return row is not None

    def _require_own_label(self, activity_id: str, label_id: str) -> None:
        """A correction may only supersede a label on the same session."""
        row = self._db.execute(
            "SELECT activity_id FROM labels WHERE label_id = ?", (label_id,)
        ).fetchone()
        if row is None:
            msg = f"cannot supersede {label_id}: no such label"
            raise StoreError(msg)
        if row["activity_id"] != activity_id:
            msg = (
                f"cannot supersede {label_id}: it belongs to activity {row['activity_id']}, "
                f"not {activity_id}"
            )
            raise StoreError(msg)


def _label_of(row: Any) -> StoredLabel:
    """Rebuild a stored label from its row. SQLite has no bool, so both flags are ints."""
    return StoredLabel(
        label_id=row["label_id"],
        activity_id=row["activity_id"],
        t_start=row["t_start"],
        t_end=row["t_end"],
        is_wave=bool(row["is_wave"]),
        source=LabelSource(row["source"]),
        verified=bool(row["verified"]),
        direction=RideDirection(row["direction"]),
        note=row["note"],
        created_at=row["created_at"],
        supersedes=row["supersedes"],
    )
