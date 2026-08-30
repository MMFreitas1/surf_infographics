"""L3, candidate generation.

Recall is the only thing this stage is judged on: a ride it never proposes cannot be
recovered by any later stage, while a bad proposal is L5's problem and L5 is built to have
it. So the sharpest test here is not "how many proposals were right" but "which real rides
were missed, and why".

The answer on the synthetic turns out to be worth stating plainly. Every ride the smoother
could actually see is found; the ones missed are the ones that were mostly blind, where the
RTS pass has no position evidence and damps the track toward stillness. That is a limit of
the data, not of the rule, and the two are measured separately below so they cannot be
confused with each other.
"""

import pytest

from surf.evaluation import Interval, score
from surf.models import FramedSample, RideDirection, SessionFrame
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FramedTrack, FrameStage
from surf.pipeline.l3 import CandidateSet, CandidateStage, PayloadError
from surf.synthetic import ORIGIN_LAT, ORIGIN_LON, make_synthetic_session

OBSERVED_ENOUGH = 0.5
"""A ride with at least this much position coverage is one the smoother had evidence for."""


def a_frame(reliable: bool = True) -> SessionFrame:
    """A stand-in frame, so a candidate test does not depend on bearing estimation."""
    return SessionFrame(
        shore_bearing_deg=90.0,
        coherence=0.95,
        reliable=reliable,
        contributing_seconds=100,
        effective_seconds=30.0,
        origin_lat=ORIGIN_LAT,
        origin_lon=ORIGIN_LON,
    )


def framed(shoreward, observed=None) -> FramedTrack:
    """A framed track carrying the given cross-shore velocities, one per second."""
    return FramedTrack(
        frame=a_frame(),
        samples=[
            FramedSample(
                t=float(i),
                cross_shore_m=0.0,
                along_shore_m=0.0,
                v_cross_ms=v,
                v_along_ms=0.0,
                confidence=0.9,
                observed=True if observed is None else observed[i],
            )
            for i, v in enumerate(shoreward)
        ],
    )


def reference():
    """The reference synthetic session, all the way through L1 and L2."""
    session = make_synthetic_session()
    track = FrameStage().run(KinematicsStage().run(session.activity))
    return session, track


def coverage_of(track: FramedTrack, interval: Interval) -> float:
    """How much of a truth interval carried a real fix."""
    during = [s for s in track.samples if interval.t_start <= s.t < interval.t_end]
    return sum(1 for s in during if s.observed) / len(during) if during else 0.0


# -- what it finds, and what it cannot ---------------------------------------------------


def test_it_finds_every_ride_the_smoother_could_actually_see():
    """The real measure of the rule, with blindness held out of it."""
    session, track = reference()
    proposals = [Interval(c.t_start, c.t_end) for c in CandidateStage().run(track).candidates]
    visible = [i for i in session.truth if coverage_of(track, i) >= OBSERVED_ENOUGH]

    assert visible, "the fixture must contain rides that were actually observed"
    assert score(proposals, visible).recall == 1.0


def test_the_rides_it_misses_are_the_ones_that_were_blind():
    """Recall below 1.0 has to be explained, not averaged away.

    If this ever fails with a *well-observed* ride among the misses, the rule has broken and
    the number to look at is not overall recall but this list.
    """
    session, track = reference()
    result = CandidateStage().run(track)
    proposals = [Interval(c.t_start, c.t_end) for c in result.candidates]

    missed = [i for i in session.truth if score(proposals, [i]).recall == 0.0]
    assert missed, "this fixture is expected to contain rides the smoother cannot see"
    for interval in missed:
        assert coverage_of(track, interval) < OBSERVED_ENOUGH, (
            f"ride at {interval.t_start}s was {coverage_of(track, interval):.0%} observed "
            "and still missed -- that is a rule failure, not blindness"
        )


def test_overall_recall_holds_at_the_pinned_level():
    """Blind rides cap this below 1.0. Pinned so a regression cannot hide behind them."""
    session, track = reference()
    proposals = [Interval(c.t_start, c.t_end) for c in CandidateStage().run(track).candidates]
    assert score(proposals, session.truth).recall == pytest.approx(0.75)


