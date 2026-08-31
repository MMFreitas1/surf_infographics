"""Human labels entering the metric, on exactly the path the synthetic golden uses.

Phase 4's whole point is that a number can finally mean something about surfing rather than
about `surf.synthetic`. That only holds if human truth reaches `score` through the same code
the generator's truth does — a second scoring path would be a second definition of "correct",
and the two would drift.

Nothing here gates on a human-labelled session, because CI has none and never will: activity
files are personal and gitignored. What is gated is the *join* — the filtering, the coverage
comparison and the scoring — using labels seeded in a temp store.
"""

from __future__ import annotations

import pytest

from surf.evaluation import Interval, rejected_intervals, score, truth_intervals
from surf.models import LabelSource, RideDirection, SmoothedSample, WaveCandidate, WaveLabel
from surf.report import (
    MIN_RIDES_FOR_A_VERDICT,
    build_report,
    compare_coverage,
    coverage_of,
    format_report,
)


def label(t_start, t_end, **overrides: object) -> WaveLabel:
    """A verified human ride label unless told otherwise."""
    fields = {"is_wave": True, "verified": True} | overrides
    return WaveLabel(t_start=t_start, t_end=t_end, **fields)


def track(flags: list[bool], t0: float = 0.0) -> list[SmoothedSample]:
    """A track whose only interesting property is which seconds carried a fix."""
    return [
        SmoothedSample(
            t=t0 + i,
            lat=38.0,
            lon=-9.0,
            vx_ms=0.0,
            vy_ms=0.0,
            position_sigma_m=2.0 if observed else 20.0,
            confidence=0.9 if observed else 0.2,
            observed=observed,
        )
        for i, observed in enumerate(flags)
    ]


# -- the filter: what may and may not enter a metric --------------------------------------


def test_only_verified_unassisted_human_rides_become_truth():
    rows = [
        label(0, 6),
        label(10, 16, verified=False),
        label(20, 26, source=LabelSource.HUMAN_ASSISTED),
        label(30, 36, source=LabelSource.CIQ_BOOTSTRAP),
        label(40, 46, is_wave=False),
    ]
    assert truth_intervals(rows) == [Interval(0.0, 6.0)]


def test_rejections_are_kept_separately_rather_than_discarded():
    """A stretch someone examined and ruled out is evidence, and not the same as silence."""
    rows = [label(0, 6), label(40, 46, is_wave=False)]
    assert rejected_intervals(rows) == [Interval(40.0, 46.0)]
    assert rejected_intervals([label(40, 46, is_wave=False, verified=False)]) == []


def test_a_correction_only_counts_once_the_superseded_row_is_filtered_out():
    """The store's `current=True` view is what does this; truth_intervals trusts its input.

    Pinned here because getting it wrong would silently double-count every corrected ride
    and quietly inflate recall.
    """
    original = label(10, 16)
    corrected = label(11, 19)
    assert len(truth_intervals([original, corrected])) == 2
    assert len(truth_intervals([corrected])) == 1


# -- the standing hypothesis --------------------------------------------------------------


def test_coverage_during_rides_is_measured_against_the_session_not_in_isolation():
    rows = track([True] * 10 + [False] * 30)  # session: 25% observed
    rides = [Interval(0.0, 10.0)]  # entirely inside the observed stretch
    comparison = compare_coverage(rows, rides)

    assert comparison is not None
    assert comparison.ride_coverage == 1.0
    assert comparison.session_coverage == 0.25
    assert comparison.lift == pytest.approx(0.75)


def test_the_verdict_refuses_to_speak_from_too_few_rides():
    """Three rides can point anywhere. A tool that says "confirmed" off three teaches you
    to trust it wrongly."""
    rows = track([True] * 20 + [False] * 20)
    few = compare_coverage(rows, [Interval(0.0, 4.0)])
    assert few is not None
    assert "too few" in few.verdict

    many = compare_coverage(rows, [Interval(float(i), i + 2.0) for i in range(0, 20, 2)])
    assert many is not None
    assert many.rides >= MIN_RIDES_FOR_A_VERDICT
    assert "too few" not in many.verdict


