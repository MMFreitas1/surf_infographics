"""L5, the stage that commits to a number.

What is being defended here is mostly not arithmetic. It is the shape of the decision:

* the ladder runs rule-first, and a model is shown **only** the ambiguous band (ADR-0005);
* a candidate nobody settles is not quietly counted as a wave;
* no tier, model included, may move a boundary (ADR-0016);
* the same input produces the same bytes, because a stage that does not is not cacheable
  by content and cannot sit in the pipeline at all (architecture.md section 3).

The thresholds themselves are deliberately thin here. Whether the rule is *good* is a
question for `evals/test_wave_adjudication.py`, which scores it against known truth; these
tests pin what it is allowed to do, not how well it does it.
"""

import pytest

from surf.models import DecidedBy, SessionFrame, WaveCandidate
from surf.pipeline.l4 import FeatureSet
from surf.pipeline.l5 import ClassifyStage, Judgement, PayloadError
from surf.synthetic import ORIGIN_LAT, ORIGIN_LON

RIDE = {
    "measured_speed_max_ms": 7.0,
    "takeoff_accel_ms2": 1.2,
    "measured_speed_variance": 3.0,
}
PADDLE = {"measured_speed_max_ms": 1.2, "measured_speed_variance": 0.4}


def a_frame() -> SessionFrame:
    return SessionFrame(
        shore_bearing_deg=90.0,
        coherence=0.95,
        reliable=True,
        contributing_seconds=100,
        effective_seconds=30.0,
        origin_lat=ORIGIN_LAT,
        origin_lon=ORIGIN_LON,
    )


def candidate(features: dict[str, float], *, start=0.0, end=15.0, coverage=0.8) -> WaveCandidate:
    return WaveCandidate(t_start=start, t_end=end, features=features, position_coverage=coverage)


def classify(*candidates: WaveCandidate, stage: ClassifyStage | None = None):
    return (stage or ClassifyStage()).run(FeatureSet(frame=a_frame(), candidates=list(candidates)))


class Fake:
    """An adjudicator that answers a fixed way and records what it was shown."""

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.seen: list[tuple[float, float]] = []

    @property
    def identity(self) -> dict[str, object]:
        return {"model": "fake", "prompt_version": "test.v1"}

    def judge(self, candidates):
        self.seen = [(c.t_start, c.t_end) for c in candidates]
        return [
            Judgement(is_wave=self.answer, reason="because the fake said so") for _ in candidates
        ]


# -- the deterministic tier --------------------------------------------------------------


def test_a_frozen_odometer_settles_a_candidate_outright():
    """The strongest signal there is: the watch's own distance never moved."""
    verdict = classify(candidate({"frozen_blind_s": 12.0}, end=15.0))
    only = verdict.verdicts[0]

    assert only.is_wave is False
    assert only.decided_by is DecidedBy.RULE
    assert "no movement through 12 of 15 s" in only.reason


def test_a_fast_candidate_is_a_wave_and_says_why():
    only = classify(candidate(RIDE)).verdicts[0]

    assert only.is_wave is True
    assert only.decided_by is DecidedBy.RULE
    assert "measured top speed 7.0 m/s" in only.reason


def test_a_candidate_that_never_beat_paddling_pace_is_not_a_wave():
    only = classify(candidate(PADDLE)).verdicts[0]

    assert only.is_wave is False
    assert only.decided_by is DecidedBy.RULE


def test_a_speed_that_barely_varies_is_read_as_a_latched_value():
    """Constant speed over a long run is a stale reading, not a ride."""
    flat = {"measured_speed_max_ms": 4.5, "measured_speed_variance": 0.0}
    varied = {"measured_speed_max_ms": 4.5, "measured_speed_variance": 3.0}

    assert classify(candidate(flat, end=20.0)).verdicts[0].strength < (
        classify(candidate(varied, end=20.0)).verdicts[0].strength
    )


def test_a_blind_candidate_is_judged_on_the_odometer_average_not_a_back_fill():
    """A wave the watch never saw can still be settled -- from a channel that kept recording.

    The number used is the blind run's average over its own duration, which is the only rate
    the odometer supports (L4). Nothing here ever sees a back-fill step.
    """
    only = classify(
        candidate(
            {"odometer_peak_ms": 8.0, "odometer_ms": 8.0, "blind_run_m": 104.0},
            coverage=0.0,
        )
    ).verdicts[0]

    assert only.is_wave is True
    assert "odometer over its best sustained stretch" in only.reason
    assert only.position_coverage == pytest.approx(0.0), (
        "coverage must survive onto the verdict so the UI can draw this differently"
    )


def test_a_candidate_with_no_speed_at_all_is_not_settled_by_the_rule():
    only = classify(candidate({"hr_mean_bpm": 120.0})).verdicts[0]

    assert only.decided_by is DecidedBy.UNRESOLVED
    assert "no speed this candidate can claim" in only.reason


# -- the ladder --------------------------------------------------------------------------


