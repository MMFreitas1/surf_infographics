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
    HUMAN_ASSISTED = "human_assisted"
    """Marked by a person who could see L3's proposals. Real judgement, but anchored to the
    detector's: a ride the detector never proposed is one the labeller was never prompted to
    look at. Kept out of the headline metric so a detector is never scored against a truth
    set it helped draw (ADR-0012)."""
    CIQ_BOOTSTRAP = "ciq_bootstrap"
    """Imported from the Connect IQ app's fields. Weak, unverified, excluded from metrics."""


class PassKind(StrEnum):
    """Which sweep of a session a labeller has completed."""

    BLIND = "blind"
    """Labelled from raw signal alone, with no candidates on screen."""
    ASSISTED = "assisted"
    """A second sweep with L3's proposals visible. Only ever runs after a blind pass."""


class RideDirection(StrEnum):
    """Which way the rider travelled along the wave face."""

    LEFT = "left"
    RIGHT = "right"
    STRAIGHT = "straight"
    UNKNOWN = "unknown"


class RejectionReason(StrEnum):
    """Why L0.5 refused to believe something the device recorded.

    Two channels, because a session carries two independent recordings of how fast the
    surfer was going and they can fail separately. The first three read the *positions*;
    the last three read the *speed field* and check it against something else that measured
    the same thing.
    """

    IMPLIED_SPEED = "implied_speed"
    """Reaching this fix from the last accepted one needs more speed than a surfer has."""
    IMPLIED_ACCELERATION = "implied_acceleration"
    """The implied speed changed faster than a body in water can change it."""
    JUMP_AND_RETURN = "jump_and_return"
    """The track left and came back inside a couple of seconds: a reacquisition, not a ride."""
    SPEED_VS_ODOMETER = "speed_vs_odometer"
    """The device's own distance counter did not move far enough for the speed it reported.

    The strongest of the six: ``distance_m`` survives the blind half at 100% coverage, so
    this is two first-party recordings of one quantity disagreeing, not a threshold guess.
    """
    SPEED_VS_ODOMETER_WINDOW = "speed_vs_odometer_window"
    """The odometer did not advance far enough *around* this second for it to be true.

    Containment rather than a threshold: a reading of ``v`` m/s asserts ``v`` metres of
    travel inside one second, and that second sits inside the window, so the window cannot
    have covered less ground than the second did. This catches what
    :attr:`SPEED_VS_ODOMETER` cannot -- a second where the odometer glitched *with* the
    speed field, so the two agreed with each other and were both wrong.
    """
    SPEED_VS_POSITION = "speed_vs_position"
    """The fixes bracketing this second contradict the speed it reported.

    The fallback for a format that carries no odometer, and weaker than it looks: it can
    only fire where fixes exist close enough on both sides to bracket the second at all.
    """
    SPEED_IMPOSSIBLE = "speed_impossible"
    """The reported speed is beyond anything a surfboard does, with no corroboration needed."""


class NotSurfingReason(StrEnum):
    """Why a stretch of the recording is not part of the session.

    The recording starts when the watch does and stops when the surfer remembers to stop it,
    so a session file routinely opens on the walk down and closes on the walk back. Those
    seconds are perfectly measured -- the wrist is dry, so coverage is *better* there than in
    the water -- they are simply not surfing.
    """

    BEFORE_ENTRY = "before_entry"
    """Recorded before the surfer got in the water."""
    AFTER_EXIT = "after_exit"
    """Recorded after the surfer came out."""
    INTERRUPTION = "interruption"
    """An interior stretch the surfer spent out of the water. Reserved for the audit pass;
    the deterministic baseline only trims the ends, because an interior lull is far more
    likely to be someone sitting on a board than someone leaving the beach."""


class AuditSource(StrEnum):
    """What decided a stretch was not surfing."""

    BASELINE = "baseline"
    """The deterministic rule: coverage, which is high out of the water and poor in it."""
    LLM = "llm"
    """The local model, adjudicating what the baseline could not settle. It only ships if it
    measurably beats the baseline (ADR-0005), so this value means a measured improvement."""


class AngleSource(StrEnum):
    """Which witness gave the shore's *angle*. Never inferred -- always recorded.

    Two estimators that share no input, so their agreement is evidence rather than
    consistency (ADR-0022). A direction served under ``NONE`` is not a measurement.
    """

    COASTLINE = "coastline"
    """A published coastline, fitted near the session. Shares nothing with the recording."""
    VELOCITY = "velocity"
    """ADR-0011's speed-weighted sum of headings, from the session's own motion."""
    NONE = "none"
    """Neither answered. The frame is returned anyway, marked, with no bearing to trust."""


