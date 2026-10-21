"""L6, the metrics stage.

What is defended here is not mostly arithmetic -- a mean is a mean. It is the set of
promises that make these numbers safe to put on a card:

* **a figure that was not measured is `None`, never 0.0.** Zero metres means "did not move"
  and zero km/h means "stood still": claims about the surfing, not about the recording;
* **`ride_measured_m` never exceeds `ride_m`.** One is the part of the other the watch
  actually saw, so the pair is what makes an estimate visible as one;
* **the count does not move.** L6 reads L5's answer and re-decides nothing, so the waves it
  reports are exactly the waves the pipeline committed to;
* **session figures count the session**, not the recording: a stretch the audit excluded is
  not entitled to appear in a cadence or a distance (ADR-0015);
* **the same input produces the same bytes**, because a stage that does not is not cacheable
  by content and cannot sit in the pipeline at all (architecture.md section 3).

The known-answer tests run against the synthetic generator, where the truth is exact: the
rides, their durations and the paddling speed are all set by `SyntheticParams`.
"""

import math

import pytest

from surf.models import (
    AuditReport,
    AuditSource,
    DecidedBy,
    FramedSample,
    NotSurfingReason,
    NotSurfingWindow,
    Sample,
    SessionFrame,
    SessionVerdict,
    WaveCandidate,
    WaveVerdict,
)
from surf.pipeline.l4 import FeatureSet
from surf.pipeline.l6 import MetricInput, MetricStage, PayloadError
from surf.synthetic import ORIGIN_LAT, ORIGIN_LON

SESSION_S = 600.0


def a_frame() -> SessionFrame:
    """A stand-in frame: L6 never reads it, it arrives inside L4's output."""
    return SessionFrame(
        shore_bearing_deg=90.0,
        coherence=0.95,
        reliable=True,
        contributing_seconds=100,
        effective_seconds=30.0,
        origin_lat=ORIGIN_LAT,
        origin_lon=ORIGIN_LON,
    )


def an_audit(*, not_surfing: list[NotSurfingWindow] | None = None) -> AuditReport:
    """An audit that calls the whole 0-600 s span session, unless told otherwise."""
    return AuditReport(
        window_s=60.0,
        t_start=0.0,
        t_end=SESSION_S,
        surfing_t_start=0.0,
        surfing_t_end=SESSION_S,
        not_surfing=not_surfing or [],
    )


def framed(t: float, *, speed: float, observed: bool = True) -> FramedSample:
    """One second of track moving straight at the shore, so speed is the cross-shore term."""
    return FramedSample(
        t=t,
        cross_shore_m=speed * t,
        along_shore_m=0.0,
        v_cross_ms=speed,
        v_along_ms=0.0,
        confidence=1.0 if observed else 0.4,
        observed=observed,
    )


def sample(t: float, *, distance: float | None, position: bool = True) -> Sample:
    """One recorded second. Position present or not; the odometer independent of it."""
    return Sample(
        t=t,
        lat=ORIGIN_LAT if position else None,
        lon=ORIGIN_LON if position else None,
        distance_m=distance,
    )


def verdict(
    *, start: float, end: float, is_wave: bool = True, coverage: float = 1.0
) -> WaveVerdict:
    return WaveVerdict(
        t_start=start,
        t_end=end,
        is_wave=is_wave,
        strength=0.9 if is_wave else 0.1,
        decided_by=DecidedBy.RULE,
        reason="measured top speed 7.0 m/s",
        position_coverage=coverage,
    )


def candidate(*, start: float, end: float, features: dict[str, float]) -> WaveCandidate:
    return WaveCandidate(t_start=start, t_end=end, features=features, position_coverage=1.0)


def an_input(
    *,
    verdicts: list[WaveVerdict],
    candidates: list[WaveCandidate] | None = None,
    framed_track: list[FramedSample] | None = None,
    samples: list[Sample] | None = None,
    audit: AuditReport | None = None,
) -> MetricInput:
    return MetricInput(
        verdict=SessionVerdict(verdicts=verdicts),
        features=FeatureSet(frame=a_frame(), candidates=candidates or []),
        framed=framed_track or [framed(float(t), speed=1.0) for t in range(int(SESSION_S))],
        samples=samples or [sample(float(t), distance=None) for t in range(int(SESSION_S))],
        audit=audit or an_audit(),
    )


# -- the null rule -----------------------------------------------------------------------


