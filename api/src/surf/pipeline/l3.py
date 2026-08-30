"""L3 -- candidates: generous proposals of where a ride might be.

This stage is deliberately loose. Its job is to miss nothing; L5's scorer is what decides
which proposals survive, and it can only tighten a set it was given. A candidate that never
gets proposed here cannot be recovered later, so recall is the metric that matters and
precision is explicitly not gated.

The rule is shape, not speed. Phase 2 measured smoothed top-end speed swinging
11.55 -> 8.50 m/s across the ``measurement_noise_m`` sweep, so "a ride is faster than X m/s"
would encode an assumed noise level rather than anything about surfing. Instead the
threshold is a **quantile of this session's own** shoreward velocity: the fastest few per
cent of seconds, whatever that happens to mean on the day. A calm session and a big one both
propose their own extremes.

What comes out is intervals, not judgements. `direction` stays `UNKNOWN` and `score` stays
`None`: left-versus-right needs ground truth to validate, and calling it here would be an
unmeasured claim of exactly the kind ADR-0008 exists to keep out.

The frame rides along on the output. ADR-0011 leaves an unreliable frame usable but marked,
and a candidate is only as trustworthy as the axis it was measured against -- so the two
travel together rather than the caller having to remember to fetch the frame separately.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from numpy.typing import NDArray

from surf.models import FramedSample, RideDirection, SessionFrame, WaveCandidate
from surf.pipeline.l2 import FramedTrack
from surf.pipeline.stage import StageMeta

NAME = "L3"
"""Candidate generation is stage L3."""

CODE_VERSION = "1"
"""Bump when this stage changes what it proposes, so cached candidates are not reused."""

_DEFAULT_DT = 1.0
"""Sample spacing assumed when a track is too short to measure its own cadence."""

_COLUMNS = ("t_start", "t_end", "position_coverage")
_CANDIDATES_KEY = b"surf.l3.frame"


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class CandidateSet:
    """L3's output: the proposals, and the frame they were measured against."""

    frame: SessionFrame
    candidates: list[WaveCandidate]


def _cadence(samples: Sequence[FramedSample]) -> float:
    """The track's own sample spacing, as the median step. Falls back to 1 Hz."""
    if len(samples) < 2:
        return _DEFAULT_DT
    steps = np.diff(np.array([s.t for s in samples], dtype=np.float64))
    positive = steps[steps > 0.0]
    return float(np.median(positive)) if positive.size else _DEFAULT_DT


def _runs(above: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Inclusive index spans where the mask is true."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(above):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            spans.append((start, i - 1))
            start = None
    if start is not None:
        spans.append((start, len(above) - 1))
    return spans


@dataclass(frozen=True)
class CandidateStage:
    """L3: propose ride intervals from sustained shoreward motion."""

    quantile: float = 0.75
    """Which of this session's own shoreward speeds counts as fast. Swept against recall over
    seven seeded sessions: mean recall is flat at 0.821 from 0.70 to 0.75 and falls away above
    it, so 0.75 is the most generous threshold that still buys anything. Going lower only
    costs precision -- 0.704 at q=0.70 against 0.794 here -- for recall already saturated.
    Recall is what this stage is for; L5 is what tightens precision."""
    min_duration_s: float = 3.0
    """Shorter than this is a lurch, not a ride. The synthetic's rides are 6 s."""
    merge_gap_s: float = 2.0
    """Two bursts closer than this are one ride that dipped below threshold mid-wave."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Each param moves the proposals, so each is in the key."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "quantile": self.quantile,
                "min_duration_s": self.min_duration_s,
                "merge_gap_s": self.merge_gap_s,
            },
        )

    def run(self, data: FramedTrack) -> CandidateSet:
        """Propose intervals of sustained shoreward motion.

        A session with no shoreward motion at all proposes nothing, rather than proposing
        its least-seaward seconds.
        """
        samples = data.samples
        if not samples:
            return CandidateSet(frame=data.frame, candidates=[])

        v_cross = np.array([s.v_cross_ms for s in samples], dtype=np.float64)
        shoreward = v_cross[v_cross > 0.0]
        if shoreward.size == 0:
            return CandidateSet(frame=data.frame, candidates=[])

        threshold = float(np.quantile(shoreward, self.quantile))
        dt = _cadence(samples)
        times = [s.t for s in samples]

        spans = _runs(v_cross >= threshold)
        intervals = [(times[i], times[j] + dt) for i, j in spans]
        merged = self._merge(intervals)

        return CandidateSet(
            frame=data.frame,
            candidates=[
                WaveCandidate(
                    t_start=start,
                    t_end=end,
                    position_coverage=self._coverage(samples, start, end),
                    direction=RideDirection.UNKNOWN,
                )
                for start, end in merged
                if end - start >= self.min_duration_s
            ],
        )

    def _merge(self, intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Join bursts separated by less than ``merge_gap_s``.

        A ride that dips below threshold for a second in the middle is one wave, not two,
        and splitting it would cost recall at the IoU matcher rather than gaining precision.
        """
        merged: list[tuple[float, float]] = []
        for start, end in intervals:
            if merged and start - merged[-1][1] < self.merge_gap_s:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _coverage(samples: Sequence[FramedSample], start: float, end: float) -> float:
        """Fraction of the interval's seconds that carried a real GPS fix (ADR-0010).

        This is what stops a candidate assembled entirely from estimated seconds reading
        like one built from measurements.
        """
        during = [s for s in samples if start <= s.t < end]
        if not during:
            return 0.0
        return sum(1 for s in during if s.observed) / len(during)

    def encode(self, output: CandidateSet) -> bytes:
        """Serialise the proposals, with the frame they were measured against as metadata."""
        columns: dict[str, pa.Array] = {
            name: pa.array([getattr(c, name) for c in output.candidates], type=pa.float64())
            for name in _COLUMNS
        }
        columns["score"] = pa.array([c.score for c in output.candidates], type=pa.float64())
        columns["direction"] = pa.array(
            [c.direction.value for c in output.candidates], type=pa.string()
        )
        columns["features"] = pa.array(
            [json.dumps(c.features, sort_keys=True) for c in output.candidates],
            type=pa.string(),
        )
        table = pa.table(columns).replace_schema_metadata(
            {_CANDIDATES_KEY: output.frame.model_dump_json().encode("utf-8")}
        )
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return bytes(sink.getvalue().to_pybytes())

    def decode(self, payload: bytes) -> CandidateSet:
        """Rebuild the candidate set ``encode`` wrote, frame included."""
        table = pq.read_table(pa.BufferReader(payload))
        raw = (table.schema.metadata or {}).get(_CANDIDATES_KEY)
        if raw is None:
            msg = f"{NAME} payload carries no frame metadata: it was not written by this stage"
            raise PayloadError(msg)
        return CandidateSet(
            frame=SessionFrame(**json.loads(raw)),
            candidates=[
                WaveCandidate(
                    t_start=row["t_start"],
                    t_end=row["t_end"],
                    position_coverage=row["position_coverage"],
                    score=row["score"],
                    direction=RideDirection(row["direction"]),
                    features=json.loads(row["features"]),
                )
                for row in table.to_pylist()
            ],
        )