class SignSource(StrEnum):
    """Which witness decided *which way* along the axis is shoreward.

    An angle is known mod 180: a line has no direction. Nothing in a static coastline file
    can supply the sign -- GSHHG places the reference session's sit spot inside its own land
    polygon -- so it comes from the recording (ADR-0022).
    """

    WALK = "walk"
    """The audit's not-surfing stretches. The walk is on land, which fixes the sign."""
    RIDES = "rides"
    """Net shoreward displacement of the fast runs. The weaker witness: it reads the same
    evidence the velocity estimator does, so it cannot corroborate a velocity angle."""
    NONE = "none"
    """Undetermined. The axis stands but no side of it is claimed."""


class RejectionEffect(StrEnum):
    """What a rejection actually did to the sample.

    Two effects, because demoting a whole fix over a bad speed reading would report "we
    could not see" about a second the watch saw perfectly well. Coverage has to keep
    meaning what it says, in both directions.
    """

    DEMOTED_TO_BLIND = "demoted_to_blind"
    """Position and speed cleared, ``has_position`` now False. Coverage falls by one."""
    SPEED_DROPPED = "speed_dropped"
    """Only ``speed_ms`` cleared. The position stood up and coverage is unchanged."""


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


class RejectedFix(BaseModel):
    """One thing L0.5 refused to believe, and the evidence that convicted it.

    Deliberately carries **no coordinates**. This repo is public and these records reach
    committed goldens; a lat/lon here would be a GPS trace in git (CLAUDE.md). The
    timestamp, the reason and the two magnitudes are what make a rejection arguable, and
    a coordinate adds nothing to that.

    A cleaner that silently drops data is indistinguishable from a bug, so every rejection
    becomes one of these and they are served, not just logged.
    """

    t: float
    """Unix seconds of the sample that was rejected."""
    reason: RejectionReason
    effect: RejectionEffect
    value: float
    """What was measured -- the implied speed, the odometer's rate, the reported speed."""
    limit: float
    """What it had to stay under. ``value`` against ``limit`` is the whole argument."""


class CleanReport(BaseModel):
    """What L0.5 did to one session: device confidence, in a shape the UI can draw.

    The before/after pairs are the honest part. A cleaner that reports only its rejections
    lets nobody judge whether it took too much, so the counts it started from travel with
    the counts it left behind.
    """

    enabled: bool = True
    """False when the cleaner was switched off. The report still ships, saying so."""
    sample_count: int = Field(ge=0)
    fixes_before: int = Field(ge=0)
    """Samples carrying a position when the cleaner started."""
    fixes_after: int = Field(ge=0)
    """Samples still carrying one when it finished."""
    speeds_before: int = Field(ge=0)
    speeds_after: int = Field(ge=0)
    rejections: list[RejectedFix] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage_before(self) -> float:
        """Position coverage as ingested."""
        return self.fixes_before / self.sample_count if self.sample_count else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage_after(self) -> float:
        """Position coverage once rejected fixes stopped counting as fixes.

        Lower than ``coverage_before`` by exactly the number demoted -- which is the point.
        A fix we refuse to believe must not go on being counted as a second the watch saw.
        """
        return self.fixes_after / self.sample_count if self.sample_count else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def counts_by_reason(self) -> dict[str, int]:
        """How many rejections each rule is responsible for, for the confidence card."""
        counts: dict[str, int] = {}
        for rejected in self.rejections:
            counts[rejected.reason.value] = counts.get(rejected.reason.value, 0) + 1
        return counts


class SessionWindow(BaseModel):
    """One slice of the recording, digested into numbers a rule or a model can read.

    **Carries no coordinates and no bearing, deliberately.** Everything here is a rate, a
    fraction or a count, so the digest describes *what the session did* without describing
    *where it happened*. That is what makes the opt-in hosted model path safe by
    construction rather than by policy: there is no location in the payload to leak.

    ``coverage`` is the load-bearing field. A surfer's wrist is underwater about half the
    time, so an in-water window runs near 0.4; carry the watch up the beach and it jumps to
    1.0. The thing that makes GPS hard is what makes this easy.
    """

    t_start: float
    t_end: float
    sample_count: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    """Fraction of this window's samples that carried a fix, after cleaning."""
    speed_mean_ms: float | None = None
    speed_max_ms: float | None = None
    speed_sd_ms: float | None = None
    """Standard deviation of the recorded speed. Surfing is bursty and walking is not."""
    odometer_rate_ms: float | None = None
    """Mean ground speed from the device's distance counter, which survives the blind half."""
    hr_mean_bpm: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        """Length of the window in seconds."""
        return self.t_end - self.t_start