def test_a_session_with_no_odometer_reports_no_distance_rather_than_zero():
    """A GPX carries no distance field. "0 m" would say nobody moved, which is a lie."""
    data = an_input(
        verdicts=[verdict(start=10.0, end=25.0)],
        candidates=[candidate(start=10.0, end=25.0, features={"measured_speed_max_ms": 7.0})],
    )

    metrics = MetricStage().run(data)

    assert metrics.distance_m is None
    assert metrics.ride_m is None
    assert metrics.swim_m is None
    assert metrics.ride_measured_m is None
    assert metrics.waves[0].ride_m is None


def test_a_wave_the_watch_never_saw_reports_no_speed_rather_than_zero():
    """The case the odometer exists for: a ride with a distance and no speed at all."""
    data = an_input(
        verdicts=[verdict(start=10.0, end=25.0, coverage=0.0)],
        candidates=[candidate(start=10.0, end=25.0, features={"odometer_m": 48.0})],
        framed_track=[framed(float(t), speed=1.0, observed=False) for t in range(int(SESSION_S))],
    )

    wave = MetricStage().run(data).waves[0]

    assert wave.top_speed_ms is None
    assert wave.avg_speed_ms is None
    assert wave.takeoff_speed_ms is None
    assert wave.ride_m == 48.0
    assert wave.position_coverage == 0.0


def test_no_second_of_the_session_observed_means_no_distribution():
    """A histogram over nothing is not a histogram, and a mean of nothing is not 0.0."""
    data = an_input(
        verdicts=[],
        framed_track=[framed(float(t), speed=1.0, observed=False) for t in range(int(SESSION_S))],
    )

    assert MetricStage().run(data).speed is None


# -- the measured/attributed pair --------------------------------------------------------


def test_the_measured_part_of_a_ride_never_exceeds_the_attributed_whole():
    """The promise the Distancia card is built on: one is a part of the other."""
    samples = [
        sample(0.0, distance=0.0),
        sample(1.0, distance=10.0),
        sample(2.0, distance=20.0, position=False),
        sample(3.0, distance=20.0, position=False),
        sample(4.0, distance=60.0),
    ]
    data = an_input(
        verdicts=[verdict(start=0.0, end=5.0)],
        candidates=[candidate(start=0.0, end=5.0, features={"odometer_m": 60.0})],
        samples=samples,
    )

    wave = MetricStage().run(data).waves[0]

    assert wave.ride_measured_m is not None
    assert wave.ride_measured_m <= wave.ride_m
    # Only the one step between two positioned seconds counts: 0 -> 10 m. The 40 m step on
    # the second the fix returned is the catch-up for the blind run behind it (ADR-0014).
    assert wave.ride_measured_m == pytest.approx(10.0)


def test_a_catch_up_step_is_never_counted_as_measured_travel():
    """201 metres on one second is the artefact Phase 5 convicted. It is not a measurement."""
    samples = [
        sample(0.0, distance=100.0),
        sample(1.0, distance=100.0, position=False),
        sample(2.0, distance=301.5),
    ]
    data = an_input(
        verdicts=[verdict(start=0.0, end=3.0)],
        candidates=[candidate(start=0.0, end=3.0, features={"odometer_m": 201.5})],
        samples=samples,
    )

    assert MetricStage().run(data).waves[0].ride_measured_m is None


def test_swim_and_ride_add_up_to_the_session_total():
    """The card draws them as two parts of one bar, so they have to be two parts of one bar."""
    samples = [sample(float(t), distance=float(t) * 2.0) for t in range(int(SESSION_S))]
    data = an_input(
        verdicts=[verdict(start=10.0, end=25.0)],
        candidates=[candidate(start=10.0, end=25.0, features={"odometer_m": 40.0})],
        samples=samples,
    )

    metrics = MetricStage().run(data)

    assert metrics.distance_m is not None
    assert metrics.swim_m is not None
    assert metrics.ride_m is not None
    assert metrics.swim_m + metrics.ride_m == pytest.approx(metrics.distance_m)


# -- the count does not move -------------------------------------------------------------


def test_only_the_waves_l5_settled_are_reported():
    """L6 re-decides nothing. A refused proposal is not a card."""
    data = an_input(
        verdicts=[
            verdict(start=10.0, end=25.0),
            verdict(start=100.0, end=140.0, is_wave=False),
            verdict(start=200.0, end=215.0),
        ],
    )

    metrics = MetricStage().run(data)

    assert metrics.wave_count == 2
    assert [w.index for w in metrics.waves] == [1, 2]
    assert [(w.t_start, w.t_end) for w in metrics.waves] == [(10.0, 25.0), (200.0, 215.0)]


