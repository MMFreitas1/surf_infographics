"""L4, feature extraction.

Two things are being defended here, and they are not the same thing.

The first is arithmetic: a rate is a rate, a mean is a mean. Those tests are cheap.

The second is the honesty rule this stage exists to hold. The device's odometer freezes
through a blind window and back-fills the whole distance in one step on reacquisition, so a
naive reading turns 201 metres into 201 m/s -- the exact artefact Phase 5 spent two passes
convicting (ADR-0014). Every odometer feature here is defined per blind *run*, averaged over
that run's own duration, and `test_a_back_fill_step_is_never_read_as_one_second_of_travel`
is the test that would fail if anyone ever changed that.

The other half of the rule: a channel the file does not carry produces **no key**, never a
zero. Zero metres means "did not move", which is a claim. Absence is not.
"""

import pytest

from surf.models import FramedSample, Sample, SessionFrame, WaveCandidate
from surf.pipeline.l3 import CandidateSet
from surf.pipeline.l4 import FeatureInput, FeatureSet, FeatureStage, PayloadError, blind_runs
from surf.synthetic import ORIGIN_LAT, ORIGIN_LON

LAT, LON = ORIGIN_LAT, ORIGIN_LON


def a_frame() -> SessionFrame:
    """A stand-in frame: L4 never reads it, it only carries it through."""
    return SessionFrame(
        shore_bearing_deg=90.0,
        coherence=0.95,
        reliable=True,
        contributing_seconds=100,
        effective_seconds=30.0,
        origin_lat=ORIGIN_LAT,
        origin_lon=ORIGIN_LON,
    )


def sample(t: float, *, fix: bool = True, distance: float | None = None, hr: int = 100) -> Sample:
    """One second, positioned or not, carrying the channels that survive a blind window."""
    return Sample(
        t=t,
        lat=LAT if fix else None,
        lon=LON if fix else None,
        distance_m=distance,
        hr_bpm=hr,
    )


def framed(t: float, *, v_cross: float = 0.0, observed: bool = True):
    """One framed second. ``speed_ms`` is computed from the velocity, so it is driven here."""
    return FramedSample(
        t=t,
        cross_shore_m=0.0,
        along_shore_m=0.0,
        v_cross_ms=v_cross,
        v_along_ms=0.0,
        confidence=0.9,
        observed=observed,
    )


def measure(candidate: WaveCandidate, samples, frames=()) -> dict[str, float]:
    """Run the stage over one candidate and hand back its features."""
    out = FeatureStage().run(
        FeatureInput(
            candidates=CandidateSet(frame=a_frame(), candidates=[candidate]),
            framed=list(frames),
            samples=list(samples),
        )
    )
    return out.candidates[0].features


# -- blind runs, and the back-fill they carry --------------------------------------------


def test_it_finds_a_run_and_the_distance_its_catch_up_carried():
    """A run's distance is the reading when the fix returns, less the frozen one it held."""
    samples = [
        sample(0.0, distance=10.0),
        sample(1.0, fix=False, distance=10.0),
        sample(2.0, fix=False, distance=10.0),
        sample(3.0, distance=95.0),
    ]
    runs = blind_runs(samples)

    assert len(runs) == 1
    assert runs[0].t_start == 1.0
    assert runs[0].t_end == 3.0
    assert runs[0].metres == pytest.approx(85.0)


def test_a_run_that_never_regains_a_fix_has_an_unknown_distance():
    """The catch-up step never arrived. Reporting 0.0 would claim the surfer stopped."""
    samples = [sample(0.0, distance=10.0), sample(1.0, fix=False, distance=10.0)]
    runs = blind_runs(samples)

    assert len(runs) == 1
    assert runs[0].metres is None
    assert runs[0].frozen is False, "unknown is not the same as motionless"


def test_a_run_the_odometer_never_moved_through_is_frozen():
    """The signal that settles a candidate outright: the surfer went nowhere."""
    samples = [
        sample(0.0, distance=10.0),
        sample(1.0, fix=False, distance=10.0),
        sample(2.0, distance=10.2),
    ]
    assert blind_runs(samples)[0].frozen is True


