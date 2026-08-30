"""L1: does the smoother recover the track, and is it honest where it cannot.

The synthetic session is the only place the first question has an answer. It carries the
noiseless track its samples were drawn from (`SyntheticSession.true_track`), so "the
smoother works" is a number here rather than a look at a chart.

The second question is the one the project actually turns on. Half a real session has no
fix, and an estimate through a gap must not read like a measurement. The sharpest test in
this file is `test_uncertainty_peaks_in_the_middle_of_a_gap`: a forward-only filter's
uncertainty grows monotonically and is worst at a gap's *end*, while an RTS-smoothed track
is pinned from both sides and is worst in its *middle*. That shape is the backward pass's
signature, and nothing else produces it.
"""

import math

import pytest

from surf.geo import M_PER_DEG_LAT, LocalFrame
from surf.models import Activity, Fidelity, Sample
from surf.pipeline.l1 import KinematicsStage
from surf.synthetic import SyntheticParams, make_synthetic_session


@pytest.fixture(scope="module")
def session():
    return make_synthetic_session()


@pytest.fixture(scope="module")
def track(session):
    return KinematicsStage().run(session.activity)


def rms(values):
    return math.sqrt(sum(v * v for v in values) / len(values))


def errors_m(track, session):
    """Distance from each smoothed second to the true position it should have recovered."""
    first = next(s for s in session.activity.samples if s.has_position)
    frame = LocalFrame(lat0=first.lat, lon0=first.lon)
    observed, blind = [], []
    for smoothed, true, sample in zip(
        track, session.true_track, session.activity.samples, strict=True
    ):
        tx, ty = frame.to_metres(*true.lat_lon)
        ex, ey = frame.to_metres(smoothed.lat, smoothed.lon)
        error = math.hypot(ex - tx, ey - ty)
        (observed if sample.has_position else blind).append(error)
    return observed, blind


def longest_blind_run(track):
    """Indices of the longest unbroken stretch with no fix."""
    runs, current = [], []
    for index, point in enumerate(track):
        if point.observed:
            runs.append(current)
            current = []
        else:
            current.append(index)
    runs.append(current)
    return max(runs, key=len)


def straight_line_activity(corrupt_at=None, jump_m=500.0, n=61):
    """A surfer moving due north at exactly 1 m/s, with an optional impossible fix."""
    samples = []
    for i in range(n):
        lat = 38.0 + i / M_PER_DEG_LAT
        if i == corrupt_at:
            lat += jump_m / M_PER_DEG_LAT
        samples.append(Sample(t=float(i), lat=lat, lon=-9.0))
    return Activity(
        activity_id="straight",
        sport="surfing",
        start_time=0.0,
        fidelity=Fidelity.FIT,
        samples=samples,
    )


# --- recovery ---------------------------------------------------------------------


def test_the_smoother_beats_the_raw_fixes_it_was_given(track, session):
    """The whole justification for L1: a smoothed fix is closer to truth than the fix was."""
    observed, _ = errors_m(track, session)
    assert rms(observed) < SyntheticParams().gps_noise_m, "smoothing must beat raw noise"
    assert rms(observed) == pytest.approx(1.84, abs=0.25)


def test_the_track_degrades_gracefully_where_there_was_no_fix(track, session):
    """Error grows in a gap. It must grow, and it must stay bounded."""
    observed, blind = errors_m(track, session)
    assert rms(blind) > rms(observed), "an estimate cannot be as good as a measurement"
    assert rms(blind) == pytest.approx(8.5, abs=1.5)
    assert rms(observed + blind) == pytest.approx(5.7, abs=1.0)