class NotSurfingWindow(BaseModel):
    """A stretch of the recording that is not part of the session.

    An **exclusion, never a demotion** (ADR-0015). The samples underneath keep their
    position, their speed and ``observed=True``, because the watch could see perfectly well
    -- better than usual, in fact. What changes is only which seconds a session metric is
    entitled to count.
    """

    t_start: float
    t_end: float
    reason: NotSurfingReason
    source: AuditSource
    confidence: float = Field(ge=0.0, le=1.0)
    """How sure the decision is. The baseline states a real number rather than 1.0: trimming
    on coverage is a good rule, not a certainty."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        """Length of the excluded stretch in seconds."""
        return self.t_end - self.t_start


class AuditReport(BaseModel):
    """Which part of the recording was the session, and what was left out.

    Carries the digest it decided from, so the decision can be argued with rather than
    merely accepted -- the same reason :class:`CleanReport` ships its before-and-after counts.

    ``top_speed_ms_all`` against ``top_speed_ms_surfing`` is the number Phase 5 exists for.
    It is computed here, where the span is decided, rather than left for a later phase to
    derive and possibly derive differently.
    """

    decided: bool = True
    """False when the audit could not tell -- no window looked like it was in the water, so
    nothing is excluded and the whole recording stands. An absent answer, stated."""
    window_s: float = Field(gt=0.0)
    windows: list[SessionWindow] = Field(default_factory=list)
    not_surfing: list[NotSurfingWindow] = Field(default_factory=list)
    t_start: float
    t_end: float
    """Bounds of the whole recording."""
    surfing_t_start: float
    surfing_t_end: float
    """Bounds of the part that is the session. Equal to the above when nothing was excluded."""
    top_speed_ms_all: float | None = None
    top_speed_ms_surfing: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def excluded_s(self) -> float:
        """Seconds of recording that are not session."""
        return sum(window.duration_s for window in self.not_surfing)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def surfing_s(self) -> float:
        """Length of the session proper."""
        return self.surfing_t_end - self.surfing_t_start


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


class CoastFit(BaseModel):
    """What the coastline witness actually fitted, so the angle can be argued with."""

    bearing_deg: float = Field(ge=0.0, lt=180.0)
    """The axis the coast runs along. **Mod 180 by construction** -- a line has no
    direction, and the sign comes from :class:`SignSource`."""
    residual_m: float = Field(ge=0.0)
    """Rms perpendicular distance of the resampled points from the fitted line.

    Reported, and **not** a quality gate. Natural Earth scores 4.3 m near the reference peak
    and is the worse source: its fit is straight because it carries one vertex per 2.7 km.
    A fit that cannot be wrong is not thereby right (ADR-0022).
    """
    points: int = Field(ge=0)
    """How many resampled points the fit rested on."""
    radius_m: float = Field(gt=0.0)
    """The window fitted over. The dominant lever, so the answer is meaningless without it:
    the same anchor on dense OSM gives 142.0 deg at 200 m and 168.7 at 1500."""
    sha256: str
    """Digest of the coastline file. In L2's params too, so a bearing can never be served
    under a coastline it was not computed from."""


class SessionFrame(BaseModel):
    """Where the shore is, for one session -- an estimate that states how good it is.

    A feature like "travelled shoreward for six seconds" needs an axis to be measured
    against, and that axis is not the compass: it is the local shore normal (ADR-0003).
    This is that axis, estimated once per session and reused by everything downstream.

    **The axis has two witnesses and ``reliable`` is their agreement** (ADR-0022). A
    published coastline fitted near the session and ADR-0011's speed-weighted velocity sum
    share no input, so landing within a few degrees of each other is evidence rather than
    mere consistency -- they did it to 4.2 deg on the reference session.

    ``coherence`` is still computed and still reported, and it no longer decides anything.
    It is the weighted mean resultant length of the velocity direction votes: whether the
    fast seconds agree *with each other*, which on a session that is four-fifths paddling
    they do not even when their sum is correct. It read 0.365 on the reference session and
    refused a bearing that was right all along. Where velocity is the *only* witness it
    still guards, together with ``effective_seconds``, because a single fast second can
    score 0.90 off a Kish size of 1.25 and no coastline can catch that.
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
    angle_source: AngleSource = AngleSource.NONE
    """Which witness gave the angle. Defaults to ``NONE`` so a frame built by hand claims no
    provenance it does not have."""
    sign_source: SignSource = SignSource.NONE
    """Which witness decided which way is shoreward."""
    disagreement_deg: float | None = Field(default=None, ge=0.0, le=90.0)
    """Angle between the two witnesses' axes, when both answered. ``None`` means only one
    did, which is a usable frame and a weaker claim.

    **This is what ``reliable`` is computed from** when it is present. Measured 4.2 deg on
    the reference session, where ``coherence`` read 0.365 and refused a bearing that was
    right all along (ADR-0022). Bounded at 90 because both sides are axes mod 180."""
    coast: CoastFit | None = None
    """The coastline fit, when there was one."""