def test_a_session_with_no_odometer_still_yields_runs_with_unknown_distances():
    """GPX carries no distance field. The runs are real; their distances are not knowable."""
    samples = [sample(0.0), sample(1.0, fix=False), sample(2.0)]
    runs = blind_runs(samples)

    assert len(runs) == 1
    assert runs[0].metres is None


# -- the honesty rule the odometer features exist to hold --------------------------------


def test_a_back_fill_step_is_never_read_as_one_second_of_travel():
    """The test that fails if anyone ever divides a catch-up step by one second.

    Two hundred metres arrive in a single sample. Spread across the eleven seconds the run
    accounts for -- ten blind ones plus the step into the second the fix returned, see
    ``BlindRun.covered_s`` -- that is 18.2 m/s: fast, and arguable. Attributed to the second
    they landed on it is 200 m/s, which is the artefact, not a measurement.
    """
    samples = [sample(0.0, distance=0.0)]
    samples += [sample(float(t), fix=False, distance=0.0) for t in range(1, 11)]
    samples.append(sample(11.0, distance=200.0))

    features = measure(WaveCandidate(t_start=0.0, t_end=12.0), samples)

    assert features["blind_run_m"] == pytest.approx(200.0)
    assert features["blind_run_s"] == pytest.approx(10.0), "the watch was blind for ten"
    assert features["blind_run_mean_ms"] == pytest.approx(200.0 / 11.0)
    assert features["blind_run_mean_ms"] < 25.0, "a back-fill was read as a per-second speed"


def test_a_candidate_with_no_odometer_gets_no_odometer_features():
    """Absence of a channel is an absent key. Zero metres would be a claim about movement."""
    samples = [sample(0.0), sample(1.0, fix=False), sample(2.0)]
    features = measure(WaveCandidate(t_start=0.0, t_end=3.0), samples)

    assert "blind_run_m" not in features
    assert "blind_run_mean_ms" not in features
    assert "frozen_blind_s" not in features
    assert features["blind_overlap_s"] == pytest.approx(1.0), "the run itself is still known"


def test_a_fully_observed_candidate_gets_no_blind_features_at_all():
    samples = [sample(float(t), distance=float(t)) for t in range(5)]
    features = measure(WaveCandidate(t_start=0.0, t_end=5.0), samples)

    assert "blind_overlap_s" not in features
    assert "blind_run_m" not in features


def test_frozen_seconds_count_only_the_candidate_s_own_overlap():
    """A proposal clipping the edge of a long frozen stretch has not spanned it."""
    samples = [sample(0.0, distance=5.0)]
    samples += [sample(float(t), fix=False, distance=5.0) for t in range(1, 21)]
    samples.append(sample(21.0, distance=5.1))

    features = measure(WaveCandidate(t_start=18.0, t_end=22.0), samples)

    assert features["blind_run_s"] == pytest.approx(20.0), "the run is twenty seconds long"
    assert features["frozen_blind_s"] == pytest.approx(3.0), "only three of them are ours"


# -- heart rate, the channel with no gaps ------------------------------------------------


def test_the_heart_rate_drop_after_a_ride_is_negative():
    """A ride ends in a rest; paddling does not. This is evidence a blind window cannot hide."""
    during = [sample(float(t), fix=False, hr=150) for t in range(10)]
    after = [sample(float(t), fix=False, hr=110) for t in range(10, 30)]

    features = measure(WaveCandidate(t_start=0.0, t_end=10.0), during + after)

    assert features["hr_mean_bpm"] == pytest.approx(150.0)
    assert features["hr_max_bpm"] == pytest.approx(150.0)
    assert features["hr_delta_after_bpm"] == pytest.approx(-40.0)


