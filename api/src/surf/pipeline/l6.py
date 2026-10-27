"""L6 -- metrics: the session and its waves as numbers a screen can render.

The last stage that computes anything. L5 commits to *how many* waves; this says what each
one was like and what the session added up to, so that the screen does arithmetic nowhere.

That division matters more than it looks. A browser summing odometer deltas would be a
pipeline stage with no cache key, no tests and no coverage attached to its answer -- and the
same figure would be derived twice, slightly differently, the first time a second screen
wanted it (architecture.md section 5.8).

**Nothing here re-decides anything.** The waves are exactly L5's, in time order, with their
boundaries untouched (ADR-0016). No feature is added to L4 and no threshold is touched, so
this stage cannot move the wave count -- which is the whole reason the per-wave numbers are
surfaced here rather than grown into L4, where they would have changed its key and with it
every verdict downstream.

**A figure that cannot be computed is `None`, never 0.0.** Zero metres means "did not move"
and zero km/h means "stood still"; both are claims about the surfing rather than about the
recording. L4 already follows that rule for an absent channel (ADR-0014) and it carries
through to the boundary here.

**Session figures count the session, not the recording.** The span is L0.6's, and any
stretch it excluded is excluded here too -- otherwise the walk up the beach lands in the
session's cadence. L0.6 hangs beside L1 rather than in the chain (ADR-0015), so its identity
travels in this stage's params; see :attr:`MetricStage.audit_key`.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from surf.models import (
    AngleSource,
    AuditReport,
    CadenceBucket,
    FramedSample,
    ReturnInterval,
    RideDirection,
    Sample,
    SessionFrame,
    SessionMetrics,
    SessionVerdict,
    SignSource,
    SpeedHistogram,
    WaveMetrics,
    WaveVerdict,
)
from surf.pipeline.l4 import FeatureSet
from surf.pipeline.stage import StageMeta

NAME = "L6"
"""Metrics are stage L6."""


def _ramp(value: float, low: float, high: float) -> float:
    """0 at or below ``low``, 1 at or above ``high``, linear between.

    Its own copy rather than L5's, because the two are free to diverge and a shared
    constant would hide that one of them had moved -- the reason ``takeoff_s`` is
    duplicated here too.
    """
    if high <= low:
        return 0.0
    return min(1.0, max(0.0, (value - low) / (high - low)))


CODE_VERSION = "1"
"""Bump when a figure changes meaning, so cached rows are not reused under a new definition."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class MetricInput:
    """What L6 needs: L5's answer, L4's measurements, the track and the raw channels.

    Five inputs rather than one for the same reason :class:`~surf.pipeline.l4.FeatureInput`
    takes three: the keyed input carries only part of what the stage has to read. The
    verdicts carry no speeds, the track carries no odometer, and neither knows which seconds
    the audit calls session.

    ``features`` is L4's output unchanged. Every per-wave speed and distance below was
    already measured there -- this stage selects and names them, it does not re-measure.
    """

    verdict: SessionVerdict
    features: FeatureSet
    framed: Sequence[FramedSample]
    samples: Sequence[Sample]
    """The **cleaned** session's samples, for the odometer. L0.5 never writes
    ``distance_m``, so it arrives exactly as the device recorded it."""
    audit: AuditReport


