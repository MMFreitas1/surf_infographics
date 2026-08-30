"""Canonical data model.

One-way door: changing these shapes requires an ADR (see CLAUDE.md).

Design note: ``lat``, ``lon`` and ``speed_ms`` are optional *by design*. Roughly half of a
real surf session has no GPS fix because the wrist is underwater. A sample without a
position is still a valid sample -- it carries time, heart rate and blind-window context.
See docs/data-findings.md.
"""

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, model_validator


class Fidelity(StrEnum):
    """How much of the original recording survived into the source file."""

    FIT = "fit"
    """Full fidelity: every record, developer fields, device metadata."""
    TCX = "tcx"
    """Partial: trackpoints with some extensions, no developer fields."""
    GPX = "gpx"
    """Degraded: records without a GPS fix are silently dropped by the exporter."""


class BlindCause(StrEnum):
    """Why a stretch of the session carries no position."""

    NO_FIX = "no_fix"
    """Record exists, position field is absent (wrist submerged)."""
    MISSING_RECORD = "missing_record"
    """No record at all (degraded export, or device stopped logging)."""
    UNKNOWN = "unknown"


class LabelSource(StrEnum):
    """Provenance of a wave label."""

    HUMAN = "human"
    """Marked by a person in the labeling UI. The only thing that counts as ground truth."""
    CIQ_BOOTSTRAP = "ciq_bootstrap"
    """Imported from the Connect IQ app's fields. Weak, unverified, excluded from metrics."""


class RideDirection(StrEnum):
    """Which way the rider travelled along the wave face."""

    LEFT = "left"
    RIGHT = "right"
    STRAIGHT = "straight"
    UNKNOWN = "unknown"