def test_heart_rate_is_measured_even_where_position_is_not():
    """Every sample here is blind. The rate is still a measurement, not an estimate."""
    samples = [sample(float(t), fix=False, hr=120 + t) for t in range(6)]
    features = measure(WaveCandidate(t_start=0.0, t_end=6.0), samples)

    assert features["hr_at_start_bpm"] == pytest.approx(120.0)
    assert features["hr_max_bpm"] == pytest.approx(125.0)


# -- kinematics, over observed seconds only ----------------------------------------------


def test_speed_statistics_ignore_the_seconds_the_smoother_estimated():
    """An estimate's variance is a property of the filter, not of the surfing (ADR-0010)."""
    frames = [
        framed(0.0, v_cross=6.0),
        framed(1.0, v_cross=7.0),
        framed(2.0, v_cross=99.0, observed=False),
    ]
    samples = [sample(float(t)) for t in range(3)]

    features = measure(WaveCandidate(t_start=0.0, t_end=3.0), samples, frames)

    assert features["measured_speed_max_ms"] == pytest.approx(7.0)
    assert features["measured_speed_mean_ms"] == pytest.approx(6.5)


def test_a_latched_reading_shows_as_near_zero_variance():
    """Constant speed across many seconds is a stale reading, not a ride."""
    frames = [framed(float(t), v_cross=4.0) for t in range(12)]
    samples = [sample(float(t)) for t in range(12)]

    features = measure(WaveCandidate(t_start=0.0, t_end=12.0), samples, frames)

    assert features["measured_speed_variance"] == pytest.approx(0.0)


def test_the_take_off_is_the_sharpest_acceleration_at_the_onset():
    frames = [
        framed(0.0, v_cross=0.5),
        framed(1.0, v_cross=1.0),
        framed(2.0, v_cross=5.0),
        framed(3.0, v_cross=5.2),
    ]
    samples = [sample(float(t)) for t in range(4)]

    features = measure(WaveCandidate(t_start=0.0, t_end=4.0), samples, frames)

    assert features["takeoff_accel_ms2"] == pytest.approx(4.0)


# -- what this stage must not do ---------------------------------------------------------


def test_it_changes_no_boundary_and_reaches_no_verdict():
    """L3 owns the interval and L5 owns the verdict. L4 only measures (ADR-0016)."""
    candidate = WaveCandidate(t_start=3.0, t_end=19.0, position_coverage=0.4)
    out = FeatureStage().run(
        FeatureInput(
            candidates=CandidateSet(frame=a_frame(), candidates=[candidate]),
            framed=[framed(float(t), v_cross=5.0) for t in range(25)],
            samples=[sample(float(t), distance=float(t)) for t in range(25)],
        )
    )
    measured = out.candidates[0]

    assert (measured.t_start, measured.t_end) == (3.0, 19.0)
    assert measured.score is None
    assert measured.direction == candidate.direction
    assert measured.position_coverage == pytest.approx(0.4)


def test_it_measures_every_candidate_it_is_given_and_keeps_their_order():
    candidates = [
        WaveCandidate(t_start=0.0, t_end=5.0),
        WaveCandidate(t_start=10.0, t_end=15.0),
    ]
    out = FeatureStage().run(
        FeatureInput(
            candidates=CandidateSet(frame=a_frame(), candidates=candidates),
            framed=[framed(float(t), v_cross=3.0) for t in range(20)],
            samples=[sample(float(t), distance=float(t)) for t in range(20)],
        )
    )

    assert [(c.t_start, c.t_end) for c in out.candidates] == [(0.0, 5.0), (10.0, 15.0)]
    assert all(c.features for c in out.candidates)


# -- the cache contract ------------------------------------------------------------------


def test_the_payload_round_trips_the_features_and_the_frame():
    """A cached payload stands in for a run, so it has to decode to what the run produced."""
    stage = FeatureStage()
    out = FeatureSet(
        frame=a_frame(),
        candidates=[
            WaveCandidate(
                t_start=1.0,
                t_end=9.0,
                position_coverage=0.25,
                features={"blind_run_m": 42.5, "hr_mean_bpm": 131.0},
            )
        ],
    )
    restored = stage.decode(stage.encode(out))

    assert restored.frame == out.frame
    assert restored.candidates[0].features == {"blind_run_m": 42.5, "hr_mean_bpm": 131.0}
    assert restored.candidates[0].t_start == pytest.approx(1.0)


