"""L0 -- ingest as a pipeline stage: source bytes in, a canonical `Activity` out.

The stage's identity -- its name, code version and params -- lives here rather than in
``surf.store``. Those three things describe what *produced* a payload; the store only
records where the payload landed. Keeping them in the store meant every later stage would
have copied the pattern instead of inheriting it.

The cached payload is a Parquet table of the sample track, with the session's own fields --
id, sport, start time, fidelity, device, blind windows -- in the file's key-value metadata.
It is self-describing on purpose: a cache hit must return exactly what a run returns, so
decoding one cannot depend on a SQLite row that a cache-only re-run may not have. SQLite
stays the queryable index over the same facts (docs/architecture.md §3).

The one invariant worth restating: a sample with no position round-trips as ``None``, never
as ``0.0``. Parquet has a null and we use it. Writing a zero would turn "we could not see"
into "the surfer was at the equator, stationary", which is the failure this project exists
to avoid.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq

from surf.ingest import parse_activity
from surf.ingest.blind import GAP_TOLERANCE
from surf.models import Activity, BlindCause, BlindWindow, Fidelity, Sample
from surf.pipeline import StageMeta

NAME = "L0"
"""Ingest is stage L0, and its output is cached under that name like any other stage."""

CODE_VERSION = "2"
"""Bump when the parsers change what they produce, so cached payloads are not reused."""

_FLOAT_COLUMNS = ("t", "lat", "lon", "speed_ms", "temp_c", "distance_m", "confidence")
_INT_COLUMNS = ("hr_bpm",)

_SESSION_KEY = b"surf.session"
"""Parquet key-value metadata entry holding everything that is not a per-sample column."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


def _sample_table(samples: Sequence[Sample]) -> pa.Table:
    """Columns for the sample track, preserving absent values as nulls rather than zeros."""
    columns: dict[str, pa.Array] = {
        name: pa.array([getattr(s, name) for s in samples], type=pa.float64())
        for name in _FLOAT_COLUMNS
    }
    for name in _INT_COLUMNS:
        columns[name] = pa.array([getattr(s, name) for s in samples], type=pa.int32())
    return pa.table(columns)


def _session_json(activity: Activity) -> bytes:
    """The activity minus its samples, as compact JSON. Computed fields are not stored."""
    return json.dumps(
        {
            "activity_id": activity.activity_id,
            "sport": activity.sport,
            "start_time": activity.start_time,
            "fidelity": activity.fidelity.value,
            "device": activity.device,
            "source_file": activity.source_file,
            "blind_windows": [
                {"t_start": w.t_start, "t_end": w.t_end, "cause": w.cause.value}
                for w in activity.blind_windows
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")


def encode_activity(activity: Activity) -> bytes:
    """Serialise a whole activity: samples as columns, the session as file metadata."""
    table = _sample_table(activity.samples).replace_schema_metadata(
        {_SESSION_KEY: _session_json(activity)}
    )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="zstd")
    return bytes(sink.getvalue().to_pybytes())


def samples_from_parquet(payload: bytes) -> list[Sample]:
    """Read just the sample track back. Nulls become ``None``, which is what they meant."""
    table = pq.read_table(pa.BufferReader(payload))
    return [Sample(**row) for row in table.to_pylist()]


def decode_activity(payload: bytes) -> Activity:
    """Rebuild the activity a cached payload stands for, samples and session alike."""
    table = pq.read_table(pa.BufferReader(payload))
    raw = (table.schema.metadata or {}).get(_SESSION_KEY)
    if raw is None:
        msg = f"{NAME} payload carries no session metadata: it was not written by this stage"
        raise PayloadError(msg)
    session = json.loads(raw)
    return Activity(
        activity_id=session["activity_id"],
        sport=session["sport"],
        start_time=session["start_time"],
        fidelity=Fidelity(session["fidelity"]),
        samples=[Sample(**row) for row in table.to_pylist()],
        blind_windows=[
            BlindWindow(t_start=w["t_start"], t_end=w["t_end"], cause=BlindCause(w["cause"]))
            for w in session["blind_windows"]
        ],
        device=session["device"],
        source_file=session["source_file"],
    )


@dataclass(frozen=True)
class IngestStage:
    """L0: parse an activity file into the canonical :class:`~surf.models.Activity`.

    ``source_file`` is display-only and deliberately absent from the params: it never
    changes what is parsed, so posting the same bytes under two names must not produce
    two cache entries.
    """

    gap_tolerance: float = GAP_TOLERANCE
    source_file: str = ""

    @property
    def meta(self) -> StageMeta:
        """Stage identity.

        ``gap_tolerance`` decides where a missing-record window opens, so it belongs in
        the key: change it and every cached blind window is drawn to the old rule.
        """
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={"gap_tolerance": self.gap_tolerance},
        )

    def run(self, data: bytes) -> Activity:
        """Parse the posted bytes. The format is read from content, never from the name."""
        return parse_activity(data, self.source_file, gap_tolerance=self.gap_tolerance)

    def encode(self, output: Activity) -> bytes:
        """Serialise the activity for the stage cache."""
        return encode_activity(output)

    def decode(self, payload: bytes) -> Activity:
        """Rebuild the activity from a cached payload."""
        return decode_activity(payload)