def test_boundaries_come_through_untouched():
    """No stage downstream of L3 may move an edge (ADR-0016), and this is the last one."""
    data = an_input(verdicts=[verdict(start=17.5, end=42.25)])

    wave = MetricStage().run(data).waves[0]

    assert (wave.t_start, wave.t_end) == (17.5, 42.25)
    assert wave.duration_s == pytest.approx(24.75)


def test_waves_are_numbered_in_the_order_they_were_surfed():
    """The index is the number on the card, so it has to be chronological."""
    data = an_input(
        verdicts=[
            verdict(start=200.0, end=215.0),
            verdict(start=10.0, end=25.0),
            verdict(start=100.0, end=118.0),
        ],
    )

    metrics = MetricStage().run(data)

    assert [w.t_start for w in metrics.waves] == [10.0, 100.0, 200.0]
    assert [w.index for w in metrics.waves] == [1, 2, 3]


# -- session figures count the session ---------------------------------------------------


def test_an_excluded_stretch_is_not_counted_as_session():
    """The walk up the beach is an exclusion, not a demotion (ADR-0015). It still must not
    land in the session's own figures."""
    excluded = NotSurfingWindow(
        t_start=300.0,
        t_end=400.0,
        reason=NotSurfingReason.INTERRUPTION,
        source=AuditSource.BASELINE,
        confidence=0.8,
    )
    data = an_input(verdicts=[], audit=an_audit(not_surfing=[excluded]))

    metrics = MetricStage().run(data)

    assert metrics.session_s == pytest.approx(SESSION_S - 100.0)


def test_coverage_is_the_fraction_of_session_seconds_that_carried_a_fix():
    half = [framed(float(t), speed=1.0, observed=t % 2 == 0) for t in range(int(SESSION_S))]
    data = an_input(verdicts=[], framed_track=half)

    assert MetricStage().run(data).coverage == pytest.approx(0.5)


def test_the_cadence_buckets_account_for_every_wave_exactly_once():
    data = an_input(
        verdicts=[
            verdict(start=10.0, end=25.0),
            verdict(start=100.0, end=118.0),
            verdict(start=590.0, end=599.0),
        ],
    )

    metrics = MetricStage().run(data)

    assert sum(b.waves for b in metrics.cadence) == metrics.wave_count
    assert metrics.cadence[0].t_start == 0.0
    assert metrics.cadence[-1].t_end == SESSION_S


def test_the_headline_rate_is_waves_over_the_session_scaled_to_ten_minutes():
    """600 s of session with three waves in it is three waves per ten minutes."""
    data = an_input(
        verdicts=[
            verdict(start=10.0, end=25.0),
            verdict(start=100.0, end=118.0),
            verdict(start=200.0, end=215.0),
        ],
    )

    assert MetricStage().run(data).waves_per_10min == pytest.approx(3.0)


def test_the_return_intervals_are_the_gaps_between_consecutive_rides():
    data = an_input(
        verdicts=[
            verdict(start=10.0, end=25.0),
            verdict(start=100.0, end=118.0),
            verdict(start=200.0, end=215.0),
        ],
    )

    metrics = MetricStage().run(data)

    assert [(r.after_wave, r.seconds) for r in metrics.returns] == [(1, 75.0), (2, 82.0)]
    assert metrics.return_mean_s == pytest.approx(78.5)
    assert metrics.return_median_s == pytest.approx(78.5)


def test_one_wave_has_no_return_interval_and_says_so():
    """Nothing to paddle back from. None, not 0.0 -- the surfer did not teleport."""
    metrics = MetricStage().run(an_input(verdicts=[verdict(start=10.0, end=25.0)]))

    assert metrics.returns == []
    assert metrics.return_mean_s is None
    assert metrics.return_median_s is None


# -- the distribution --------------------------------------------------------------------


def test_the_histogram_accounts_for_every_observed_second():
    """A bin count that does not add up is a chart that lies about its own sample."""
    track = [framed(float(t), speed=0.2 + t * 0.01, observed=t % 3 != 0) for t in range(60)]
    data = an_input(verdicts=[], framed_track=track, audit=an_audit())

    histogram = MetricStage().run(data).speed

    assert histogram is not None
    assert sum(histogram.counts) == histogram.n_seconds
    assert histogram.n_seconds == sum(1 for s in track if s.observed)
    assert len(histogram.bin_edges_ms) == len(histogram.counts) + 1


