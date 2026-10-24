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

**Since ADR-0022 that estimate is one of two witnesses, not the method.** The axis is a
question about the beach, so a published coastline can answer it without consulting the
session at all -- and on the reference session the two land **4.2 degrees apart**. Two
estimators sharing no input agreeing that closely is evidence; one estimator agreeing with
itself is not, which is the whole reason the gate moved.

So this stage answers two separate questions with two separate chains, because the angle and
the sign have different best sources.

**The angle**, in order and never silently substituted: the coastline, then velocity, then
neither. It comes back mod 180 either way, because that is all a line can tell you.

**The sign** -- which perpendicular points to land: the walk, then the fast runs, then
neither. Nothing in a static coastline file can supply it. GSHHG places the reference
session's sit spot, where Miguel floated for 23 minutes, *inside* its own land polygon, so a
point-in-polygon test answers confidently and wrongly. The audit already separates the walk
from the session (ADR-0015), and the walk is on land: all 489 observed walking seconds of the
reference recording fall on one side, with no exceptions.

**Reliability is agreement.** With both witnesses, ``reliable`` is whether their axes land
within ``max_disagreement_deg``. With the coastline alone it holds, because a coastline
cannot be fooled by the session it is describing. With velocity alone ADR-0011's two guards
still apply unchanged -- a single 6 m/s second scores 0.90 coherence off a Kish size of 1.25,
and no coastline is there to catch it. ``coherence`` is still computed and still reported; it
has simply stopped being what decides. It read 0.365 on the reference session and refused a
bearing that was right all along.

An unreliable frame is still returned, with its numbers and ``reliable=False``. That is
ADR-0011's rule and it has not changed: it is not an error, and it is not a default bearing.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from surf import coast as coastline
from surf.geo import LocalFrame
from surf.models import (
    AngleSource,
    AuditReport,
    CoastFit,
    FramedSample,
    SessionFrame,
    SignSource,
    SmoothedSample,
)
from surf.pipeline.stage import StageMeta

NAME = "L2"
"""The frame is stage L2."""

CODE_VERSION = "2"
"""Bump when this stage changes what it produces, so cached frames are not reused.

2 -- two witnesses for the axis, the sign from the walk, and agreement in place of
coherence as the gate (ADR-0022)."""

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

MIN_SIGN_SECONDS = 10
"""How many observed seconds each of the session and the walk must carry for the walk to
settle the sign. Ten is a floor against a stray fix outside the session span, not a measured
threshold: the reference recording offers 489 walking seconds against 1334 in the water."""

MIN_SIGN_SEPARATION_M = 20.0
"""How far the witness must land from zero to be read as a side at all.

Without it a walk that happens to sit *along* the shore from the peak -- offset nearly zero
on the cross-shore axis -- would have its sign decided by a metre of noise."""