def test_the_threshold_is_relative_so_scaling_the_session_changes_nothing():
    """Same property L2's bearing has, for the same reason: no absolute speed anywhere.

    Phase 2's `measurement_noise_m` sweep moves the whole velocity scale, so a rule keyed on
    an absolute m/s would propose differently under a different assumed noise level.
    """
    _, track = reference()
    scaled = FramedTrack(
        frame=track.frame,
        samples=[s.model_copy(update={"v_cross_ms": s.v_cross_ms * 3.5}) for s in track.samples],
    )
    stage = CandidateStage()
    assert [(c.t_start, c.t_end) for c in stage.run(scaled).candidates] == [
        (c.t_start, c.t_end) for c in stage.run(track).candidates
    ]


# -- the interval rules ------------------------------------------------------------------


def test_two_bursts_inside_the_merge_gap_are_one_ride():
    """A wave that dips below threshold mid-ride is still one wave."""
    track = framed([-0.5] * 10 + [6.0] * 5 + [-0.5] + [6.0] * 5 + [-0.5] * 10)
    candidates = CandidateStage().run(track).candidates
    assert len(candidates) == 1
    assert (candidates[0].t_start, candidates[0].t_end) == (10.0, 21.0)


def test_bursts_further_apart_stay_separate():
    track = framed([-0.5] * 10 + [6.0] * 5 + [-0.5] * 4 + [6.0] * 5 + [-0.5] * 10)
    assert len(CandidateStage().run(track).candidates) == 2


def test_a_burst_shorter_than_the_minimum_is_not_proposed():
    track = framed([-0.5] * 20 + [6.0] * 2 + [-0.5] * 20)
    assert CandidateStage().run(track).candidates == []


def test_position_coverage_reports_the_fraction_that_carried_a_fix():
    """ADR-0010's line, arriving at the candidate. Three of five seconds were real."""
    shoreward = [-0.5] * 10 + [6.0] * 5 + [-0.5] * 10
    observed = [True] * 10 + [True, False, True, False, True] + [True] * 10
    candidates = CandidateStage().run(framed(shoreward, observed)).candidates
    assert len(candidates) == 1
    assert candidates[0].position_coverage == pytest.approx(0.6)


def test_a_candidate_built_from_nothing_but_estimates_says_so():
    shoreward = [-0.5] * 10 + [6.0] * 5 + [-0.5] * 10
    observed = [True] * 10 + [False] * 5 + [True] * 10
    built = CandidateStage().run(framed(shoreward, observed)).candidates
    assert built[0].position_coverage == 0.0


# -- what it refuses to claim -------------------------------------------------------------


def test_a_candidate_carries_no_verdict_yet():
    """L3 proposes intervals. Scoring is L5's, and left-versus-right needs Phase 4 labels."""
    _, track = reference()
    for candidate in CandidateStage().run(track).candidates:
        assert candidate.score is None
        assert candidate.direction is RideDirection.UNKNOWN


def test_a_session_with_no_shoreward_motion_proposes_nothing():
    """Not "its least seaward seconds" -- nothing."""
    assert CandidateStage().run(framed([-1.0] * 60)).candidates == []


def test_an_empty_track_proposes_nothing():
    result = CandidateStage().run(FramedTrack(frame=a_frame(), samples=[]))
    assert result.candidates == []


def test_the_frame_travels_with_the_candidates():
    """A candidate is only as good as the axis it was measured against (ADR-0011)."""
    track = FramedTrack(frame=a_frame(reliable=False), samples=framed([1.0] * 30).samples)
    assert CandidateStage().run(track).frame.reliable is False


# -- the payload ---------------------------------------------------------------------------


def test_the_payload_round_trips_the_candidates_and_the_frame():
    stage = CandidateStage()
    _, track = reference()
    out = stage.run(track)
    back: CandidateSet = stage.decode(stage.encode(out))
    assert back.frame == out.frame
    assert [c.model_dump() for c in back.candidates] == [c.model_dump() for c in out.candidates]


def test_a_payload_this_stage_did_not_write_is_refused():
    _, track = reference()
    with pytest.raises(PayloadError):
        CandidateStage().decode(FrameStage().encode(track))