class Peak(BaseModel):
    """One stretch the track held still: a surfer sitting on a board, waiting.

    The sitting is the signal. Roughly 40% of the reference session is spent inside a 20 m
    circle for over a minute at a time, which is more of it than the riding and the paddling
    put together -- and it is where the waves come from, so it is what a map of a session
    should show.

    **There is no ``spread``.** The clusterer extends a group while every member stays within
    its radius of the running centroid, so the widest member always ends up at or near that
    radius: measured, spread equalled the radius at *every* radius swept. Reporting it would
    be reporting the parameter back as if it were a finding.
    """

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    """Centroid of the observed seconds in this cluster."""
    t_start: float
    t_end: float
    observed_s: int = Field(ge=0)
    """Seconds the watch actually saw. Only observed seconds are clustered at all, so this
    is also the member count -- and it is **not** ``t_end - t_start``, which is the whole
    reason a duration floor is not enough on its own."""
    area: int = Field(ge=0)
    """Which merged peak area this cluster belongs to. Centroids 4-80 m apart are one bank,
    not several peaks, so the clusters are grouped and the grouping is served."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        """Wall-clock span, blind seconds included."""
        return self.t_end - self.t_start

    @computed_field  # type: ignore[prop-decorator]
    @property
    def observed_fraction(self) -> float:
        """How much of the span the watch saw.

        The floor that matters. A 170 s cluster built on **10 observed seconds** is evidence
        of nothing, and an absolute seconds floor separates it worse than a fraction does:
        measured across the reference session's clusters, the fraction runs 0.06 to 0.75 with
        a median of 0.41 against the session's own 0.40, and the thin one is a clear outlier.
        """
        span = self.duration_s
        return self.observed_s / span if span > 0.0 else 0.0


class PeakArea(BaseModel):
    """Several clusters that are the same place -- one bank, visited repeatedly."""

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    """Observed-weighted centroid of the clusters in this area, so the longer sits count for
    more. Measured stable: across 48 parameter sets this point moved at most 24.9 m, median
    9.4 m, which is why no downstream number is allowed to depend on the clusterer's
    parameters."""
    peaks: int = Field(ge=1)
    observed_s: int = Field(ge=0)
    held_s: float = Field(ge=0.0)
    """Total wall-clock time held still here, summed over its clusters."""


class SessionPeaks(BaseModel):
    """Where one session sat still, and how those sits group into places.

    Hangs off L1 **beside** L2 rather than in front of it (ADR-0015's shape, and ADR-0022's
    reason): the frame does not depend on this. Anchoring the shore fit on the clustered peak
    rather than on the session's plain centroid moves the fitted angle 0.62 degrees, against
    a tolerance of tens of degrees -- so peaks exist to be drawn, not to decide anything.
    """

    peaks: list[Peak] = Field(default_factory=list)
    areas: list[PeakArea] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def held_s(self) -> float:
        """Total time the session spent sitting still."""
        return sum(peak.duration_s for peak in self.peaks)


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


class DecidedBy(StrEnum):
    """Which tier settled a candidate. ADR-0005's ladder, visible in the output.

    Recorded per verdict rather than per session because the two tiers are not equally
    trustworthy and a reader is entitled to know which one answered. It is also what makes
    "the model changed nothing on this session" an observation rather than a guess.
    """

    RULE = "rule"
    """The deterministic rule was confident enough to settle it alone."""
    MODEL = "model"
    """The rule landed in the ambiguous band and a model was asked."""
    UNRESOLVED = "unresolved"
    """The rule was unsure and no model was available. The band is not a verdict, so this
    candidate is **not** counted as a wave -- and says so, rather than defaulting quietly."""


class WaveVerdict(BaseModel):
    """One candidate, decided. L3 owns the boundaries; this owns only the answer.

    ``t_start`` and ``t_end`` are copied through untouched and no tier may move them.
    ADR-0016 measured this model's verdicts as reproducible across identical runs and its
    *span edges* as not, so the boundaries stay with the deterministic stage that produced
    them and the content-addressed guarantee in architecture.md section 3 survives.
    """

    t_start: float
    t_end: float
    is_wave: bool
    strength: float = Field(ge=0.0, le=1.0)
    """The deterministic rule's proposal strength, kept even when a model overrode it.

    Not a calibrated probability and must never be rendered as one: there are no labels to
    calibrate against (ADR-0013). It is the rule's own reading, on the rule's own scale.
    """
    decided_by: DecidedBy
    reason: str = ""
    """Why, in one line, in words a person can disagree with."""
    position_coverage: float = Field(default=0.0, ge=0.0, le=1.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start


class SessionVerdict(BaseModel):
    """What the pipeline commits to for one session: a count, and its reasoning.

    The count is the product's answer to "how many waves", and the pipeline reaches it
    rather than handing the ambiguity to the screen. Every candidate L3 proposed appears in
    ``verdicts`` with the tier that settled it, so the number can be taken apart.

    It is a *reading of the data*, not a validated measurement. No accuracy figure may be
    published beside it until a session is labelled the day it was surfed (ADR-0013); the UI
    states that once, for the session, rather than hedging every number on the screen.
    """

    verdicts: list[WaveVerdict] = Field(default_factory=list)
    adjudicated: int = Field(default=0, ge=0)
    """How many candidates the rule could not settle and a model was asked about."""
    model: str = ""
    """Which model answered, empty when none did. A verdict is only interpretable next to
    the thing that reached it."""
    prompt_version: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wave_count(self) -> int:
        """The number. One integer, reached here so nothing downstream has to decide."""
        return sum(1 for v in self.verdicts if v.is_wave)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def proposed_count(self) -> int:
        """How many candidates L3 offered, so the rejection rate stays visible."""
        return len(self.verdicts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unresolved_count(self) -> int:
        """Candidates no tier settled. Not counted as waves, and not hidden either."""
        return sum(1 for v in self.verdicts if v.decided_by is DecidedBy.UNRESOLVED)


class BasemapLayer(BaseModel):
    """One basemap the map may draw, and the attribution its licence requires.

    Served rather than hard-coded in the client so the licence text and the tile URL travel
    together with the process that serves the tiles. ``attribution`` is not optional and the
    map must render it -- and it is per layer, because the sea floor and the imagery are
    credited to different people.
    """

    id: str
    tile_url: str
    """Template with ``{z}``, ``{x}`` and ``{y}``, relative to the API's own origin."""
    attribution: str
    min_zoom: int = Field(ge=0, le=24)
    max_zoom: int = Field(ge=0, le=24)
    """Where the source's own resolution runs out. Past it the map overzooms the last tile,
    which looks soft rather than claiming detail the data does not have."""
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    """How strongly it draws when on. A shading layer at full strength replaces what it
    was meant to shade."""
    default: bool = False
    """Ticked on when the map opens. Exactly one layer carries this."""