def test_the_verdict_names_the_opposite_result_rather_than_hiding_it():
    """If rides turn out worse observed, that is a product fact, not a bug to bury."""
    rows = track([True] * 30 + [False] * 30)
    rides = [Interval(float(t), t + 2.0) for t in range(30, 50, 2)]  # all in the blind half
    comparison = compare_coverage(rows, rides)

    assert comparison is not None
    assert comparison.lift < 0
    assert "opposite of the hypothesis" in comparison.verdict


def test_no_rides_means_no_comparison_rather_than_a_zero():
    assert compare_coverage(track([True, False]), []) is None
    assert compare_coverage([], [Interval(0.0, 6.0)]) is None
    assert coverage_of(track([True, True]), [Interval(90.0, 99.0)]) == (0, 0.0)


# -- the join, end to end -----------------------------------------------------------------


def test_candidates_are_scored_against_human_truth_through_the_same_scorer():
    rows = track([True] * 60)
    labels = [label(10, 20), label(30, 40)]
    candidates = [
        WaveCandidate(t_start=10.0, t_end=20.0, direction=RideDirection.UNKNOWN),
        WaveCandidate(t_start=50.0, t_end=56.0),
    ]

    report = build_report("a1", rows, labels, candidates)
    direct = score([Interval(c.t_start, c.t_end) for c in candidates], truth_intervals(labels))

    assert report.scores == direct
    assert report.scores is not None
    assert report.scores.recall == 0.5
    assert report.scores.precision == 0.5


def test_a_proposal_on_a_rejected_stretch_is_a_confirmed_false_positive():
    """Unmatched only means unlabelled. This one is wrong on the record."""
    rows = track([True] * 60)
    labels = [label(10, 20), label(40, 50, is_wave=False)]
    candidates = [WaveCandidate(t_start=40.0, t_end=50.0)]

    report = build_report("a1", rows, labels, candidates)
    assert report.confirmed_false_positives == 1


def test_the_report_counts_what_exists_apart_from_what_counts():
    rows = track([True] * 60)
    labels = [
        label(10, 20),
        label(30, 40, source=LabelSource.HUMAN_ASSISTED),
        label(45, 50, verified=False),
    ]
    report = build_report("a1", rows, labels, [])

    assert report.labels_total == 3
    assert report.rides == 1
    assert report.assisted == 1
    assert report.uncounted == 2


def test_an_unlabelled_session_reports_that_rather_than_a_number():
    """Reporting recall 1.0 against zero labels would be the most misleading output here."""
    report = build_report("a1", track([True] * 10), [], [WaveCandidate(t_start=1, t_end=5)])
    assert report.scores is None
    assert report.coverage is None

    text = format_report(report)
    assert "no labelled rides yet" in text
    assert "no human truth on this session yet" in text


def test_the_report_reads_as_sentences_a_person_can_act_on():
    rows = track([True] * 20 + [False] * 20)
    labels = [label(float(t), t + 2.0) for t in range(0, 20, 2)]
    text = format_report(build_report("abc123", rows, labels, []))

    assert "session abc123" in text
    assert "during rides" in text
    assert "whole session" in text
    assert "lift" in text


# -- the command a person actually runs ---------------------------------------------------


def test_the_cli_reports_an_empty_store_without_failing(tmp_path, monkeypatch, capsys):
    """`make labels` before anything is ingested is a fair question with a plain answer."""
    from surf.report import main

    monkeypatch.setenv("SURF_DATA_DIR", str(tmp_path))
    assert main([]) == 0
    assert "no sessions stored" in capsys.readouterr().out


def test_asking_for_a_session_that_is_not_there_does_fail(tmp_path, monkeypatch, capsys):
    from surf.report import main

    monkeypatch.setenv("SURF_DATA_DIR", str(tmp_path))
    assert main(["nope"]) == 1
    assert "no session matching" in capsys.readouterr().out
