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

from surf.models import SmoothedSample
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FramedTrack, FrameStage, PayloadError, estimate_bearing
from surf.synthetic import ORIGIN_LAT, ORIGIN_LON, SyntheticParams, make_synthetic_session

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