class BasemapInfo(BaseModel):
    """Every layer the map may draw, in the order they stack, bottom first."""

    layers: list[BasemapLayer] = Field(default_factory=list)


class WaveMetrics(BaseModel):
    """One wave, measured. L5 decided *whether*; this says *what it was like*.

    Every field here is `None` when the channel it comes from was not recorded, never 0.0.
    Zero metres means "did not move" and zero km/h means "stood still", and both are claims
    about the surfing rather than about the recording -- the rule L4 already follows for a
    missing channel, carried through to the boundary (ADR-0014).

    ``t_start`` and ``t_end`` are L3's, copied through untouched like everything else
    downstream of it: no stage may move a boundary (ADR-0016).
    """

    index: int = Field(ge=1)
    """Which wave this is, counting from 1, in the order they were surfed. The number the
    screen puts on the card, assigned here so the UI never has to decide it."""
    t_start: float
    t_end: float
    position_coverage: float = Field(ge=0.0, le=1.0)
    top_speed_ms: float | None = None
    """Fastest observed second. Over observed seconds only -- an estimate's peak is a
    property of the smoother, not of the ride (ADR-0010)."""
    avg_speed_ms: float | None = None
    """Mean over the ride's observed seconds, take-off and kick-out included."""
    takeoff_speed_ms: float | None = None
    """Mean observed speed over the ride's opening seconds. Paired with wave speed when
    Phase 8 lands, this is what says whether the paddling needs work."""
    ride_m: float | None = None
    """Distance travelled, from the device's own odometer, attributed second by second: an
    observed second at its own delta, a blind second at its run's average. Part measurement
    and part even-spreading, which is why ``ride_measured_m`` ships beside it."""
    ride_measured_m: float | None = None
    """The part of ``ride_m`` the watch actually saw. Never larger than it."""
    hr_mean_bpm: float | None = None
    hr_max_bpm: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start


