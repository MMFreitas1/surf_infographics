"""Canonical model invariants -- including the project's honesty rules."""

import pytest
from pydantic import ValidationError

from surf.models import (
    Activity,
    BlindCause,
    BlindWindow,
    Fidelity,
    LabelSource,
    Sample,
    WaveLabel,
)


def test_sample_without_position_is_valid():
    """Half of a real session has no fix. That is data, not an error."""
    s = Sample(t=1.0, hr_bpm=110)
    assert s.has_position is False
    assert s.hr_bpm == 110


def test_sample_with_position_reports_it():
    assert Sample(t=1.0, lat=37.909, lon=-8.802).has_position is True


def test_sample_rejects_impossible_latitude():
    with pytest.raises(ValidationError):
        Sample(t=1.0, lat=91.0, lon=0.0)


def test_blind_window_duration_and_wave_hiding():
    short = BlindWindow(t_start=0.0, t_end=3.0, cause=BlindCause.NO_FIX)
    long = BlindWindow(t_start=0.0, t_end=44.0, cause=BlindCause.NO_FIX)
    assert short.duration_s == 3.0
    assert short.could_hide_a_wave() is False
    assert long.could_hide_a_wave() is True


def test_blind_window_rejects_reversed_bounds():
    with pytest.raises(ValidationError):
        BlindWindow(t_start=10.0, t_end=5.0)


def test_bootstrap_labels_never_count_as_truth():
    """ADR-0006: only verified human labels may enter a metric."""
    ciq = WaveLabel(t_start=0, t_end=10, is_wave=True, source=LabelSource.CIQ_BOOTSTRAP)
    unverified_human = WaveLabel(t_start=0, t_end=10, is_wave=True)
    verified_human = WaveLabel(t_start=0, t_end=10, is_wave=True, verified=True)
    assert ciq.counts_as_truth is False
    assert unverified_human.counts_as_truth is False
    assert verified_human.counts_as_truth is True


def test_verified_flag_alone_does_not_promote_bootstrap_labels():
    ciq = WaveLabel(
        t_start=0, t_end=10, is_wave=True, source=LabelSource.CIQ_BOOTSTRAP, verified=True
    )
    assert ciq.counts_as_truth is False


def test_activity_coverage_matches_the_reference_session_shape():
    """A surfing session is expected to sit near 50% position coverage."""
    samples = [
        Sample(t=float(i), lat=37.9 if i % 2 == 0 else None, lon=-8.8 if i % 2 == 0 else None)
        for i in range(10)
    ]
    act = Activity(
        activity_id="x", sport="surfing", start_time=0.0, fidelity=Fidelity.FIT, samples=samples
    )
    assert act.position_coverage == pytest.approx(0.5)
    assert act.duration_s == pytest.approx(9.0)


def test_empty_activity_has_zero_coverage_not_a_crash():
    act = Activity(activity_id="x", sport="surfing", start_time=0.0, fidelity=Fidelity.GPX)
    assert act.position_coverage == 0.0
    assert act.duration_s == 0.0
    assert act.blind_seconds == 0.0