MIN_RUN_SECONDS = 3
"""Shortest stretch counted as a fast run by the ride-majority witness."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class FrameInput:
    """What L2 needs: the smoothed track, and the audit that knows where the walk was.

    Two inputs rather than one for the reason :class:`~surf.pipeline.l4.FeatureInput` takes
    three -- the keyed input carries only part of what the stage reads. The track knows
    nothing about which of its seconds were a walk up the beach, and that is precisely the
    evidence that fixes which way the shore is.

    ``audit`` is optional so the stage stays usable without L0.6: the sign then falls to the
    fast runs, which is a weaker witness and is recorded as one.
    """

    track: Sequence[SmoothedSample]
    audit: AuditReport | None = None


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


@lru_cache(maxsize=1)
def _coast_fingerprint() -> str:
    """Digest of the committed coastline, or "" when it cannot be read.

    Computed here rather than passed in, because a parameter the caller has to remember to
    fill is a silent-wrongness trap: forget it and a cached bearing is served under a
    coastline it was not computed from, with nothing on screen to say so. ``coast.load`` is
    memoised, so this is one file read per process.
    """
    try:
        return coastline.load().sha256
    except coastline.CoastlineError:
        return ""


def _axis_of(bearing_deg: float) -> float:
    """A direction, reduced to the axis it lies on. Both witnesses compare as axes.

    Comparing a *direction* would fold the sign into the disagreement and make two estimators
    that agree perfectly about the beach look 180 degrees apart.
    """
    return bearing_deg % 180.0


def _axis_gap(first_deg: float, second_deg: float) -> float:
    """Angle between two axes, in [0, 90]."""
    return abs((first_deg - second_deg + 90.0) % 180.0 - 90.0)


def _unit(bearing_deg: float) -> tuple[float, float]:
    """(east, north) of a compass bearing."""
    theta = math.radians(bearing_deg)
    return math.sin(theta), math.cos(theta)


def sign_from_walk(
    track: Sequence[SmoothedSample], audit: AuditReport | None, shoreward_deg: float
) -> float | None:
    """How far the walk sits along the candidate shoreward direction, or ``None``.

    The audit's not-surfing stretches are the walk down the beach and the walk back, measured
    perfectly and excluded from the session (ADR-0015). They are on **land**, so the
    perpendicular that points toward them is the one that points shoreward.

    Returns the signed median offset in metres, relative to the session's own observed
    centroid: positive means this candidate direction is shoreward. ``None`` when there is no
    walk to read, or when it sits too close to the session to separate the two sides.
    """
    if audit is None or not track:
        return None

    inside = [
        s
        for s in track
        if s.observed and audit.surfing_t_start <= s.t <= audit.surfing_t_end
    ]
    outside = [
        s
        for s in track
        if s.observed and not (audit.surfing_t_start <= s.t <= audit.surfing_t_end)
    ]
    if len(inside) < MIN_SIGN_SECONDS or len(outside) < MIN_SIGN_SECONDS:
        return None

    origin = inside[0]
    local = LocalFrame(lat0=origin.lat, lon0=origin.lon)
    east, north = _unit(shoreward_deg)
    session = [local.to_metres(s.lat, s.lon) for s in inside]
    centre_x = sum(x for x, _ in session) / len(session)
    centre_y = sum(y for _, y in session) / len(session)

    offsets = sorted(
        (x - centre_x) * east + (y - centre_y) * north
        for x, y in (local.to_metres(s.lat, s.lon) for s in outside)
    )
    median = offsets[len(offsets) // 2]
    return median if abs(median) >= MIN_SIGN_SEPARATION_M else None


def sign_from_rides(
    track: Sequence[SmoothedSample], shoreward_deg: float, *, min_speed_ms: float
) -> float | None:
    """Net displacement of the fast runs along the candidate direction, or ``None``.

    The weaker witness, and deliberately listed as one: it reads the same evidence the
    velocity estimator does, so it cannot corroborate a velocity angle -- it can only supply
    a sign the coastline could not. On the reference session it calls the side 7 runs out of
    10, net +301 m, where the walk calls it 489 seconds out of 489.
    """
    runs = _fast_runs(track, min_speed_ms)
    if not runs:
        return None

    origin = next((s for s in track if s.observed), None)
    if origin is None:
        return None
    local = LocalFrame(lat0=origin.lat, lon0=origin.lon)
    east, north = _unit(shoreward_deg)

    net = 0.0
    for run in runs:
        start_x, start_y = local.to_metres(run[0].lat, run[0].lon)
        end_x, end_y = local.to_metres(run[-1].lat, run[-1].lon)
        net += (end_x - start_x) * east + (end_y - start_y) * north
    return net if abs(net) >= MIN_SIGN_SEPARATION_M else None


def _fast_runs(
    track: Sequence[SmoothedSample], min_speed_ms: float
) -> list[list[SmoothedSample]]:
    """Contiguous observed stretches above a speed floor.

    Speed only, with no axis involved, because the axis is what this is helping to decide.
    An axis-derived detector here would be the pipeline grading its own homework.
    """
    out: list[list[SmoothedSample]] = []
    current: list[SmoothedSample] = []
    for sample in track:
        if sample.observed and math.hypot(sample.vx_ms, sample.vy_ms) >= min_speed_ms:
            current.append(sample)
        else:
            if len(current) >= MIN_RUN_SECONDS:
                out.append(current)
            current = []
    if len(current) >= MIN_RUN_SECONDS:
        out.append(current)
    return out


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
    use_coastline: bool = True
    """Whether to ask the coastline at all. False falls the angle straight through to
    velocity, which is what a test needs to exercise the fallback on purpose."""
    coast_radius_m: float = coastline.DEFAULT_RADIUS_M
    """How far either way along the shore to fit. **Declared, because it is the dominant
    lever**: the same anchor on the dense OSM measuring stick gives 142.0 deg at 200 m and
    168.7 at 1500. 1000 m is where the committed extract's spacing supports a fit and where
    it agrees with OSM to 0.2 deg (ADR-0022)."""
    max_disagreement_deg: float = 25.0
    """How far the two witnesses may be apart and still be believed.

    Measured 4.2 deg on the reference session, so this clears it with room. It is a
    disagreement ceiling rather than a tuned threshold: the two estimators share no input,
    so a gap much larger than a few degrees means one of them is describing somewhere else
    -- a session at a spot the extract does not really cover, or a session whose motion
    never pointed shoreward."""
    ride_sign_speed_ms: float = 4.0
    """Speed floor for the ride-majority sign witness. Speed only, no axis: the axis is what
    it is helping to decide, so reading one here would be circular."""
    coast: coastline.Coastline | None = None
    """A coastline to use instead of the committed extract.

    Injected rather than loaded so the primary estimator can be tested against a known
    answer. The committed extract reaches the real Portuguese coast and the synthetic session
    sits 5 km offshore of it, so without this the coastline witness would never fire in a
    test or an eval at all -- the evals were passing because the primary path was never
    exercised, which is the kind of green that means nothing.

    Only its digest enters the cache key, never the geometry."""
    audit_key: str = ""
    """L0.6's cache key, carried as a **param** rather than in the input hash.

    Exactly L6's pattern in ``session.py:metrics_for`` and for ADR-0015's reason: the walk
    decides the sign, so a different audit is a different frame and must re-key -- but the
    audit changes no sample, and putting L0.6 in front of L1 would mean retuning a coverage
    threshold invalidated a smoothed track that cannot have changed. Empty when no audit was
    supplied, in which case the sign falls to the fast runs."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Every param here moves the bearing, so every one is in the key.

        ``coast_sha256`` is read from the file rather than passed in, so that a bearing can
        never be served under a coastline it was not computed from -- not even by a caller
        who forgot to thread it through.
        """
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "speed_exponent": self.speed_exponent,
                "min_coherence": self.min_coherence,
                "min_effective_seconds": self.min_effective_seconds,
                "use_confidence_weight": self.use_confidence_weight,
                "use_coastline": self.use_coastline,
                "coast_radius_m": self.coast_radius_m,
                "coast_sha256": self._coast_sha256(),
                "max_disagreement_deg": self.max_disagreement_deg,
                "ride_sign_speed_ms": self.ride_sign_speed_ms,
                "audit_key": self.audit_key,
            },
        )

    def run(self, data: FrameInput | Sequence[SmoothedSample]) -> FramedTrack:
        """Rotate a smoothed track into its own shore frame.

        An empty track yields an empty result whose frame is explicitly unreliable: there
        is no session to find a shore for, and a default bearing of due north would be a
        fiction that reads exactly like a measurement.

        A bare sequence is accepted as well as a :class:`FrameInput`, so a caller with no
        audit to offer -- a test, or a session ingested before L0.6 existed -- does not have
        to wrap it to say so. The sign then falls to the fast runs, and says it did.
        """
        payload = data if isinstance(data, FrameInput) else FrameInput(track=data)
        track = payload.track
        if not track:
            return FramedTrack(frame=self._empty_frame(), samples=[])

        velocity = estimate_bearing(
            track,
            speed_exponent=self.speed_exponent,
            use_confidence_weight=self.use_confidence_weight,
        )
        origin = track[0]
        fit = self._coast_fit(track, payload.audit)
        axis, angle_source = self._axis(fit, velocity)
        shoreward, sign_source = self._shoreward(track, payload.audit, axis)

        frame = SessionFrame(
            shore_bearing_deg=shoreward % 360.0,
            coherence=velocity.coherence,
            reliable=self._is_reliable(fit, velocity, angle_source, sign_source),
            contributing_seconds=velocity.contributing,
            effective_seconds=velocity.effective,
            origin_lat=origin.lat,
            origin_lon=origin.lon,
            angle_source=angle_source,
            sign_source=sign_source,
            disagreement_deg=self._disagreement(fit, velocity),
            coast=fit,
        )
        local = LocalFrame(lat0=origin.lat, lon0=origin.lon)
        return FramedTrack(frame=frame, samples=self._rotate(track, local, _unit(shoreward)))

    def _coast_sha256(self) -> str:
        """Which coastline this frame is keyed on: the injected one, or the committed file."""
        if not self.use_coastline:
            return ""
        return self.coast.sha256 if self.coast is not None else _coast_fingerprint()

    def _coast_fit(
        self, track: Sequence[SmoothedSample], audit: AuditReport | None
    ) -> CoastFit | None:
        """Fit the published coastline near the session, or ``None`` where it does not reach.

        Anchored on the **session's** observed centroid, not the recording's. The recording
        is longer than the session (ADR-0015) and the walk back up the beach runs a couple of
        hundred metres inland, so including it drags the anchor off the water. Small here --
        it moved the fitted angle 0.2 deg on the reference session -- but the audit is in
        this stage's input already, and an anchor that is partly on a footpath is the wrong
        anchor whatever it costs.

        Not a clustered peak either. Measured: the session centroid and the
        observed-weighted peak centroid sit 28 m apart and differ by 0.62 deg, against a
        tolerance of tens of degrees, so peak clustering is not in this path at all
        (ADR-0022). Absence is a state the caller handles, never a default bearing.
        """
        if not self.use_coastline:
            return None
        positioned = [
            s
            for s in track
            if s.observed
            and (audit is None or audit.surfing_t_start <= s.t <= audit.surfing_t_end)
        ]
        if not positioned:
            return None

        latitude = sum(s.lat for s in positioned) / len(positioned)
        longitude = sum(s.lon for s in positioned) / len(positioned)
        try:
            bearing = coastline.bearing_near(
                latitude, longitude, self.coast_radius_m, coast=self.coast
            )
        except coastline.CoastlineError:
            # A missing extract is a missing witness, not a broken session. The frame falls
            # through to velocity and records that it did.
            return None
        if bearing is None:
            return None
        return CoastFit(
            bearing_deg=bearing.bearing_deg,
            residual_m=bearing.residual_m,
            points=bearing.points,
            radius_m=bearing.radius_m,
            sha256=self._coast_sha256(),
        )

    def _axis(
        self, fit: CoastFit | None, velocity: _Bearing
    ) -> tuple[float, AngleSource]:
        """The angle chain: coastline, then velocity, then neither.

        Returns an axis in [0, 180) and which witness gave it. The coastline is primary not
        because it measured better -- the two agree to 4.2 deg -- but because it shares no
        input with the session. L3 finds candidates by projecting onto this axis, so an axis
        estimated from the session's own velocity is partly circular; an external one is not.
        """
        if fit is not None:
            return fit.bearing_deg, AngleSource.COASTLINE
        if velocity.coherence > 0.0:
            # Velocity gives a *direction*; the axis it implies is a quarter turn off it.
            return _axis_of(velocity.bearing_deg + 90.0), AngleSource.VELOCITY
        return 0.0, AngleSource.NONE

    def _shoreward(
        self,
        track: Sequence[SmoothedSample],
        audit: AuditReport | None,
        axis_deg: float,
    ) -> tuple[float, SignSource]:
        """The sign chain: the walk, then the fast runs, then neither.

        An axis has two perpendiculars. This picks one and says who picked it. When nobody
        can, the first perpendicular is returned with ``SignSource.NONE`` and the frame is
        unreliable -- a rotation still has to happen for the track to be expressible at all,
        and marking it is what stops the arbitrary choice from reading as a measurement.
        """
        candidate = (axis_deg - 90.0) % 360.0

        walk = sign_from_walk(track, audit, candidate)
        if walk is not None:
            return (candidate if walk > 0.0 else (candidate + 180.0) % 360.0), SignSource.WALK

        rides = sign_from_rides(track, candidate, min_speed_ms=self.ride_sign_speed_ms)
        if rides is not None:
            return (candidate if rides > 0.0 else (candidate + 180.0) % 360.0), SignSource.RIDES

        return candidate, SignSource.NONE

    @staticmethod
    def _disagreement(fit: CoastFit | None, velocity: _Bearing) -> float | None:
        """How far apart the two witnesses are, as axes, or ``None`` when only one answered.

        Compared as axes rather than as directions on purpose: folding the sign in would
        make two estimators that agree perfectly about the beach look 180 degrees apart.
        """
        if fit is None or velocity.coherence <= 0.0:
            return None
        return _axis_gap(fit.bearing_deg, _axis_of(velocity.bearing_deg + 90.0))

    def _is_reliable(
        self,
        fit: CoastFit | None,
        velocity: _Bearing,
        angle_source: AngleSource,
        sign_source: SignSource,
    ) -> bool:
        """Agreement, where there are two witnesses; ADR-0011's guards where there is one.

        An axis with no side to it is not usable whatever the angle, so a missing sign is
        disqualifying on its own.

        With both witnesses the test is whether they agree, because they share no input.
        With the **coastline alone** it holds: a coastline cannot be fooled by the session
        it is describing, and the thing a lone velocity estimate can get wrong is exactly
        the thing it cannot see about itself. With **velocity alone** ADR-0011's two guards
        apply unchanged -- votes that disagree, caught by coherence, and votes that agree
        only because nearly all the weight sits on one second, caught by the Kish size.
        """
        if angle_source is AngleSource.NONE or sign_source is SignSource.NONE:
            return False

        disagreement = self._disagreement(fit, velocity)
        if disagreement is not None:
            return disagreement <= self.max_disagreement_deg
        if angle_source is AngleSource.COASTLINE:
            return True
        return (
            velocity.coherence >= self.min_coherence
            and velocity.effective >= self.min_effective_seconds
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
        track: Sequence[SmoothedSample], local: LocalFrame, shoreward: tuple[float, float]
    ) -> list[FramedSample]:
        """Project to local metres, then rotate position and velocity into the shore frame.

        Cross-shore is the shoreward unit vector; alongshore is that turned 90 degrees to
        the left, which makes the pair right-handed.
        """
        cross_e, cross_n = shoreward
        along_e, along_n = -cross_n, cross_e
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