def test_the_band_goes_unresolved_when_there_is_no_adjudicator_and_is_not_counted():
    """An unsure rule with nobody to ask is not a yes."""
    verdict = classify(candidate({"measured_speed_max_ms": 3.2}))
    only = verdict.verdicts[0]

    assert only.decided_by is DecidedBy.UNRESOLVED
    assert only.is_wave is False
    assert verdict.wave_count == 0
    assert verdict.unresolved_count == 1


def test_the_model_is_shown_the_band_and_nothing_else():
    """ADR-0005 scopes a model to what the tier below could not settle. This is that scope."""
    fake = Fake(answer=True)
    stage = ClassifyStage(adjudicator=fake)
    verdict = classify(
        candidate(RIDE, start=0.0, end=15.0),
        candidate({"measured_speed_max_ms": 3.2}, start=20.0, end=35.0),
        candidate(PADDLE, start=40.0, end=55.0),
        stage=stage,
    )

    assert fake.seen == [(20.0, 35.0)], "a confident candidate was sent to the model"
    assert verdict.adjudicated == 1
    assert [v.decided_by for v in verdict.verdicts] == [
        DecidedBy.RULE,
        DecidedBy.MODEL,
        DecidedBy.RULE,
    ]


def test_the_model_can_turn_a_band_candidate_into_a_wave():
    stage = ClassifyStage(adjudicator=Fake(answer=True))
    verdict = classify(candidate({"measured_speed_max_ms": 3.2}), stage=stage)

    assert verdict.wave_count == 1
    assert verdict.verdicts[0].decided_by is DecidedBy.MODEL
    assert "model: because the fake said so" in verdict.verdicts[0].reason


def test_the_model_can_also_refuse_one():
    stage = ClassifyStage(adjudicator=Fake(answer=False))
    verdict = classify(candidate({"measured_speed_max_ms": 3.2}), stage=stage)

    assert verdict.wave_count == 0
    assert verdict.verdicts[0].decided_by is DecidedBy.MODEL


def test_the_model_is_named_on_the_verdict_it_reached():
    """A verdict is only interpretable next to the thing that reached it."""
    verdict = classify(
        candidate({"measured_speed_max_ms": 3.2}),
        stage=ClassifyStage(adjudicator=Fake()),
    )
    assert verdict.model == "fake"
    assert verdict.prompt_version == "test.v1"


def test_no_model_means_no_model_named():
    assert classify(candidate(RIDE)).model == ""


# -- what no tier is allowed to do -------------------------------------------------------


def test_no_tier_moves_a_boundary():
    """ADR-0016: verdicts were reproducible, span edges were not. So edges stay with L3."""
    verdict = classify(
        candidate(RIDE, start=11.0, end=29.0),
        candidate({"measured_speed_max_ms": 3.2}, start=40.0, end=57.0),
        stage=ClassifyStage(adjudicator=Fake()),
    )

    assert [(v.t_start, v.t_end) for v in verdict.verdicts] == [(11.0, 29.0), (40.0, 57.0)]


def test_every_candidate_gets_a_verdict_and_they_keep_their_order():
    verdict = classify(
        candidate(RIDE, start=0.0, end=15.0),
        candidate(PADDLE, start=20.0, end=35.0),
        candidate(RIDE, start=40.0, end=55.0),
    )

    assert verdict.proposed_count == 3
    assert [v.t_start for v in verdict.verdicts] == [0.0, 20.0, 40.0]
    assert verdict.wave_count == 2


def test_an_empty_candidate_set_commits_to_zero_rather_than_to_nothing():
    verdict = classify()

    assert verdict.wave_count == 0
    assert verdict.proposed_count == 0


# -- the cache contract ------------------------------------------------------------------


def test_the_same_input_produces_the_same_bytes():
    """The property that lets this stage be content-addressed at all."""
    stage = ClassifyStage()
    data = FeatureSet(frame=a_frame(), candidates=[candidate(RIDE), candidate(PADDLE)])

    assert stage.encode(stage.run(data)) == stage.encode(stage.run(data))


def test_the_adjudicator_is_part_of_the_cache_key():
    """A different model must not silently reuse the last one's verdicts."""
    plain = ClassifyStage().meta.params
    with_model = ClassifyStage(adjudicator=Fake()).meta.params

    assert plain["adjudicator"] == {}
    assert with_model["adjudicator"] == {"model": "fake", "prompt_version": "test.v1"}


def test_the_payload_round_trips():
    stage = ClassifyStage()
    out = stage.run(FeatureSet(frame=a_frame(), candidates=[candidate(RIDE)]))
    restored = stage.decode(stage.encode(out))

    assert restored.wave_count == out.wave_count
    assert restored.verdicts[0].reason == out.verdicts[0].reason
    assert restored.verdicts[0].decided_by is out.verdicts[0].decided_by


def test_a_payload_this_stage_did_not_write_is_refused():
    with pytest.raises(PayloadError):
        ClassifyStage().decode(b'{"not": "a verdict", "verdicts": 3}')