def test_the_fastest_second_lands_inside_the_last_bin():
    """An off-by-one here would silently drop the top speed out of the chart."""
    track = [framed(float(t), speed=7.3, observed=True) for t in range(10)]
    data = an_input(verdicts=[], framed_track=track)

    histogram = MetricStage().run(data).speed

    assert histogram is not None
    assert histogram.bin_edges_ms[-1] >= 7.3
    assert histogram.counts[-1] == 10


def test_a_single_observed_second_has_no_spread():
    track = [framed(0.0, speed=3.0, observed=True)]
    data = an_input(verdicts=[], framed_track=track)

    histogram = MetricStage().run(data).speed

    assert histogram is not None
    assert histogram.n_seconds == 1
    assert histogram.mean_ms == pytest.approx(3.0)
    assert histogram.sd_ms == 0.0


# -- the riding distribution -------------------------------------------------------------
#
# `speed` is every observed second in the water; `ride_speed` is only the seconds on a
# wave. They are different populations, and the Velocidade card is about the second one.


def a_ride_at(speed: float, *, start: float, end: float) -> list[FramedSample]:
    """A session paddling at 1.0 m/s with one stretch ridden at `speed`."""
    return [
        framed(float(t), speed=speed if start <= t < end else 1.0) for t in range(int(SESSION_S))
    ]


def test_the_riding_distribution_counts_only_the_seconds_on_a_wave():
    """Known answer: ten seconds at 5.0 m/s, and nothing else, inside a ten-second ride."""
    data = an_input(
        verdicts=[verdict(start=20.0, end=30.0)],
        framed_track=a_ride_at(5.0, start=20.0, end=30.0),
    )

    metrics = MetricStage().run(data)

    assert metrics.ride_speed is not None
    assert metrics.ride_speed.n_seconds == 10
    assert metrics.ride_speed.mean_ms == pytest.approx(5.0)
    assert metrics.ride_speed.sd_ms == 0.0
    # The whole-session figure still sees every second, riding and paddling alike.
    assert metrics.speed is not None
    assert metrics.speed.n_seconds == int(SESSION_S)


def test_the_two_distributions_are_not_the_same_number():
    """The reason this field exists. A session is mostly paddling, so a mean over both
    populations sits between two humps and describes neither."""
    data = an_input(
        verdicts=[verdict(start=20.0, end=30.0)],
        framed_track=a_ride_at(5.0, start=20.0, end=30.0),
    )

    metrics = MetricStage().run(data)

    assert metrics.speed is not None
    assert metrics.ride_speed is not None
    assert metrics.ride_speed.mean_ms > metrics.speed.mean_ms
    assert metrics.ride_speed.n_seconds < metrics.speed.n_seconds


def test_a_session_with_no_waves_has_no_riding_distribution():
    """None, not an empty histogram: nobody rode anything, so there is nothing to describe."""
    metrics = MetricStage().run(an_input(verdicts=[]))

    assert metrics.speed is not None
    assert metrics.ride_speed is None


def test_a_refused_proposal_contributes_no_riding_seconds():
    """Only the waves L5 settled count. A proposal it rejected is not a ride, however fast
    the seconds inside it were."""
    data = an_input(
        verdicts=[verdict(start=20.0, end=30.0, is_wave=False)],
        framed_track=a_ride_at(9.0, start=20.0, end=30.0),
    )

    metrics = MetricStage().run(data)

    assert metrics.ride_speed is None


def test_a_wave_the_watch_never_saw_contributes_no_riding_seconds():
    """Coverage 0 means no observed second, so there is no speed to put in a bin -- the same
    rule the per-wave fields follow."""
    blind = [framed(float(t), speed=5.0, observed=False) for t in range(int(SESSION_S))]
    data = an_input(
        verdicts=[verdict(start=20.0, end=30.0, coverage=0.0)],
        framed_track=blind,
    )

    assert MetricStage().run(data).ride_speed is None


def test_a_ride_inside_an_excluded_stretch_is_left_out_of_the_riding_distribution():
    """ADR-0015 applies to this figure too: a second L0.6 excluded is not a session second,
    so it cannot be a riding second either."""
    excluded = NotSurfingWindow(
        t_start=15.0,
        t_end=35.0,
        reason=NotSurfingReason.INTERRUPTION,
        source=AuditSource.BASELINE,
        confidence=0.8,
    )
    data = an_input(
        verdicts=[verdict(start=20.0, end=30.0)],
        framed_track=a_ride_at(5.0, start=20.0, end=30.0),
        audit=an_audit(not_surfing=[excluded]),
    )

    assert MetricStage().run(data).ride_speed is None


