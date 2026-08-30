"""The detection eval gate.

Ground truth here is a generated session whose wave intervals are known exactly. It
takes no dependency on any third-party app's output (ADR-0008): those values are derived
from the same GPS we already hold, so they would contribute their errors and no
information. Real human labels arrive in Phase 4 and join this gate then.
"""

from itertools import pairwise

from surf.evaluation import Interval, score
from surf.synthetic import SyntheticParams, make_synthetic_session


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
