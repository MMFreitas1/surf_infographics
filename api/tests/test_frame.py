"""L2, the shore frame.

The estimator's whole claim is that it uses speed for *relative* weighting only, never as a
threshold, so the two properties worth pinning hardest are that scaling every velocity
changes nothing and that rotating the session rotates the answer with it. The rest of this
file is about the two ways a bearing can be wrong while looking right: the votes can
disagree, or they can agree because one second is doing all the voting.
"""

import math
import random

import pytest

from surf import coast as coastline
from surf.models import AngleSource, AuditReport, SignSource, SmoothedSample
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import (
    FramedTrack,
    FrameInput,
    FrameStage,
    PayloadError,
    estimate_bearing,
)
from surf.synthetic import (
    ORIGIN_LAT,
    ORIGIN_LON,
    SyntheticParams,
    coastline_at,
    make_synthetic_session,
)

TRUE_SHORE_DEG = 90.0
"""The synthetic generator puts the shore due east, and rides travel +x toward it."""

TOLERANCE_DEG = 5.0
"""The error we accept on a session the estimator declares reliable. Stated, not implied."""


def bearing_error(bearing_deg: float, truth_deg: float = TRUE_SHORE_DEG) -> float:
    """Signed difference between two bearings, wrapped into [-180, 180)."""
    return ((bearing_deg - truth_deg + 180.0) % 360.0) - 180.0


def track_from(velocities, confidence: float = 0.9) -> list[SmoothedSample]:
    """A synthetic L1 track carrying the given velocities."""
    return [
        SmoothedSample(
            t=float(i),
            lat=ORIGIN_LAT + i * 1e-6,
            lon=ORIGIN_LON + i * 1e-6,
            vx_ms=vx,
            vy_ms=vy,
            position_sigma_m=2.0,
            confidence=confidence,
            observed=True,
        )
        for i, (vx, vy) in enumerate(velocities)
    ]


