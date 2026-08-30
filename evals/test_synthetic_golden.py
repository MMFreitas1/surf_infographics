"""The detection eval gate.

Ground truth here is a generated session whose wave intervals are known exactly. It
takes no dependency on any third-party app's output (ADR-0008): those values are derived
from the same GPS we already hold, so they would contribute their errors and no
information. Real human labels arrive in Phase 4 and join this gate then.
"""

import math
from itertools import pairwise

import pytest

from surf.evaluation import Interval, score
from surf.synthetic import (
    M_PER_DEG_LAT,
    ORIGIN_LAT,
    SyntheticParams,
    make_synthetic_session,
)


def radial_error_m(sample, point):
    """Distance between a recorded fix and the true position it was drawn from."""
    lat, lon = point.lat_lon
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    return math.hypot((sample.lat - lat) * M_PER_DEG_LAT, (sample.lon - lon) * m_per_deg_lon)


def paired(session):
    """Each second's true state next to the sample recorded from it."""
    return zip(session.true_track, session.activity.samples, strict=True)


def test_generator_reproduces_the_golden_exactly(synthetic, synthetic_golden):
    """Determinism is the whole point of a seeded fixture."""
    expected = synthetic_golden["expected"]
    a = synthetic.activity
    assert len(a.samples) == expected["sample_count"]
    assert a.duration_s == expected["duration_s"]
    assert round(a.position_coverage, 6) == expected["position_coverage"]
    assert len(a.blind_windows) == expected["blind_window_count"]
    assert a.blind_seconds == expected["blind_seconds"]
    assert synthetic.wave_count == expected["wave_count"]


def test_truth_intervals_match_the_golden(synthetic, synthetic_golden):
    got = [{"t_start": i.t_start, "t_end": i.t_end} for i in synthetic.truth]
    assert got == synthetic_golden["truth_intervals"]


def test_regenerating_twice_gives_identical_output():
    a = make_synthetic_session()
    b = make_synthetic_session()
    assert [(i.t_start, i.t_end) for i in a.truth] == [(i.t_start, i.t_end) for i in b.truth]
    assert a.activity.position_coverage == b.activity.position_coverage


def test_a_different_seed_gives_a_different_session():
    a = make_synthetic_session()
    b = make_synthetic_session(SyntheticParams(seed=99))
    assert [(i.t_start, i.t_end) for i in a.truth] != [(i.t_start, i.t_end) for i in b.truth]


def test_the_fixture_resembles_a_real_session(synthetic):
    """If the fixture stops being realistic it stops being a useful gate."""
    a = synthetic.activity
    assert 0.35 <= a.position_coverage <= 0.65, "real sessions sit near 50% coverage"
    assert any(w.could_hide_a_wave() for w in a.blind_windows), "must contain wave-sized gaps"
    assert all(3.0 <= i.duration <= 30.0 for i in synthetic.truth), "rides are 3-30s"


def test_rides_do_not_overlap(synthetic):
    ordered = sorted(synthetic.truth, key=lambda i: i.t_start)
    for earlier, later in pairwise(ordered):
        assert earlier.t_end <= later.t_start


# --- the gate itself must be able to tell good from bad -------------------------


def test_a_perfect_detector_scores_one(synthetic):
    s = score(list(synthetic.truth), synthetic.truth)
    assert s.f1 == 1.0


def test_a_silent_detector_scores_zero(synthetic):
    s = score([], synthetic.truth)
    assert s.recall == 0.0
    assert s.f1 == 0.0


def test_a_detector_that_merges_every_ride_into_one_is_punished(synthetic):
    """Over-merging is a real failure mode: one long span is not many rides."""
    span = Interval(synthetic.truth[0].t_start, synthetic.truth[-1].t_end)
    s = score([span], synthetic.truth)
    assert s.true_positives <= 1
    assert s.f1 < 0.3


def test_a_detector_offset_by_a_few_seconds_still_matches(synthetic):
    """Boundaries need not be exact; the gate must tolerate small timing error."""
    shifted = [Interval(i.t_start + 1.0, i.t_end + 1.0) for i in synthetic.truth]
    s = score(shifted, synthetic.truth)
    assert s.recall == 1.0


def test_a_detector_offset_by_a_long_way_does_not_match(synthetic):
    shifted = [Interval(i.t_start + 60.0, i.t_end + 60.0) for i in synthetic.truth]
    s = score(shifted, synthetic.truth)
    assert s.true_positives == 0


# --- the true track: what a smoother is scored against --------------------------


def test_the_true_track_is_pinned_by_the_golden(synthetic, synthetic_golden):
    """Otherwise nothing in this gate would notice a changed speed profile.

    Coverage, blind windows and truth intervals all fall out of the RNG *sequence*, and
    changing `ride_peak_speed` draws exactly as many numbers as before. The kinematics
    need pinning of their own or they are unguarded.
    """
    expected = synthetic_golden["true_track"]
    speeds = [p.speed_ms for p in synthetic.true_track]
    assert len(synthetic.true_track) == expected["point_count"]
    assert round(sum(speeds), 6) == expected["path_length_m"]
    assert round(max(speeds), 6) == expected["max_speed_ms"]
    assert round(sum(speeds) / len(speeds), 6) == expected["mean_speed_ms"]


def test_the_true_track_has_a_state_for_every_second_including_blind_ones(synthetic):
    """The point of it: a smoother has to be scorable *through* a dropout, not around it."""
    assert len(synthetic.true_track) == len(synthetic.activity.samples)
    assert all(point.t == sample.t for point, sample in paired(synthetic))
    assert any(not s.has_position for s in synthetic.activity.samples), (
        "the fixture must contain dropout or this proves nothing"
    )


def test_the_recorded_speed_is_the_true_speed_wherever_there_is_a_fix(synthetic):
    for point, sample in paired(synthetic):
        if sample.has_position:
            assert sample.speed_ms == pytest.approx(point.speed_ms, abs=1e-12)


def test_positioned_samples_scatter_around_the_true_track_at_the_stated_noise(synthetic):
    """3 m per axis, so radial error is Rayleigh: mean sigma*sqrt(pi/2), about 3.76 m.

    This is what ties the exposed track to the samples. If `true_track` held the wrong
    points -- off by one second, say -- the scatter would not land on the stated noise.
    """
    noise = SyntheticParams().gps_noise_m
    errors = [radial_error_m(s, p) for p, s in paired(synthetic) if s.has_position]
    assert len(errors) > 500
    assert sum(errors) / len(errors) == pytest.approx(noise * math.sqrt(math.pi / 2), abs=0.4)
    assert max(errors) < 5 * noise


def test_the_true_track_moves_fastest_during_the_rides(synthetic):
    """The two kinds of truth must agree: the ride intervals are where the speed is."""

    def in_a_ride(t):
        return any(i.t_start <= t < i.t_end for i in synthetic.truth)

    riding = [p.speed_ms for p in synthetic.true_track if in_a_ride(p.t)]
    resting = [p.speed_ms for p in synthetic.true_track if not in_a_ride(p.t)]
    assert sum(riding) / len(riding) > 4.0 * (sum(resting) / len(resting))
