"""Known-answer tests for the evaluation metrics themselves.

If the scorer is wrong, every number the project reports is wrong. These are the
tests that keep the gate honest.
"""

import pytest

from surf.evaluation import Interval, iou, match_intervals, score


def test_identical_intervals_have_iou_one():
    assert iou(Interval(0, 10), Interval(0, 10)) == 1.0


def test_disjoint_intervals_have_iou_zero():
    assert iou(Interval(0, 10), Interval(20, 30)) == 0.0


def test_touching_intervals_do_not_overlap():
    assert iou(Interval(0, 10), Interval(10, 20)) == 0.0


def test_half_overlap():
    # intersection 5, union 15
    assert iou(Interval(0, 10), Interval(5, 15)) == pytest.approx(5 / 15)


def test_interval_rejects_reversed_bounds():
    with pytest.raises(ValueError, match="ends before it starts"):
        Interval(10, 5)


def test_perfect_detection_scores_one():
    truths = [Interval(0, 10), Interval(50, 60)]
    s = score(list(truths), truths)
    assert (s.precision, s.recall, s.f1) == (1.0, 1.0, 1.0)


def test_a_missed_wave_costs_recall_not_precision():
    truths = [Interval(0, 10), Interval(50, 60)]
    s = score([Interval(0, 10)], truths)
    assert s.true_positives == 1
    assert s.false_negatives == 1
    assert s.precision == 1.0
    assert s.recall == pytest.approx(0.5)


def test_a_phantom_wave_costs_precision_not_recall():
    """The incumbent app's failure mode. It must show up as low precision."""
    truths = [Interval(0, 10)]
    s = score([Interval(0, 10), Interval(100, 130)], truths)
    assert s.false_positives == 1
    assert s.precision == pytest.approx(0.5)
    assert s.recall == 1.0


def test_each_prediction_matches_at_most_one_truth():
    """One long detection spanning two rides must not count as two hits."""
    truths = [Interval(0, 10), Interval(11, 20)]
    result = match_intervals([Interval(0, 20)], truths, min_iou=0.3)
    assert len(result.matched) == 1
    assert len(result.unmatched_truths) == 1


def test_low_overlap_is_not_a_match():
    result = match_intervals([Interval(0, 10)], [Interval(9, 30)], min_iou=0.3)
    assert result.matched == []
    assert result.unmatched_predictions == [0]
    assert result.unmatched_truths == [0]


def test_matching_is_deterministic_under_ties():
    preds = [Interval(0, 10), Interval(0, 10)]
    truths = [Interval(0, 10), Interval(0, 10)]
    first = match_intervals(preds, truths)
    for _ in range(5):
        assert match_intervals(preds, truths) == first


def test_empty_inputs_do_not_divide_by_zero():
    """Nothing to find and nothing found is vacuously perfect, not a crash."""
    s = score([], [])
    assert (s.precision, s.recall, s.f1) == (1.0, 1.0, 1.0)


def test_a_detector_that_outputs_nothing_scores_zero_f1():
    s = score([], [Interval(0, 10)])
    assert s.precision == 1.0
    assert s.recall == 0.0
    assert s.f1 == 0.0