def rideless_track(seed: int = 11, n: int = 600) -> list[SmoothedSample]:
    """Paddling out and back with no rides: headings that largely cancel."""
    rng = random.Random(seed)
    velocities = []
    for i in range(n):
        heading = 0.0 if (i // 60) % 2 == 0 else math.pi
        angle = rng.gauss(heading, 0.5)
        speed = rng.uniform(0.5, 1.1)
        velocities.append((speed * math.cos(angle), speed * math.sin(angle)))
    return track_from(velocities)


def synthetic_track(n_waves: int = 8):
    """A generated session, smoothed by L1, ready for L2."""
    session = make_synthetic_session(SyntheticParams(n_waves=n_waves))
    return session, KinematicsStage().run(session.activity)


# -- the bearing ----------------------------------------------------------------------


def test_the_bearing_finds_the_shore_the_generator_used():
    _, track = synthetic_track()
    frame = FrameStage().run(track).frame
    assert frame.reliable
    assert abs(bearing_error(frame.shore_bearing_deg)) < TOLERANCE_DEG


def test_scaling_every_velocity_leaves_the_bearing_exactly_where_it_was():
    """The property the whole estimator rests on.

    Phase 2 measured smoothed top-end speed swinging 11.55 -> 8.50 m/s across the
    ``measurement_noise_m`` sweep. If the bearing moved when speeds scaled, it would be
    tuned to that assumed noise level rather than to surfing. It does not move.
    """
    _, track = synthetic_track()
    scaled = [s.model_copy(update={"vx_ms": s.vx_ms * 7.3, "vy_ms": s.vy_ms * 7.3}) for s in track]
    assert estimate_bearing(scaled).bearing_deg == pytest.approx(
        estimate_bearing(track).bearing_deg, abs=1e-9
    )


def test_rotating_the_session_rotates_the_bearing_with_it():
    _, track = synthetic_track()
    theta = math.radians(37.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    turned = [
        s.model_copy(
            update={
                "vx_ms": s.vx_ms * cos_t - s.vy_ms * sin_t,
                "vy_ms": s.vx_ms * sin_t + s.vy_ms * cos_t,
            }
        )
        for s in track
    ]
    # Rotating east/north counter-clockwise by theta turns a compass bearing *down* by it.
    moved = bearing_error(estimate_bearing(turned).bearing_deg, estimate_bearing(track).bearing_deg)
    assert moved == pytest.approx(-37.0, abs=1e-6)


# -- the two ways a bearing goes wrong -------------------------------------------------


def test_a_session_with_no_rides_is_reported_unreliable():
    """Nothing points shoreward on a flat day, and the honest answer is to say so."""
    frame = FrameStage().run(rideless_track()).frame
    assert not frame.reliable
    assert frame.coherence < 0.15


def test_one_fast_second_cannot_speak_for_a_whole_session():
    """Coherence alone is fooled by concentration; the effective sample size is not.

    A single 6 m/s spike in an otherwise aimless session scores ~0.9 coherence, because
    almost all the weight sits on that one second and it trivially agrees with itself.
    """
    rng = random.Random(11)
    drift = []
    for _ in range(600):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        speed = rng.uniform(0.2, 1.0)
        drift.append((speed * math.cos(angle), speed * math.sin(angle)))
    drift[300] = (6.0, 0.0)

    frame = FrameStage().run(track_from(drift)).frame
    assert frame.coherence > 0.85, "the spike really does look coherent"
    assert frame.effective_seconds < 2.0, "and it rests on almost nothing"
    assert not frame.reliable


def test_too_few_waves_is_not_enough_to_call_the_shore():
    """One ride cannot outvote a session of paddling, and the frame admits it.

    Measured: at one wave the bearing is 24 degrees out, outside the tolerance this stage
    claims. It is rejected rather than reported.
    """
    _, track = synthetic_track(n_waves=1)
    assert not FrameStage().run(track).frame.reliable


def test_every_frame_it_calls_reliable_is_inside_the_stated_tolerance():
    """The guards are only worth anything if they gate on accuracy. Sweep and check."""
    for n_waves in (1, 2, 3, 4, 6, 8, 12):
        _, track = synthetic_track(n_waves=n_waves)
        frame = FrameStage().run(track).frame
        if frame.reliable:
            assert abs(bearing_error(frame.shore_bearing_deg)) < TOLERANCE_DEG, (
                f"{n_waves} waves: called reliable but is "
                f"{bearing_error(frame.shore_bearing_deg):.1f} deg out"
            )


# -- the rotation ---------------------------------------------------------------------


def test_the_rotation_preserves_speed():
    """A rotation cannot change how fast anyone was going."""
    _, track = synthetic_track()
    framed = FrameStage().run(track).samples
    for smoothed, rotated in zip(track, framed, strict=True):
        assert rotated.speed_ms == pytest.approx(smoothed.speed_ms, abs=1e-9)


def test_rides_travel_toward_the_shore_not_away_from_it():
    """The sign convention, checked where the generator says a ride actually happened."""
    session, track = synthetic_track()
    framed = FrameStage().run(track).samples
    by_t = {s.t: s for s in framed}
    for interval in session.truth:
        during = [by_t[t] for t in by_t if interval.t_start <= t < interval.t_end]
        mean_cross = sum(s.v_cross_ms for s in during) / len(during)
        assert mean_cross > 0.0, f"ride at {interval.t_start} travels seaward"


def test_the_frame_is_right_handed():
    """Alongshore is shoreward turned 90 degrees to the *left*, and the sign has to be real.

    Checked against the stage's own output rather than by recomputing the axes from the
    bearing -- recomputing them here would reproduce whatever convention the code chose and
    agree with it either way. With the shore due east, a second spent heading due north is
    moving along the shore to the left, so its alongshore velocity is positive.
    """
    velocities = [(5.0, 0.0)] * 100 + [(0.0, 1.0)]
    out = FrameStage().run(track_from(velocities))

    assert abs(bearing_error(out.frame.shore_bearing_deg)) < 0.1, "shore should come out east"
    heading_north = out.samples[-1]
    assert heading_north.v_cross_ms == pytest.approx(0.0, abs=1e-3)
    assert heading_north.v_along_ms == pytest.approx(1.0, abs=1e-3)

    heading_east = out.samples[0]
    assert heading_east.v_cross_ms == pytest.approx(5.0, abs=1e-3)
    assert heading_east.v_along_ms == pytest.approx(0.0, abs=1e-3)


def test_confidence_and_observed_survive_the_rotation():
    """ADR-0010's line has to reach the candidates, so it cannot be dropped here."""
    _, track = synthetic_track()
    framed = FrameStage().run(track).samples
    assert [s.observed for s in framed] == [s.observed for s in track]
    assert [s.confidence for s in framed] == [s.confidence for s in track]


# -- degenerate input and the payload ---------------------------------------------------


def test_an_empty_track_yields_a_frame_that_admits_it_knows_nothing():
    out = FrameStage().run([])
    assert out.samples == []
    assert not out.frame.reliable
    assert out.frame.contributing_seconds == 0


def test_a_motionless_session_has_no_heading_to_offer():
    out = FrameStage().run(track_from([(0.0, 0.0)] * 50))
    assert not out.frame.reliable
    assert out.frame.coherence == 0.0


def test_the_payload_round_trips_the_frame_as_well_as_the_rows():
    """A cache hit must return what a run returned -- frame included, not just samples."""
    stage = FrameStage()
    _, track = synthetic_track()
    out = stage.run(track)
    back: FramedTrack = stage.decode(stage.encode(out))
    assert back.frame == out.frame
    assert back.samples == out.samples


def test_a_payload_this_stage_did_not_write_is_refused():
    stage = FrameStage()
    naked = KinematicsStage().encode(KinematicsStage().run(make_synthetic_session().activity))
    with pytest.raises(PayloadError):
        stage.decode(naked)


# -- two witnesses for the angle, and a separate one for the sign (ADR-0022) -------------

M_PER_DEG_LAT = 111_320.0


def at(east_m: float, north_m: float) -> tuple[float, float]:
    """Metres east/north of the synthetic origin, as degrees."""
    per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    return ORIGIN_LAT + north_m / M_PER_DEG_LAT, ORIGIN_LON + east_m / per_deg_lon


def placed(east_m: float, north_m: float, t: float, *, vx=0.0, vy=0.0) -> SmoothedSample:
    lat, lon = at(east_m, north_m)
    return SmoothedSample(
        t=t,
        lat=lat,
        lon=lon,
        vx_ms=vx,
        vy_ms=vy,
        position_sigma_m=2.0,
        confidence=0.9,
        observed=True,
    )


def session_with_walk(walk_east_m: float, *, rides: bool = True):
    """A session at the origin with a walk parked at a chosen offset, positions integrated.

    Integrated rather than scattered, because the sign witnesses read *displacement*: a
    fixture whose velocities and positions disagree would let the ride-majority test pass
    while measuring nothing. Each ride runs shoreward and the paddling between them cancels
    it, so the session stays put and the walk stays separable.

    The walk is what fixes the sign. It is on land, so shoreward is the perpendicular
    pointing toward it; parking it due east or due west is the cleanest way to ask whether
    the stage reads it, because the synthetic coast runs north-south.
    """
    rng = random.Random(5)
    track = [placed(walk_east_m, i * 2.0, float(i)) for i in range(40)]

    x = y = 0.0
    for i in range(400):
        if rides and i % 100 >= 80:
            vx, vy = 5.0, rng.gauss(0.0, 0.4)
        else:
            heading = 0.0 if (i // 20) % 2 == 0 else math.pi
            angle = rng.gauss(heading, 0.6)
            speed = rng.uniform(0.8, 1.7)
            vx, vy = speed * math.cos(angle), speed * math.sin(angle)
        x += vx
        y += vy
        track.append(placed(x, y, 100.0 + i, vx=vx, vy=vy))

    audit = AuditReport(
        window_s=30.0,
        t_start=0.0,
        t_end=600.0,
        surfing_t_start=100.0,
        surfing_t_end=500.0,
    )
    return track, audit


@pytest.mark.parametrize("coast_axis_deg", [0.0, 30.0, 90.0, 165.3])
def test_a_synthetic_coast_at_a_known_angle_gives_a_known_shore_bearing(coast_axis_deg):
    """The known-answer test for the primary estimator, and the reason
    `synthetic.coastline_at` exists: the committed extract never reaches this origin, so
    without an injectable coast this path is green because it is never run."""
    track, audit = session_with_walk(walk_east_m=300.0)
    stage = FrameStage(coast=coastline_at(coast_axis_deg))

    frame = stage.run(FrameInput(track=track, audit=audit)).frame

    assert frame.angle_source is AngleSource.COASTLINE
    assert frame.coast is not None
    assert frame.coast.bearing_deg == pytest.approx(coast_axis_deg, abs=0.2)
    # Shoreward is perpendicular to the coast, on whichever side the walk sits.
    assert min(
        abs(bearing_error(frame.shore_bearing_deg, (coast_axis_deg + turn) % 360.0))
        for turn in (90.0, 270.0)
    ) == pytest.approx(0.0, abs=0.3)


def test_the_angle_falls_through_to_velocity_where_the_coastline_does_not_reach():
    """The synthetic origin is over 5 km offshore of the committed extract, by design."""
    _, track = synthetic_track()

    frame = FrameStage().run(track).frame

    assert frame.angle_source is AngleSource.VELOCITY
    assert frame.coast is None
    assert frame.disagreement_deg is None


def test_a_missing_extract_is_a_missing_witness_not_a_broken_session(monkeypatch):
    """A coastline that cannot be read costs the frame a witness. It does not raise."""

    def boom(*args: object, **kwargs: object) -> None:
        raise coastline.CoastlineError("gone")

    monkeypatch.setattr(coastline, "bearing_near", boom)
    track, audit = session_with_walk(walk_east_m=300.0)

    frame = FrameStage().run(FrameInput(track=track, audit=audit)).frame

    assert frame.angle_source is AngleSource.VELOCITY


def test_the_walk_decides_which_way_is_shoreward():
    """All of the reference session's 489 observed walking seconds fall on one side."""
    track, audit = session_with_walk(walk_east_m=300.0)

    frame = FrameStage(coast=coastline_at(0.0)).run(FrameInput(track=track, audit=audit)).frame

    assert frame.sign_source is SignSource.WALK
    assert bearing_error(frame.shore_bearing_deg, 90.0) == pytest.approx(0.0, abs=0.3)


def test_a_walk_on_the_other_side_turns_the_bearing_right_around():
    """The sharpest form of the claim: the angle is identical, the sign is opposite."""
    east = (
        FrameStage(coast=coastline_at(0.0))
        .run(FrameInput(*session_with_walk(walk_east_m=300.0)))
        .frame
    )
    west = (
        FrameStage(coast=coastline_at(0.0))
        .run(FrameInput(*session_with_walk(walk_east_m=-300.0)))
        .frame
    )

    assert east.coast.bearing_deg == pytest.approx(west.coast.bearing_deg, abs=0.01)
    assert abs(bearing_error(east.shore_bearing_deg, west.shore_bearing_deg)) == pytest.approx(
        180.0, abs=0.3
    )


def test_without_an_audit_the_sign_falls_to_the_rides():
    """Weaker, and recorded as weaker: it reads the same evidence velocity does."""
    track, _ = session_with_walk(walk_east_m=300.0)

    frame = FrameStage(coast=coastline_at(0.0)).run(FrameInput(track=track)).frame

    assert frame.sign_source is SignSource.RIDES
    assert bearing_error(frame.shore_bearing_deg, 90.0) == pytest.approx(0.0, abs=0.3)


def test_with_no_walk_and_no_rides_the_axis_stands_but_no_side_is_claimed():
    """A rotation still has to happen for the track to be expressible. Marking it is what
    stops the arbitrary choice from reading as a measurement."""
    track, _ = session_with_walk(walk_east_m=300.0, rides=False)
    session_only = [s for s in track if s.t >= 100.0]

    frame = FrameStage(coast=coastline_at(0.0)).run(FrameInput(track=session_only)).frame

    assert frame.sign_source is SignSource.NONE
    assert not frame.reliable


# -- reliability is agreement (ADR-0022) -------------------------------------------------


def test_coherence_no_longer_decides_whether_the_frame_is_trusted():
    """The headline of ADR-0022, as a test, and put the sharp way.

    The reference session scores 0.365 coherence -- far below ADR-0011's 0.85 gate -- and
    its bearing is right to 4.2 degrees. Coherence asks whether the velocity votes agree
    *with each other*, which on a session that is four-fifths paddling they do not, even
    when their sum is correct. So this sets the old gate to a value nothing can ever clear
    and shows the frame is trusted anyway, because the two witnesses agree. Nothing about
    the fixture's noise is doing the work.
    """
    track, audit = session_with_walk(walk_east_m=300.0)
    impossible = FrameStage(coast=coastline_at(0.0), min_coherence=1.1)

    frame = impossible.run(FrameInput(track=track, audit=audit)).frame

    assert frame.coherence < impossible.min_coherence
    assert frame.disagreement_deg is not None
    assert frame.disagreement_deg <= impossible.max_disagreement_deg
    assert frame.reliable

    # Take the second witness away and ADR-0011's gate is back in charge, and refuses.
    alone = FrameStage(use_coastline=False, min_coherence=1.1)
    assert not alone.run(FrameInput(track=track, audit=audit)).frame.reliable


def test_two_witnesses_that_disagree_refuse_the_frame():
    """A coast at right angles to where the session says the shore is. One of them is
    describing somewhere else, and the frame must not pick a favourite."""
    track, audit = session_with_walk(walk_east_m=300.0)

    frame = FrameStage(coast=coastline_at(90.0)).run(FrameInput(track=track, audit=audit)).frame

    assert frame.disagreement_deg > 25.0
    assert not frame.reliable


def test_the_disagreement_is_measured_between_axes_not_directions():
    """Folding the sign in would make two estimators that agree perfectly about the beach
    look 180 degrees apart."""
    for walk in (300.0, -300.0):
        track, audit = session_with_walk(walk_east_m=walk)

        frame = FrameStage(coast=coastline_at(0.0)).run(FrameInput(track=track, audit=audit)).frame

        assert frame.disagreement_deg <= 90.0
        assert frame.disagreement_deg < 25.0


def test_velocity_alone_still_faces_both_of_adr_0011_guards():
    """Where the coastline is absent nothing has changed: a lone velocity estimate can be
    fooled by concentration, and no coastline is there to catch it."""
    frame = FrameStage().run(rideless_track()).frame

    assert frame.angle_source is AngleSource.VELOCITY
    assert frame.disagreement_deg is None
    assert not frame.reliable


# -- the key ------------------------------------------------------------------------------


def test_the_coastline_digest_is_in_the_stage_key():
    """A bearing can never be served under a coastline it was not computed from."""
    one = FrameStage(coast=coastline_at(0.0)).meta.params
    other = FrameStage(coast=coastline_at(30.0)).meta.params

    assert one["coast_sha256"] != other["coast_sha256"]
    assert FrameStage(use_coastline=False).meta.params["coast_sha256"] == ""


def test_the_audit_key_travels_in_the_params():
    """ADR-0015's pattern, now at L2 as well as L6: the walk decides the sign, so a
    different audit is a different frame -- but the audit changes no sample, so L0.6 must
    not sit in front of L1."""
    params = FrameStage(audit_key="abc123").meta.params

    assert params["audit_key"] == "abc123"
    assert FrameStage().meta.params["audit_key"] == ""
    assert params != FrameStage().meta.params