@dataclass(frozen=True)
class MetricStage:
    """L6: measure the session and every wave L5 settled."""

    takeoff_s: float = 4.0
    """The opening stretch ``takeoff_speed_ms`` averages over.

    The same window L4 reads its take-off acceleration from, so the two describe the same
    part of the ride. Kept as this stage's own parameter rather than imported from L4: they
    are free to diverge, and a shared constant would hide that one of them had moved.
    """
    bin_ms: float = 0.5
    """Width of a speed histogram bin, in m/s. Narrow enough to separate paddling from
    riding -- the two populations sit around 1 and above 4 -- and wide enough that a
    session's worth of seconds does not scatter into noise."""
    bucket_s: float = 600.0
    """Length of a cadence bucket. Ten minutes, because "waves per 10 min" is the figure the
    design asks for and bucketing on anything else would mean rescaling it for display."""
    straight_band_deg: float = 8.0
    """How far off dead-shoreward still counts as going straight.

    **Derived from two directions rather than swept.** From below: a left cannot become a
    right unless the angle uncertainty exceeds *twice* the band, so with the reference
    session's two witnesses 4.4 degrees apart anything above 2.2 makes a handed error
    impossible. From above: Miguel labelled his session a right-hand point and ride 11 --
    the best-measured marginal call in it, 23 observed seconds of 24 -- a **right** at 9.3
    degrees off, so a band of 10 or more would call a real right straight.

    8.0 sits between. The consequence is that **straight is rare by design**, which is the
    point: it is a beginner's shape, riding the whitewater in to the beach, and Miguel does
    not ride it. A band wide enough to be safe against a badly chosen regression window
    would have swallowed a quarter of his session.
    """
    direction_margin_deg: float = 20.0
    """How far past the band a ride has to run before its direction stops being marginal.

    The angular half of ``direction_confidence``: a ride just outside the band is a weaker
    claim than one at right angles to the shore, and this is the span over which that
    confidence is ramped. 20 degrees, which puts the measured spread of real rides (9.3 to
    33.8 off straight) across the whole range rather than bunched at the top.
    """
    single_witness_factor: float = 0.6
    """What a direction is worth when the shore axis rested on one witness, not two.

    A frame off the coastline alone or the velocity alone is usable and is a weaker claim
    (ADR-0022), and the factor says so rather than the screen having to look it up. Not
    measured -- there is one labelled session -- so it is a stated discount and is named one.
    """
    audit_key: str = ""
    """The cache key of the L0.6 audit these figures were computed against.

    L0.6 is not in this stage's chain -- it hangs beside L1 so that retuning a coverage
    threshold cannot invalidate a smoothed track that cannot have changed (ADR-0015). But it
    decides which seconds count as session, so a different audit *must* mean different
    metrics. Carrying its key here is the same device L5 uses for its adjudicator
    (``l5.py``, "a different model, a different answer"): the parameter is part of the key,
    so a retuned audit produces a fresh aggregate instead of silently reusing the old one.
    """

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Every param moves a number, and the audit decides the span."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "takeoff_s": self.takeoff_s,
                "bin_ms": self.bin_ms,
                "bucket_s": self.bucket_s,
                "straight_band_deg": self.straight_band_deg,
                "direction_margin_deg": self.direction_margin_deg,
                "single_witness_factor": self.single_witness_factor,
                "audit_key": self.audit_key,
            },
        )

    def run(self, data: MetricInput) -> SessionMetrics:
        """Measure the session, then each wave in it."""
        features = {(c.t_start, c.t_end): c.features for c in data.features.candidates}

        # L3 emits its proposals in time order, so this sort changes nothing today. It is
        # here because `index` and the return intervals below both read the order as
        # meaning, and an interval computed from an out-of-order pair would be negative --
        # a thing to be made impossible rather than validated against later.
        waves = sorted((v for v in data.verdict.verdicts if v.is_wave), key=lambda v: v.t_start)
        rows = [
            self._wave(index, verdict, features.get((verdict.t_start, verdict.t_end), {}), data)
            for index, verdict in enumerate(waves, start=1)
        ]

        ride_spans = [(row.t_start, row.t_end) for row in rows]
        session_s = float(sum(1 for s in data.framed if self._in_session(s.t, data.audit)))
        observed_s = sum(1 for s in data.framed if s.observed and self._in_session(s.t, data.audit))
        returns = self._returns(rows)
        intervals = [r.seconds for r in returns]
        distance_m = self._session_distance(data.samples, data.audit)
        ride_m = _total(row.ride_m for row in rows)

        return SessionMetrics(
            waves=rows,
            distance_m=distance_m,
            ride_m=ride_m,
            swim_m=(
                max(0.0, distance_m - ride_m)
                if distance_m is not None and ride_m is not None
                else None
            ),
            ride_measured_m=_total(row.ride_measured_m for row in rows),
            speed=self._histogram(data.framed, data.audit),
            # The same code over the wave spans only. With no waves there are no riding
            # seconds, so this is None rather than an empty distribution.
            ride_speed=self._histogram(data.framed, data.audit, ride_spans),
            waves_per_10min=(len(rows) / session_s * 600.0 if session_s > 0.0 else 0.0),
            cadence=self._cadence(rows, data.audit),
            bucket_s=self.bucket_s,
            returns=returns,
            return_mean_s=statistics.fmean(intervals) if intervals else None,
            return_median_s=statistics.median(intervals) if intervals else None,
            session_s=session_s,
            coverage=observed_s / session_s if session_s > 0.0 else 0.0,
        )

    def _direction(
        self, features: dict[str, float], frame: SessionFrame
    ) -> tuple[RideDirection, float | None]:
        """Left, right, straight or unknown -- and what the answer is worth.

        **The count is not re-decided here and cannot be.** L5 settled which candidates are
        waves; this names a property of one it already kept (architecture.md section 3).

        Three ways the answer is ``UNKNOWN``, and each is a different silence worth keeping
        distinct. The frame never established which way the sea is, so alongshore has no
        agreed sign and every direction would be a coin toss. Or the frame has no angle at
        all. Or the watch saw under two seconds of the ride, so L4 reported no alongshore
        travel -- the reference session's ride 2 is three seconds the watch missed entirely,
        and it ships as a wave that publishes no direction rather than one that guesses.

        Confidence is the product of three factors, each in [0, 1] and each with a reason:
        how far past the straight band the ride ran, how much of the ride was observed, and
        whether the shore axis had two witnesses or one. A product rather than a weighted sum
        because any one of them being near zero should sink the claim on its own -- a
        perfectly angled ride seen for two seconds is not a confident left.
        """
        if frame.sign_source is SignSource.NONE or frame.angle_source is AngleSource.NONE:
            return RideDirection.UNKNOWN, None

        along = features.get("alongshore_ms")
        offset = features.get("shoreward_offset_deg")
        if along is None or offset is None:
            return RideDirection.UNKNOWN, None

        if offset < self.straight_band_deg:
            direction = RideDirection.STRAIGHT
        else:
            direction = RideDirection.LEFT if along > 0.0 else RideDirection.RIGHT

        angle = _ramp(
            offset, self.straight_band_deg, self.straight_band_deg + self.direction_margin_deg
        )
        witnesses = 1.0 if frame.disagreement_deg is not None else self.single_witness_factor
        coverage = features.get("position_coverage", 0.0)
        return direction, max(0.0, min(1.0, angle * coverage * witnesses))

    def _wave(
        self,
        index: int,
        verdict: WaveVerdict,
        features: dict[str, float],
        data: MetricInput,
    ) -> WaveMetrics:
        """One wave's card, mostly selected from what L4 already measured."""
        direction, confidence = self._direction(features, data.features.frame)
        return WaveMetrics(
            index=index,
            t_start=verdict.t_start,
            t_end=verdict.t_end,
            position_coverage=verdict.position_coverage,
            top_speed_ms=features.get("measured_speed_max_ms"),
            avg_speed_ms=features.get("measured_speed_mean_ms"),
            takeoff_speed_ms=self._takeoff_speed(data.framed, verdict.t_start),
            ride_m=features.get("odometer_m"),
            ride_measured_m=_measured_metres(data.samples, verdict.t_start, verdict.t_end),
            hr_mean_bpm=features.get("hr_mean_bpm"),
            hr_max_bpm=features.get("hr_max_bpm"),
            direction=direction,
            direction_confidence=confidence,
        )

    def _takeoff_speed(self, framed: Sequence[FramedSample], start: float) -> float | None:
        """Mean observed speed over the ride's opening seconds.

        Observed only, and `None` when the watch saw none of them: a take-off is exactly
        where the wrist goes under, so this is a figure that is often honestly unknown.
        """
        onset = [s.speed_ms for s in framed if start <= s.t < start + self.takeoff_s and s.observed]
        return statistics.fmean(onset) if onset else None

    def _histogram(
        self,
        framed: Sequence[FramedSample],
        audit: AuditReport,
        spans: Sequence[tuple[float, float]] | None = None,
    ) -> SpeedHistogram | None:
        """Observed seconds, spread across fixed-width speed bins.

        ``spans`` restricts which seconds count. ``None`` means the whole session, which is
        the figure the confidence panel is about; the wave spans mean the seconds spent on a
        wave, which is a *different population* and the one the Velocidade card is about.
        A session is mostly paddling, so the two differ by more than a rounding: mixing them
        puts the mean between two humps, where it describes neither.
        """
        speeds = [
            s.speed_ms
            for s in framed
            if s.observed and self._in_session(s.t, audit) and _within(s.t, spans)
        ]
        if not speeds:
            return None

        bins = max(1, math.ceil(max(speeds) / self.bin_ms))
        counts = [0] * bins
        for speed in speeds:
            counts[min(bins - 1, int(speed / self.bin_ms))] += 1

        return SpeedHistogram(
            bin_edges_ms=[round(i * self.bin_ms, 6) for i in range(bins + 1)],
            counts=counts,
            mean_ms=statistics.fmean(speeds),
            # Population, not sample: these are all the seconds there were, not a draw
            # from a larger set of them.
            sd_ms=statistics.pstdev(speeds),
            n_seconds=len(speeds),
        )

    def _cadence(self, rows: Sequence[WaveMetrics], audit: AuditReport) -> list[CadenceBucket]:
        """Waves per bucket across the session span, counted by where each ride began."""
        buckets: list[CadenceBucket] = []
        start = audit.surfing_t_start
        while start < audit.surfing_t_end:
            end = min(start + self.bucket_s, audit.surfing_t_end)
            buckets.append(
                CadenceBucket(
                    t_start=start,
                    t_end=end,
                    waves=sum(1 for row in rows if start <= row.t_start < end),
                )
            )
            start = end
        return buckets

    def _returns(self, rows: Sequence[WaveMetrics]) -> list[ReturnInterval]:
        """The paddle back out after each wave but the last."""
        return [
            ReturnInterval(after_wave=current.index, seconds=max(0.0, nxt.t_start - current.t_end))
            for current, nxt in pairwise(rows)
        ]

    def _session_distance(self, samples: Sequence[Sample], audit: AuditReport) -> float | None:
        """How far the odometer moved across the session, from its reading at each end.

        A cumulative field read at two points, which is the one thing it can always be
        trusted for: the freezing and back-filling that makes it unusable as a rate
        (ADR-0014) cancels out over a span. The exception is a recording that ends with the
        fix still gone -- its final catch-up step never arrives, so the total is short by
        that last blind run. Stated here rather than corrected, because the distance was
        never recorded.
        """
        readings = [
            s.distance_m
            for s in samples
            if self._in_session(s.t, audit) and s.distance_m is not None
        ]
        if len(readings) < 2:
            return None
        return max(0.0, readings[-1] - readings[0])

    def _in_session(self, t: float, audit: AuditReport) -> bool:
        """Whether this second is one a session figure is entitled to count (ADR-0015)."""
        if not (audit.surfing_t_start <= t < audit.surfing_t_end):
            return False
        return not any(w.t_start <= t < w.t_end for w in audit.not_surfing)

    def encode(self, output: SessionMetrics) -> bytes:
        """JSON, not Parquet: tens of rows, like L5's verdicts."""
        return output.model_dump_json().encode("utf-8")

    def decode(self, payload: bytes) -> SessionMetrics:
        """Rebuild the metrics ``encode`` wrote."""
        try:
            return SessionMetrics.model_validate_json(payload)
        except ValueError as exc:
            msg = f"{NAME} payload is not a SessionMetrics: it was not written by this stage"
            raise PayloadError(msg) from exc