def test_a_straight_line_is_recovered_exactly(track):
    """A known-answer case with no noise: 1 m/s north, and the smoother must say so."""
    line = KinematicsStage().run(straight_line_activity())
    middle = line[len(line) // 2]
    assert middle.speed_ms == pytest.approx(1.0, abs=0.01)
    assert middle.vy_ms == pytest.approx(1.0, abs=0.01)
    assert middle.vx_ms == pytest.approx(0.0, abs=0.01)


# --- honesty ----------------------------------------------------------------------


def test_uncertainty_peaks_in_the_middle_of_a_gap(track):
    """The RTS signature. A forward-only filter would put the worst second at the end.

    If this test ever fails with the maximum at the last index of the run, the backward
    pass has stopped running, whatever the rest of the suite says.
    """
    run = longest_blind_run(track)
    sigmas = [track[i].position_sigma_m for i in run]
    peak = sigmas.index(max(sigmas))

    assert len(run) > 30, "the fixture must contain a long gap or this proves nothing"
    assert peak != len(sigmas) - 1, "uncertainty peaking at the end means no backward pass"
    assert abs(peak - len(sigmas) // 2) <= len(sigmas) // 4
    assert sigmas[len(sigmas) // 2] > 5 * sigmas[0]


def test_confidence_falls_where_the_track_is_estimated(track):
    observed = [p.confidence for p in track if p.observed]
    blind = [p.confidence for p in track if not p.observed]
    assert min(observed) > 0.5
    assert sum(blind) / len(blind) < sum(observed) / len(observed)
    assert min(blind) < 0.2, "deep inside a gap we must admit we do not know"


def test_every_second_is_marked_observed_exactly_when_it_had_a_fix(track, session):
    assert [p.observed for p in track] == [s.has_position for s in session.activity.samples]


def test_the_track_has_one_row_per_sample_and_invents_no_others(track, session):
    assert len(track) == len(session.activity.samples)
    assert [p.t for p in track] == [s.t for s in session.activity.samples]


def test_a_session_with_no_fix_at_all_yields_no_track():
    """Nothing to estimate from. An invented track would be worse than an empty one."""
    blind = Activity(
        activity_id="blind",
        sport="surfing",
        start_time=0.0,
        fidelity=Fidelity.FIT,
        samples=[Sample(t=float(i), hr_bpm=100) for i in range(10)],
    )
    assert KinematicsStage().run(blind) == []


def test_confidence_is_one_knee_with_no_cliffs():
    stage = KinematicsStage(confidence_sigma_m=10.0)
    assert stage.confidence_for(0.0) == 1.0
    assert stage.confidence_for(10.0) == pytest.approx(0.5)
    assert stage.confidence_for(1000.0) < 0.001
    rising = [stage.confidence_for(s) for s in (0.0, 1.0, 5.0, 10.0, 50.0)]
    assert rising == sorted(rising, reverse=True)


# --- the physical prior -----------------------------------------------------------


def test_an_impossible_fix_does_not_drag_the_track():
    """Raw differencing on the reference session reaches 109 m/s. This is what rejects it."""
    clean = KinematicsStage().run(straight_line_activity())
    spiked = KinematicsStage().run(straight_line_activity(corrupt_at=30))
    drift = max(abs((a.lat - b.lat) * M_PER_DEG_LAT) for a, b in zip(spiked, clean, strict=True))
    assert drift < 0.1, "a 500 m spike must not move the track"


def test_without_the_prior_the_same_fix_does_drag_it():
    """The paired half: it is the gate doing the work, not the filter's own smoothing."""
    clean = KinematicsStage().run(straight_line_activity())
    ungated = KinematicsStage(max_speed_ms=1e6).run(straight_line_activity(corrupt_at=30))
    drift = max(abs((a.lat - b.lat) * M_PER_DEG_LAT) for a, b in zip(ungated, clean, strict=True))
    assert drift > 10.0


# --- determinism ------------------------------------------------------------------


def test_the_stage_is_pure(session):
    """A stage must be a function of its input, or the cache key is a lie."""
    once = KinematicsStage().run(session.activity)
    twice = KinematicsStage().run(session.activity)
    assert [p.model_dump() for p in once] == [p.model_dump() for p in twice]


def test_a_changed_param_changes_the_track(session):
    loose = KinematicsStage(process_noise=4.0).run(session.activity)
    tight = KinematicsStage(process_noise=0.05).run(session.activity)
    assert [p.model_dump() for p in loose] != [p.model_dump() for p in tight]


# --- the real session -------------------------------------------------------------


def test_the_reference_session_smooths_within_the_physical_prior(sample_fit):
    """Real data, where raw differencing produces 392 km/h."""
    from surf.ingest import parse_file

    activity = parse_file(sample_fit)
    track = KinematicsStage().run(activity)

    assert len(track) == len(activity.samples)
    assert max(p.speed_ms for p in track) < KinematicsStage().max_speed_ms
    observed = [p.confidence for p in track if p.observed]
    blind = [p.confidence for p in track if not p.observed]
    assert sum(blind) / len(blind) < sum(observed) / len(observed)