class Sample(BaseModel):
    """One instant of the session, nominally 1 Hz."""

    t: float
    """Unix seconds, UTC."""
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    speed_ms: float | None = Field(default=None, ge=0.0)
    hr_bpm: int | None = Field(default=None, ge=20, le=250)
    temp_c: float | None = None
    distance_m: float | None = Field(default=None, ge=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    """Confidence in this sample *as recorded* -- 1.0 for a first-party fix.

    Not the smoother's posterior. L1 does not write back here: its estimate is a separate
    row on :class:`SmoothedSample`, so a measured second and an estimated one can never be
    mistaken for each other (ADR-0010).
    """

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_position(self) -> bool:
        """True when both coordinates are present."""
        return self.lat is not None and self.lon is not None


class BlindWindow(BaseModel):
    """A stretch of session with no usable position. A first-class object, not an absence."""

    t_start: float
    t_end: float
    cause: BlindCause = BlindCause.UNKNOWN

    @model_validator(mode="after")
    def _check_order(self) -> BlindWindow:
        if self.t_end < self.t_start:
            msg = "blind window ends before it starts"
            raise ValueError(msg)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        """Length of the window in seconds."""
        return self.t_end - self.t_start

    def could_hide_a_wave(self, min_ride_s: float = 5.0) -> bool:
        """True when this window is long enough to conceal an entire ride."""
        return self.duration_s >= min_ride_s


class SmoothedSample(BaseModel):
    """One second of the L1 track: an estimate, never a measurement (ADR-0010).

    Parallel to :class:`Sample`, not a replacement for it. The measured track keeps exactly
    what the device recorded, gaps included; this one always carries a position, because an
    estimate exists even where no fix did. ``observed`` is the line between the two, and
    nothing downstream may render ``observed=False`` as measured.
    """

    t: float
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    vx_ms: float
    """Velocity east, m/s."""
    vy_ms: float
    """Velocity north, m/s."""
    position_sigma_m: float = Field(ge=0.0)
    """Posterior standard deviation of the position. What we do not know, in metres."""
    confidence: float = Field(ge=0.0, le=1.0)
    """Derived from ``position_sigma_m``: 1.0 when the position is pinned, falling as the
    estimate loosens. Inside a blind window it bottoms out in the *middle*, because the
    backward pass pins the track from both ends."""
    observed: bool
    """True when this second carried a GPS fix."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def speed_ms(self) -> float:
        """Ground speed: the magnitude of the smoothed velocity."""
        return math.hypot(self.vx_ms, self.vy_ms)


class SessionFrame(BaseModel):
    """Where the shore is, for one session -- an estimate that states how good it is.

    A feature like "travelled shoreward for six seconds" needs an axis to be measured
    against, and that axis is not the compass: it is the local shore normal (ADR-0003).
    This is that axis, estimated once per session and reused by everything downstream.

    ``coherence`` is what keeps it honest. Where a session has real rides, the fast seconds
    agree on a direction and it runs high; on a flat day nothing points shoreward and it
    collapses. A low value is an answer -- "we cannot tell where the shore is" -- not a
    failure to be papered over with a confident wrong bearing.
    """

    shore_bearing_deg: float = Field(ge=0.0, lt=360.0)
    """Compass bearing of *shoreward*, the direction a ride travels. 90 is due east."""
    coherence: float = Field(ge=0.0, le=1.0)
    """Weighted mean resultant length of the velocity directions. 1.0 is total agreement."""
    reliable: bool
    """``coherence`` cleared the stage's threshold. False means: do not trust the bearing."""
    contributing_seconds: int = Field(ge=0)
    """How many seconds carried enough motion to weigh on the estimate."""
    effective_seconds: float = Field(ge=0.0)
    """Kish effective sample size of the weights: ``(sum w)^2 / sum w^2``. How many seconds
    the bearing *actually* rests on, which is not the same as how many were counted. One
    6 m/s spike in an otherwise aimless session drives this to ~1 while coherence reads
    0.9, so this is what stops a single second from passing as a session's worth of
    evidence."""
    origin_lat: float = Field(ge=-90.0, le=90.0)
    """Latitude of the local frame's origin."""
    origin_lon: float = Field(ge=-180.0, le=180.0)
    """Longitude of the local frame's origin, so shore-relative metres map back to the map."""


class FramedSample(BaseModel):
    """One second of the track, rotated into the session's shore frame.

    Parallel to :class:`SmoothedSample` in the same way that one is parallel to
    :class:`Sample`: rotating an estimate leaves it an estimate. ``observed`` and
    ``confidence`` ride through untouched, because the measured/estimated line (ADR-0010)
    has to survive as far as a :class:`WaveCandidate`.
    """

    t: float
    cross_shore_m: float
    """Metres from the origin toward the shore. Positive is shoreward."""
    along_shore_m: float
    """Metres along the shore, 90 degrees to the left of shoreward."""
    v_cross_ms: float
    """Velocity toward the shore, m/s. Positive on a ride."""
    v_along_ms: float
    """Velocity along the shore, m/s."""
    confidence: float = Field(ge=0.0, le=1.0)
    """Carried through from the L1 track: a rotation adds no certainty."""
    observed: bool
    """True when this second carried a GPS fix."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def speed_ms(self) -> float:
        """Ground speed. A rotation preserves it, so this matches the L1 track exactly."""
        return math.hypot(self.v_cross_ms, self.v_along_ms)


class WaveCandidate(BaseModel):
    """A proposed ride interval, before and after scoring."""

    t_start: float
    t_end: float
    features: dict[str, float] = Field(default_factory=dict)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    """Calibrated probability that this is a real ride. None until L5 runs."""
    direction: RideDirection = RideDirection.UNKNOWN
    position_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    """Fraction of the candidate's duration that had a GPS fix."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        """Length of the candidate in seconds."""
        return self.t_end - self.t_start


class WaveLabel(BaseModel):
    """Human ground truth. Append-only: corrections are new rows (ADR-0006)."""

    t_start: float
    t_end: float
    is_wave: bool
    source: LabelSource = LabelSource.HUMAN
    verified: bool = False
    direction: RideDirection = RideDirection.UNKNOWN
    note: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def counts_as_truth(self) -> bool:
        """Only verified human labels may enter an evaluation metric."""
        return self.source is LabelSource.HUMAN and self.verified


class ActivitySummary(BaseModel):
    """An activity without its samples, for listing.

    A projection, not a second canonical shape: every field here means exactly what it
    means on :class:`Activity`. It exists because a list endpoint must not ship 3790
    samples per row -- and because returning an ``Activity`` with an empty ``samples``
    list would read as "this session recorded nothing", which is a lie about the data.
    """

    activity_id: str
    sport: str
    start_time: float
    fidelity: Fidelity
    device: str = ""
    source_file: str = ""
    sample_count: int
    duration_s: float
    position_coverage: float
    blind_seconds: float
    ingested_at: float

    @classmethod
    def of(cls, activity: Activity, *, ingested_at: float) -> ActivitySummary:
        """Project a full activity down to its summary."""
        return cls(
            activity_id=activity.activity_id,
            sport=activity.sport,
            start_time=activity.start_time,
            fidelity=activity.fidelity,
            device=activity.device,
            source_file=activity.source_file,
            sample_count=len(activity.samples),
            duration_s=activity.duration_s,
            position_coverage=activity.position_coverage,
            blind_seconds=activity.blind_seconds,
            ingested_at=ingested_at,
        )


class Activity(BaseModel):
    """A single recorded session."""

    activity_id: str
    sport: str
    start_time: float
    fidelity: Fidelity
    samples: list[Sample] = Field(default_factory=list)
    blind_windows: list[BlindWindow] = Field(default_factory=list)
    device: str = ""
    source_file: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        """Wall-clock length of the session."""
        if not self.samples:
            return 0.0
        return self.samples[-1].t - self.samples[0].t

    @computed_field  # type: ignore[prop-decorator]
    @property
    def position_coverage(self) -> float:
        """Fraction of samples carrying a GPS fix. Expect roughly 0.5 for surfing."""
        if not self.samples:
            return 0.0
        return sum(1 for s in self.samples if s.has_position) / len(self.samples)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def blind_seconds(self) -> float:
        """Total time with no usable position."""
        return sum(w.duration_s for w in self.blind_windows)