def _within(t: float, spans: Sequence[tuple[float, float]] | None) -> bool:
    """Whether this second falls inside one of ``spans``. ``None`` restricts nothing.

    An empty sequence is not the same as ``None``: it restricts to nothing at all, which is
    what a session with no waves should mean.
    """
    if spans is None:
        return True
    return any(start <= t < end for start, end in spans)


def _total(values: Iterable[float | None]) -> float | None:
    """Sum what was measured, or `None` when nothing was.

    A sum over no measurements is not 0.0 -- that would report a session with no odometer as
    one where nobody moved.
    """
    present = [value for value in values if value is not None]
    return math.fsum(present) if present else None


def _measured_metres(samples: Sequence[Sample], start: float, end: float) -> float | None:
    """Odometer metres this span's **observed** seconds account for, and only those.

    A step whose previous sample had no fix is the device's catch-up for the blind run
    behind it, not travel during the second it landed on -- the artefact that makes 201
    metres look like 201 m/s (ADR-0014). Those steps belong to the run, so they are left out
    here entirely: this is the part of ``ride_m`` the watch actually saw, which is why it is
    always the smaller of the two.
    """
    total = 0.0
    known = False
    for previous, current in pairwise(samples):
        if not (start <= current.t < end):
            continue
        if not (current.has_position and previous.has_position):
            continue
        if current.distance_m is None or previous.distance_m is None:
            continue
        total += max(0.0, current.distance_m - previous.distance_m)
        known = True
    return total if known else None
