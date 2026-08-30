"""L2 -- frame: where the shore is, and the track rotated to face it.

A feature has to mean the same thing at every break, and absolute east/north does not
(ADR-0003). "Travelled shoreward at 6 m/s for five seconds" is a statement about surfing;
"travelled east" is a statement about Sines. This stage estimates the one axis that turns
the first into the second, then rotates the L1 track into it.

The bearing comes from a **speed-weighted** sum of velocity directions: every second votes
for where it was heading, weighted by how fast it was going and how well we knew it. Rides
are the fast seconds and they run shoreward, so they dominate the sum; paddling is slow and
largely cancels itself. Nothing here crosses a speed *threshold*, and that is the point.
Phase 2 measured the smoothed top-end speed swinging 11.55 -> 8.50 m/s across the
``measurement_noise_m`` sweep, so a rule keyed on absolute speed would be tuned to an
assumed noise level rather than to surfing. Weighting only ever compares seconds *within*
one session, so scaling every velocity by a constant leaves the bearing exactly where it
was -- a property `test_frame.py` pins directly.

The estimate carries its own reliability. ``coherence`` is the weighted mean resultant
length of those direction votes: near 1 when the fast seconds agree, near 0 when they do
not. A flat day has no rides to point shoreward, and the honest output is "we cannot tell
where the shore is", not a confident wrong bearing. That is what ``reliable`` records.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from surf.geo import LocalFrame
from surf.models import FramedSample, SessionFrame, SmoothedSample
from surf.pipeline.stage import StageMeta

NAME = "L2"
"""The frame is stage L2."""

CODE_VERSION = "1"
"""Bump when this stage changes what it produces, so cached frames are not reused."""

_COLUMNS = (
    "t",
    "cross_shore_m",
    "along_shore_m",
    "v_cross_ms",
    "v_along_ms",
    "confidence",
)
_FRAME_KEY = b"surf.l2.frame"
"""Parquet metadata entry holding the session frame -- part of the output, not provenance."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class FramedTrack:
    """L2's output: one session's frame, and its track rotated into that frame."""

    frame: SessionFrame
    samples: list[FramedSample]


@dataclass(frozen=True)
class _Bearing:
    """The estimated shoreward direction, with the evidence behind it."""

    east: float
    """East component of the shoreward unit vector."""
    north: float
    """North component of the shoreward unit vector."""
    coherence: float
    contributing: int
    effective: float
    """Kish effective sample size: how many seconds the estimate really rests on."""

    @property
    def bearing_deg(self) -> float:
        """Compass bearing of shoreward: clockwise from north, so due east is 90."""
        return math.degrees(math.atan2(self.east, self.north)) % 360.0


def estimate_bearing(
    track: Sequence[SmoothedSample],
    *,
    speed_exponent: float = 2.0,
    use_confidence_weight: bool = True,
) -> _Bearing:
    """Estimate the shoreward direction from a speed-weighted sum of headings.

    Each second contributes its unit velocity, weighted by ``speed ** speed_exponent`` and,
    optionally, by how well the position was known. Weighting by confidence keeps an
    estimated second inside a blind window from carrying the same vote as a measured one.

    A second that was not moving has no heading to contribute and is left out rather than
    counted as agreeing with nothing.
    """
    if not track:
        return _Bearing(east=0.0, north=0.0, coherence=0.0, contributing=0, effective=0.0)

    vx = np.array([s.vx_ms for s in track], dtype=np.float64)
    vy = np.array([s.vy_ms for s in track], dtype=np.float64)
    speed = np.hypot(vx, vy)

    weights = np.power(speed, speed_exponent)
    if use_confidence_weight:
        weights = weights * np.array([s.confidence for s in track], dtype=np.float64)

    moving = speed > 0.0
    weights = np.where(moving, weights, 0.0)
    total = float(weights.sum())
    if total <= 0.0:
        return _Bearing(east=0.0, north=0.0, coherence=0.0, contributing=0, effective=0.0)
    effective = total * total / float((weights * weights).sum())

    unit_x = np.divide(vx, speed, out=np.zeros_like(vx), where=moving)
    unit_y = np.divide(vy, speed, out=np.zeros_like(vy), where=moving)
    east = float((weights * unit_x).sum())
    north = float((weights * unit_y).sum())

    resultant = math.hypot(east, north)
    if resultant <= 0.0:
        # Every heading cancelled: there is a sum, but it points nowhere.
        return _Bearing(
            east=0.0,
            north=0.0,
            coherence=0.0,
            contributing=int(moving.sum()),
            effective=effective,
        )

    return _Bearing(
        east=east / resultant,
        north=north / resultant,
        coherence=resultant / total,
        contributing=int((weights > 0.0).sum()),
        effective=effective,
    )