class SpeedHistogram(BaseModel):
    """How the session's observed seconds were distributed across speed.

    A histogram rather than a mean and a standard deviation alone, because a surf session is
    not one population: paddling and riding are two, and a session reported as "2.1 +/- 1.8
    m/s" draws a single tidy hump over a shape that had two. Both forms ship -- the summary
    statistics are here too -- so the screen can show the distribution and still draw the
    mean line the design asks for.

    Counts are over **observed, in-session** seconds. ``bin_edges_ms`` is one longer than
    ``counts``: edge *i* to edge *i+1* holds ``counts[i]``.
    """

    bin_edges_ms: list[float] = Field(default_factory=list)
    counts: list[int] = Field(default_factory=list)
    mean_ms: float
    sd_ms: float
    """Population standard deviation. 0.0 from a single second, which is honest: one
    measurement has no spread."""
    n_seconds: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_bins(self) -> SpeedHistogram:
        if len(self.bin_edges_ms) != len(self.counts) + 1:
            msg = (
                f"histogram is malformed: {len(self.bin_edges_ms)} edges around "
                f"{len(self.counts)} bins"
            )
            raise ValueError(msg)
        if sum(self.counts) != self.n_seconds:
            msg = f"histogram counts {sum(self.counts)} seconds but claims {self.n_seconds}"
            raise ValueError(msg)
        return self


class CadenceBucket(BaseModel):
    """How many waves were caught in one stretch of the session."""

    t_start: float
    t_end: float
    waves: int = Field(ge=0)


class ReturnInterval(BaseModel):
    """The paddle back out: from one wave's end to the next one's start."""

    after_wave: int = Field(ge=1)
    """The wave this interval follows, by :attr:`WaveMetrics.index`."""
    seconds: float = Field(ge=0.0)


