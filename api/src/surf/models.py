"""Canonical data model.

One-way door: changing these shapes requires an ADR (see CLAUDE.md).

Design note: ``lat``, ``lon`` and ``speed_ms`` are optional *by design*. Roughly half of a
real surf session has no GPS fix because the wrist is underwater. A sample without a
position is still a valid sample -- it carries time, heart rate and blind-window context.
See docs/data-findings.md.
"""

from __future__ import annotations

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
    """Posterior confidence in this sample's kinematics. 1.0 until L1 refines it."""

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
