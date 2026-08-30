"""Goldens pinning the reference session.

CI never holds `sample_data/` -- the files carry a real GPS trace and this repo is public --
so every test here skips there. They are the tests that run locally before a merge.

The strongest assertion in the file is the cross-check: the FIT and the GPX are parsed by
completely separate code down completely separate paths (positions absent from records
versus records absent from the file) and must still agree on how much of the session was
blind. Only a correct bounds convention makes that true.
"""

import json
from pathlib import Path

import pytest

from surf.ingest import parse_file
from surf.models import BlindCause, Fidelity

GOLDEN = json.loads((Path(__file__).parent / "goldens" / "reference_session.json").read_text())


@pytest.fixture
def fit_activity(sample_fit):
    return parse_file(sample_fit)


@pytest.fixture
def gpx_activity(sample_gpx):
    return parse_file(sample_gpx)


def summarise(activity):
    """The same aggregates the golden records. Never a coordinate."""
    speeds = [s.speed_ms for s in activity.samples if s.speed_ms is not None]
    distances = [s.distance_m for s in activity.samples if s.distance_m is not None]
    return {
        "activity_id": activity.activity_id,
        "sport": activity.sport,
        "device": activity.device,
        "fidelity": activity.fidelity.value,
        "start_time": activity.start_time,
        "sample_count": len(activity.samples),
        "positioned_count": sum(1 for s in activity.samples if s.has_position),
        "position_coverage": activity.position_coverage,
        "span_s": activity.duration_s,
        "blind_window_count": len(activity.blind_windows),
        "no_fix_window_count": sum(
            1 for w in activity.blind_windows if w.cause is BlindCause.NO_FIX
        ),
        "missing_record_window_count": sum(
            1 for w in activity.blind_windows if w.cause is BlindCause.MISSING_RECORD
        ),
        "blind_seconds": activity.blind_seconds,
        "windows_over_5s": sum(1 for w in activity.blind_windows if w.could_hide_a_wave()),
        "longest_blind_window_s": max(w.duration_s for w in activity.blind_windows),
        "heart_rate_count": sum(1 for s in activity.samples if s.hr_bpm is not None),
        "speed_count": len(speeds),
        "max_speed_ms": max(speeds) if speeds else None,
        "final_distance_m": distances[-1] if distances else None,
    }


def test_fit_matches_the_golden(fit_activity):
    assert summarise(fit_activity) == GOLDEN["fit"]


def test_gpx_matches_the_golden(gpx_activity):
    assert summarise(gpx_activity) == GOLDEN["gpx"]


def test_fit_and_gpx_agree_on_how_much_of_the_session_was_blind(fit_activity, gpx_activity):
    """Two files, two derivations, one answer -- or the bounds convention is wrong."""
    assert fit_activity.blind_seconds == gpx_activity.blind_seconds
    assert len(fit_activity.blind_windows) == len(gpx_activity.blind_windows)
    assert fit_activity.duration_s == gpx_activity.duration_s


def test_the_gpx_holds_exactly_the_fits_positioned_records(fit_activity, gpx_activity):
    """The export keeps the fixes and drops everything else, including good HR and distance."""
    positioned = sum(1 for s in fit_activity.samples if s.has_position)
    assert len(gpx_activity.samples) == positioned
    assert gpx_activity.position_coverage == 1.0  # every survivor has a fix, by construction


def test_the_gpx_loses_data_the_fit_kept(fit_activity, gpx_activity):
    """ADR-0002: this is why FIT is primary and GPX is labelled degraded."""
    assert all(s.speed_ms is None for s in gpx_activity.samples)
    assert all(s.distance_m is None for s in gpx_activity.samples)
    fit_hr = sum(1 for s in fit_activity.samples if s.hr_bpm is not None)
    gpx_hr = sum(1 for s in gpx_activity.samples if s.hr_bpm is not None)
    assert fit_hr > gpx_hr


def test_about_half_the_session_has_no_position(fit_activity):
    """The property of the sport this whole project is built around."""
    assert 0.45 < fit_activity.position_coverage < 0.55
    assert fit_activity.fidelity is Fidelity.FIT


def test_blind_seconds_equal_the_samples_that_carry_no_fix(fit_activity):
    """No imputation anywhere: every blind second is one we actually failed to observe."""
    blind_samples = sum(1 for s in fit_activity.samples if not s.has_position)
    gap_seconds = sum(
        w.duration_s for w in fit_activity.blind_windows if w.cause is BlindCause.MISSING_RECORD
    )
    assert fit_activity.blind_seconds == blind_samples + gap_seconds


def test_the_recording_is_one_second_longer_than_the_watch_reports(fit_activity):
    """A real, small disagreement in the file, pinned rather than smoothed over.

    Record timestamps span 3790 s; the session message reports 3789.019 s elapsed. The
    difference is a single dropped record 16 s in, which our derivation surfaces as a
    one-second MISSING_RECORD window.
    """
    reported = GOLDEN["device_reported"]["elapsed_s"]
    assert fit_activity.duration_s == pytest.approx(reported, abs=1.0)
    assert fit_activity.duration_s > reported
    gaps = [w for w in fit_activity.blind_windows if w.cause is BlindCause.MISSING_RECORD]
    assert [w.duration_s for w in gaps] == [1.0]


def test_measured_distance_and_speed_match_the_watchs_own_summary(fit_activity):
    distances = [s.distance_m for s in fit_activity.samples if s.distance_m is not None]
    speeds = [s.speed_ms for s in fit_activity.samples if s.speed_ms is not None]
    assert distances[-1] == pytest.approx(GOLDEN["device_reported"]["distance_m"])
    assert max(speeds) == pytest.approx(GOLDEN["device_reported"]["max_speed_ms"])


def test_no_connect_iq_developer_field_reaches_the_activity(fit_activity):
    """ADR-0008/0009. The reference file carries 22 developer-field slots; none are read."""
    dumped = fit_activity.model_dump()
    assert set(dumped["samples"][0]) == {
        "t",
        "lat",
        "lon",
        "speed_ms",
        "hr_bpm",
        "temp_c",
        "distance_m",
        "confidence",
        "has_position",
    }
    assert "wavenum" not in json.dumps(dumped)
    assert "waveplot" not in json.dumps(dumped)