class SessionMetrics(BaseModel):
    """L6: the session as the cards show it, and every wave in it, measured.

    The end of the chain, and the last stage that computes anything. It exists so that the
    screen does arithmetic nowhere: a browser summing odometer deltas would be a pipeline
    stage with no cache key, no tests and no coverage attached to its answer.

    Nothing here re-decides anything. The waves are exactly L5's, in L5's order; a figure
    this stage cannot compute is `None` rather than zero.
    """

    waves: list[WaveMetrics] = Field(default_factory=list)
    distance_m: float | None = None
    """The whole session, from the odometer's own reading at each end of the session span."""
    ride_m: float | None = None
    """Of that, the part spent on waves."""
    swim_m: float | None = None
    """And the part spent getting back out. ``distance_m`` minus ``ride_m``, so the two
    halves of the card's split bar always add up to the total above them."""
    ride_measured_m: float | None = None
    speed: SpeedHistogram | None = None
    """Every observed second in the water: paddling, sitting and riding together. None when
    no second of the session carried a fix -- a distribution over nothing is not a
    distribution."""
    ride_speed: SpeedHistogram | None = None
    """The observed seconds spent **on a wave**, and nothing else.

    A separate field rather than a filter the screen applies, because the two are different
    populations and only one of them is what "how fast did he surf" means. A session is
    mostly paddling -- on the reference session the whole-session distribution puts 239
    seconds under 0.5 m/s -- so a mean taken over both sits between two humps and describes
    neither. None when no wave had an observed second, including when there were no waves.
    """
    waves_per_10min: float = 0.0
    cadence: list[CadenceBucket] = Field(default_factory=list)
    bucket_s: float = Field(default=600.0, gt=0.0)
    returns: list[ReturnInterval] = Field(default_factory=list)
    return_mean_s: float | None = None
    return_median_s: float | None = None
    session_s: float = Field(default=0.0, ge=0.0)
    """Seconds the audit calls session: the span it chose, less any stretch it excluded."""
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    """Fraction of those seconds that carried a fix. The session's own figure, in the one
    place it lives -- every per-wave figure carries its own."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wave_count(self) -> int:
        """The same number L5 reached. Recomputed from these rows so the two cannot differ
        without a test noticing."""
        return len(self.waves)


class WaveLabel(BaseModel):
    """Human ground truth. Append-only: corrections are new rows (ADR-0006)."""

    t_start: float
    t_end: float
    is_wave: bool
    """False is truth too: "I looked at this stretch and it is not a ride" is what makes a
    false positive measurable rather than merely unlabelled."""
    source: LabelSource = LabelSource.HUMAN
    verified: bool = False
    direction: RideDirection = RideDirection.UNKNOWN
    note: str = ""

    @model_validator(mode="after")
    def _check_span(self) -> WaveLabel:
        if self.t_end <= self.t_start:
            msg = f"label has no duration: {self.t_start} -> {self.t_end}"
            raise ValueError(msg)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def counts_as_truth(self) -> bool:
        """Only verified, *unassisted* human labels may enter an evaluation metric.

        The source check does two jobs. It keeps unverified Connect IQ imports out
        (ADR-0006), and it keeps out labels made with L3's proposals on screen
        (ADR-0012) -- those are honest human judgements, but they are anchored to the
        detector, and scoring the detector against them measures agreement rather than
        accuracy.
        """
        return self.source is LabelSource.HUMAN and self.verified


class StoredLabel(WaveLabel):
    """A label as the store holds it: the judgement, plus where it came from and when.

    A subclass rather than a parallel shape, so the fields a labeller actually sets can
    never drift from :class:`WaveLabel`. What is added here is provenance the UI does not
    supply and the store owns.

    Nothing is ever updated or deleted (ADR-0006). A correction is a new row naming the row
    it replaces, so the record of how judgement changed survives alongside the judgement.
    """

    label_id: str
    activity_id: str
    created_at: float
    """Unix seconds. Also the tie-break for which of two labels is the later word."""
    supersedes: str | None = None
    """The ``label_id`` this row corrects, or None when it is an original."""


class LabelPass(BaseModel):
    """A completed sweep of one session by one labeller.

    This exists because "no labels" is ambiguous and the difference matters: a session
    nobody has opened and a session someone swept carefully and found no rides in look
    identical in the ``labels`` table. The blind pass is the gate on the assisted one
    (ADR-0012), so it has to be a fact we record rather than one we infer from a count.
    """

    activity_id: str
    kind: PassKind
    completed_at: float
    label_count: int = Field(ge=0)
    """How many labels the pass produced. Zero is a valid, meaningful answer."""


class SessionTrack(BaseModel):
    """What the labeling UI needs to draw a session: the frame, and both tracks.

    An envelope over the existing models, not a merged row. Joining
    :class:`SmoothedSample` and :class:`FramedSample` into one flat shape would be more
    convenient and would quietly create a third canonical form of a second of a session;
    keeping them parallel means the rotation stays visibly a rotation of the estimate.
    The two lists are index-aligned -- L2 emits one framed row per smoothed row, in
    order -- and the validator below refuses to serve them if that ever stops being true.
    """

    frame: SessionFrame
    smoothed: list[SmoothedSample]
    framed: list[FramedSample]

    @model_validator(mode="after")
    def _check_aligned(self) -> SessionTrack:
        if len(self.smoothed) != len(self.framed):
            msg = (
                f"track is not aligned: {len(self.smoothed)} smoothed rows against "
                f"{len(self.framed)} framed rows"
            )
            raise ValueError(msg)
        return self


class SessionCandidates(BaseModel):
    """L3's proposals, with the frame they were measured against.

    The envelope to :class:`SessionTrack`'s, and for the same reason the stage itself keeps
    the two together: a candidate is only as trustworthy as the axis it was measured
    against, so an unreliable frame has to travel with the proposals rather than be
    something the caller is trusted to fetch separately (ADR-0011).
    """

    frame: SessionFrame
    candidates: list[WaveCandidate]


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