def test_a_payload_this_stage_did_not_write_is_refused():
    """Decoding must not depend on a database row a cache-only re-run may not have."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    sink = pa.BufferOutputStream()
    pq.write_table(pa.table({"t_start": pa.array([0.0])}), sink)

    with pytest.raises(PayloadError):
        FeatureStage().decode(bytes(sink.getvalue().to_pybytes()))


# -- attributing distance to the candidate's own seconds ---------------------------------


def test_every_second_is_attributed_exactly_once():
    """Observed seconds take their own delta; blind ones take their run's average.

    Ten metres in the first observed second, then a four-second blind run that back-filled
    40 m. The run contributes 10 m/s to each of its own seconds and nothing to anyone else's.
    """
    samples = [
        sample(0.0, distance=0.0),
        sample(1.0, distance=10.0),
        sample(2.0, fix=False, distance=10.0),
        sample(3.0, fix=False, distance=10.0),
        sample(4.0, fix=False, distance=10.0),
        sample(5.0, distance=50.0),
    ]
    features = measure(WaveCandidate(t_start=0.0, t_end=6.0), samples)

    # 10 m observed + 40 m across the run's own seconds, over five attributed seconds.
    assert features["odometer_m"] == pytest.approx(50.0)


def test_the_catch_up_second_does_not_swallow_the_whole_run():
    """The step landing on it belongs to the run behind it, not to that one second.

    Without this, a 40 m back-fill reads as 40 m/s on the second the fix returned -- the
    artefact this whole design exists to refuse.
    """
    samples = [
        sample(0.0, distance=0.0),
        sample(1.0, fix=False, distance=0.0),
        sample(2.0, fix=False, distance=0.0),
        sample(3.0, fix=False, distance=0.0),
        sample(4.0, distance=40.0),
    ]
    features = measure(WaveCandidate(t_start=4.0, t_end=5.0), samples)

    # That second alone is worth the run's average, 10 m/s -- not the entire 40 m.
    assert features["odometer_ms"] == pytest.approx(10.0)


def test_the_peak_window_finds_a_ride_buried_in_an_over_long_candidate():
    """L3 merges bursts, so a real ride arrives padded with paddling on both sides.

    A mean over the whole proposal reads as paddling, which is what the padding was. The
    peak window is what survives that, and on the seeded sessions it was the single largest
    source of refused rides.
    """
    slow = [sample(float(t), distance=float(t)) for t in range(15)]  # 1 m/s
    fast = [sample(float(t), distance=15.0 + (t - 15) * 6.0) for t in range(15, 25)]  # 6 m/s
    tail = [sample(float(t), distance=75.0 + (t - 25)) for t in range(25, 40)]  # 1 m/s

    features = measure(WaveCandidate(t_start=0.0, t_end=40.0), slow + fast + tail)

    assert features["odometer_ms"] < 2.5, "the whole-span mean is diluted, as expected"
    assert features["odometer_peak_ms"] == pytest.approx(6.0, abs=0.7)


def test_the_peak_window_shrinks_to_fit_a_short_candidate():
    """A candidate shorter than the window is its own window, not an error."""
    samples = [sample(float(t), distance=float(t) * 3.0) for t in range(6)]
    features = measure(WaveCandidate(t_start=0.0, t_end=5.0), samples)

    assert features["odometer_peak_ms"] == pytest.approx(3.0, abs=0.5)


def test_a_session_with_no_odometer_attributes_nothing():
    """Absence again: no distance field means no distance features, never zero ones."""
    features = measure(WaveCandidate(t_start=0.0, t_end=5.0), [sample(float(t)) for t in range(6)])

    assert "odometer_m" not in features
    assert "odometer_ms" not in features
    assert "odometer_peak_ms" not in features