# -- the stage contract ------------------------------------------------------------------


def test_the_payload_round_trips():
    """A cached payload stands in for running the stage, so it has to be the same answer."""
    stage = MetricStage()
    metrics = stage.run(an_input(verdicts=[verdict(start=10.0, end=25.0)]))

    assert stage.decode(stage.encode(metrics)) == metrics


def test_a_payload_this_stage_did_not_write_is_refused():
    with pytest.raises(PayloadError):
        MetricStage().decode(b'{"not": "a SessionMetrics", "waves": 3}')


def test_the_audit_identity_is_part_of_the_cache_key():
    """L0.6 is not in this stage's chain (ADR-0015) but it decides which seconds count, so a
    different audit has to mean a different cached aggregate."""
    assert MetricStage(audit_key="a").meta.params != MetricStage(audit_key="b").meta.params


def test_every_parameter_that_moves_a_number_is_in_the_key():
    params = MetricStage().meta.params

    assert set(params) == {"takeoff_s", "bin_ms", "bucket_s", "audit_key"}


# -- known answers, against the generator's exact truth ----------------------------------


@pytest.fixture
def measured_session(tmp_path):
    """The synthetic session with its odometer on, run through the real chain."""
    from surf.config import Settings
    from surf.pipeline.cache import StageCache
    from surf.pipeline.session import metrics_for, waves_for
    from surf.synthetic import SyntheticParams, make_synthetic_session

    settings = Settings(SURF_DATA_DIR=tmp_path / "data")
    cache = StageCache(settings.cache_dir)
    session = make_synthetic_session(SyntheticParams(n_waves=8, odometer=True))
    verdict_out, _ = waves_for(session.activity, cache, samples_key="metrics-known")
    metrics, _ = metrics_for(session.activity, cache, samples_key="metrics-known")
    return session, verdict_out, metrics


def test_the_chain_reports_the_count_the_pipeline_committed_to(measured_session):
    """The whole reason this stage reads L5 rather than re-deciding: one answer, two routes."""
    _, verdict_out, metrics = measured_session

    assert metrics.wave_count == verdict_out.wave_count


def test_every_reported_wave_is_one_the_generator_actually_put_there(measured_session):
    """No ride is invented. Each row overlaps a true interval from the generator."""
    session, _, metrics = measured_session

    for wave in metrics.waves:
        assert any(
            wave.t_start < truth.t_end and truth.t_start < wave.t_end for truth in session.truth
        ), f"wave {wave.index} overlaps no true ride"


def test_the_ride_speeds_sit_in_the_band_the_generator_was_given(measured_session):
    """Rides peak at 4-8 m/s by construction, and paddling integrates 1.0. A top speed
    outside that band would mean the numbers on the card came from somewhere else."""
    _, _, metrics = measured_session

    for wave in metrics.waves:
        if wave.top_speed_ms is not None:
            assert 1.0 <= wave.top_speed_ms <= 12.0, f"wave {wave.index} tops {wave.top_speed_ms}"


def test_the_session_totals_are_internally_consistent(measured_session):
    _, _, metrics = measured_session

    assert metrics.distance_m is not None
    assert metrics.ride_m is not None
    assert metrics.ride_measured_m is not None
    assert metrics.ride_measured_m <= metrics.ride_m
    assert metrics.ride_m <= metrics.distance_m
    assert metrics.swim_m == pytest.approx(metrics.distance_m - metrics.ride_m)
    assert metrics.waves_per_10min == pytest.approx(metrics.wave_count / metrics.session_s * 600.0)


def test_the_return_intervals_match_the_waiting_the_generator_wrote(measured_session):
    """Between rides the generator paddles out (45-90 s), waits (60-200 s) and recovers
    (12-30 s), so a gap is minutes, not seconds -- and never negative."""
    _, _, metrics = measured_session

    for interval in metrics.returns:
        assert 0.0 < interval.seconds < 600.0, f"after wave {interval.after_wave}"


def test_the_distribution_covers_the_whole_observed_session(measured_session):
    _, _, metrics = measured_session

    assert metrics.speed is not None
    assert metrics.speed.n_seconds == pytest.approx(
        round(metrics.coverage * metrics.session_s), abs=1
    )
    assert math.isclose(sum(metrics.speed.counts), metrics.speed.n_seconds)