@dataclass(frozen=True)
class FrameStage:
    """L2: estimate the shore bearing and rotate the L1 track into the shore frame."""

    speed_exponent: float = 4.0
    """How hard fast seconds outvote slow ones, swept against the synthetic where the true
    shore is known. At 2.0 a one- or two-wave session comes out pointing *seaward* -- 154
    and -172 degrees wrong -- because sustained paddling outweighs a couple of short rides.
    At 4.0 the same sessions land within 24 and 13 degrees, and every session with three or
    more waves lands within 3.6. Higher still buys nothing: the error curve is flat past 4
    while the estimate leans on ever fewer seconds."""
    min_coherence: float = 0.85
    """Below this the direction votes disagree too much to call, and the frame is reported
    unreliable rather than dressed up as a bearing. Measured: rideless sessions score 0.01
    to 0.10, one- and two-wave sessions 0.24 to 0.44, and every session accurate to better
    than 4 degrees scores above 0.88."""
    min_effective_seconds: float = 5.0
    """The bearing must rest on at least this much effective evidence. Coherence alone
    cannot see concentration: a single 6 m/s spike in an otherwise aimless session scores
    0.90 coherence off an effective sample size of 1.25. Every genuinely rideable session
    measured here clears 13. This is the guard that keeps one second from speaking for a
    session."""
    use_confidence_weight: bool = True
    """Weight each second's vote by its L1 confidence, so an estimated second inside a
    blind window counts for less than a measured one."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Every param here moves the bearing, so every one is in the key."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "speed_exponent": self.speed_exponent,
                "min_coherence": self.min_coherence,
                "min_effective_seconds": self.min_effective_seconds,
                "use_confidence_weight": self.use_confidence_weight,
            },
        )

    def run(self, data: Sequence[SmoothedSample]) -> FramedTrack:
        """Rotate a smoothed track into its own shore frame.

        An empty track yields an empty result whose frame is explicitly unreliable: there
        is no session to find a shore for, and a default bearing of due north would be a
        fiction that reads exactly like a measurement.
        """
        if not data:
            return FramedTrack(frame=self._empty_frame(), samples=[])

        bearing = estimate_bearing(
            data,
            speed_exponent=self.speed_exponent,
            use_confidence_weight=self.use_confidence_weight,
        )
        origin = data[0]
        frame = SessionFrame(
            shore_bearing_deg=bearing.bearing_deg,
            coherence=bearing.coherence,
            reliable=self._is_reliable(bearing),
            contributing_seconds=bearing.contributing,
            effective_seconds=bearing.effective,
            origin_lat=origin.lat,
            origin_lon=origin.lon,
        )
        local = LocalFrame(lat0=origin.lat, lon0=origin.lon)
        return FramedTrack(frame=frame, samples=self._rotate(data, local, bearing))

    def _is_reliable(self, bearing: _Bearing) -> bool:
        """Two independent ways the bearing can fail, so two guards.

        The votes can disagree, which coherence catches; or they can agree only because
        almost all the weight sits on a handful of seconds, which only the effective sample
        size catches. Both have to pass.
        """
        return (
            bearing.coherence >= self.min_coherence
            and bearing.effective >= self.min_effective_seconds
        )

    def _empty_frame(self) -> SessionFrame:
        """The frame for a session with no track: no bearing, and it says so."""
        return SessionFrame(
            shore_bearing_deg=0.0,
            coherence=0.0,
            reliable=False,
            contributing_seconds=0,
            effective_seconds=0.0,
            origin_lat=0.0,
            origin_lon=0.0,
        )

    @staticmethod
    def _rotate(
        track: Sequence[SmoothedSample], local: LocalFrame, bearing: _Bearing
    ) -> list[FramedSample]:
        """Project to local metres, then rotate position and velocity into the shore frame.

        Cross-shore is the shoreward unit vector; alongshore is that turned 90 degrees to
        the left, which makes the pair right-handed.
        """
        cross_e, cross_n = bearing.east, bearing.north
        along_e, along_n = -bearing.north, bearing.east
        framed: list[FramedSample] = []
        for s in track:
            x, y = local.to_metres(s.lat, s.lon)
            framed.append(
                FramedSample(
                    t=s.t,
                    cross_shore_m=x * cross_e + y * cross_n,
                    along_shore_m=x * along_e + y * along_n,
                    v_cross_ms=s.vx_ms * cross_e + s.vy_ms * cross_n,
                    v_along_ms=s.vx_ms * along_e + s.vy_ms * along_n,
                    confidence=s.confidence,
                    observed=s.observed,
                )
            )
        return framed

    def encode(self, output: FramedTrack) -> bytes:
        """Serialise the framed track: rows as columns, the frame as file metadata.

        The frame is read back on decode, unlike L1's params: it *is* part of the output,
        and a cache hit has to return everything a run would have returned.
        """
        columns: dict[str, pa.Array] = {
            name: pa.array([getattr(s, name) for s in output.samples], type=pa.float64())
            for name in _COLUMNS
        }
        columns["observed"] = pa.array([s.observed for s in output.samples], type=pa.bool_())
        table = pa.table(columns).replace_schema_metadata(
            {_FRAME_KEY: output.frame.model_dump_json().encode("utf-8")}
        )
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return bytes(sink.getvalue().to_pybytes())

    def decode(self, payload: bytes) -> FramedTrack:
        """Rebuild the framed track ``encode`` wrote."""
        table = pq.read_table(pa.BufferReader(payload))
        raw = (table.schema.metadata or {}).get(_FRAME_KEY)
        if raw is None:
            msg = f"{NAME} payload carries no frame metadata: it was not written by this stage"
            raise PayloadError(msg)
        return FramedTrack(
            frame=SessionFrame(**json.loads(raw)),
            samples=[FramedSample(**row) for row in table.to_pylist()],
        )
