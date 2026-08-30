"""Blind-window derivation.

These bounds decide every coverage number the app reports, so the convention is pinned
here explicitly: a sample owns the interval from its own timestamp to the next one, which
makes n blind samples in a 1 Hz recording exactly n blind seconds.
"""

from surf.ingest.blind import (
    blind_from_missing_positions,
    blind_from_time_gaps,
    derive_blind_windows,
    nominal_interval,
)
from surf.models import BlindCause, Sample


def at(t, *, positioned):
    """One sample at time t, with or without a fix."""
    return Sample(t=float(t), lat=10.0 if positioned else None, lon=20.0 if positioned else None)


def series(pattern):
    """Build a 1 Hz series from a string: '#' has a fix, '.' does not."""
    return [at(i, positioned=char == "#") for i, char in enumerate(pattern)]


def test_nominal_interval_is_measured_not_assumed():
    assert nominal_interval(series("####")) == 1.0
    assert nominal_interval([at(0, positioned=True), at(5, positioned=True)]) == 5.0


def test_nominal_interval_falls_back_when_there_is_nothing_to_measure():
    assert nominal_interval([]) == 1.0
    assert nominal_interval([at(0, positioned=True)]) == 1.0


def test_a_run_of_n_blind_samples_is_n_blind_seconds():
    """The convention that makes the FIT and GPX derivations agree on the same session."""
    windows = blind_from_missing_positions(series("#...#"))
    assert len(windows) == 1
    assert windows[0].duration_s == 3.0
    assert windows[0].t_start == 1.0
    assert windows[0].t_end == 4.0


def test_blind_run_at_the_start_is_captured():
    windows = blind_from_missing_positions(series("..##"))
    assert (windows[0].t_start, windows[0].t_end) == (0.0, 2.0)


def test_blind_run_at_the_end_extends_by_one_interval():
    """The last sample still owns its own second, even with nothing after it."""
    windows = blind_from_missing_positions(series("##.."))
    assert (windows[0].t_start, windows[0].t_end) == (2.0, 4.0)
    assert windows[0].duration_s == 2.0


def test_separate_runs_stay_separate():
    windows = blind_from_missing_positions(series("#.#.#"))
    assert [w.duration_s for w in windows] == [1.0, 1.0]


def test_a_fully_blind_session_is_one_window():
    windows = blind_from_missing_positions(series("...."))
    assert len(windows) == 1
    assert windows[0].duration_s == 4.0


def test_a_session_with_no_dropout_has_no_windows():
    assert blind_from_missing_positions(series("####")) == []


def test_missing_position_windows_carry_the_no_fix_cause():
    assert blind_from_missing_positions(series("#.#"))[0].cause is BlindCause.NO_FIX


def test_time_gaps_become_missing_record_windows():
    samples = [at(0, positioned=True), at(1, positioned=True), at(5, positioned=True)]
    windows = blind_from_time_gaps(samples)
    assert len(windows) == 1
    assert (windows[0].t_start, windows[0].t_end) == (2.0, 5.0)
    assert windows[0].cause is BlindCause.MISSING_RECORD


def test_a_regular_series_has_no_gaps():
    assert blind_from_time_gaps(series("####")) == []


def test_derive_returns_both_causes_in_time_order():
    """A TCX can have both: a positionless point, and a stretch with no point at all."""
    samples = [
        at(0, positioned=True),
        at(1, positioned=False),
        at(2, positioned=True),
        at(8, positioned=True),
    ]
    windows = derive_blind_windows(samples)
    assert [w.cause for w in windows] == [BlindCause.NO_FIX, BlindCause.MISSING_RECORD]
    assert [w.t_start for w in windows] == [1.0, 3.0]


def test_windows_long_enough_to_hide_a_ride_are_flagged():
    windows = blind_from_missing_positions(series("#" + "." * 20 + "#"))
    assert windows[0].could_hide_a_wave() is True
