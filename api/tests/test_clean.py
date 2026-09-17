"""L0.5: does the cleaner remove the impossible without removing the session.

Two failure modes matter here and they pull in opposite directions. A cleaner that takes
too little leaves a 109 m/s jump to draw a spike across the map and a 74.8 km/h reading to
crown a bogus best wave. A cleaner that takes too much silently deletes the fastest seconds
of a real ride -- which is exactly the data the product exists to measure -- and no amount of
green output would show it.

So the thresholds are not asserted, they are *swept against known truth*. The synthetic
session carries the intervals that are genuinely rides, which makes "this ceiling does not
eat real surfing" a number rather than an opinion, and
`test_l1s_gate_would_not_survive_as_a_removal_ceiling` is the sharpest test in the file: it
pins the reason L0.5's ceiling must be looser than the one L1 already uses.
"""

import math
from dataclasses import replace
from itertools import pairwise

import pytest

from surf.geo import LocalFrame
from surf.ingest import parse_activity
from surf.ingest.blind import derive_blind_windows
from surf.models import (
    Activity,
    BlindCause,
    Fidelity,
    RejectedFix,
    RejectionEffect,
    RejectionReason,
    Sample,
)
from surf.pipeline import StageCache, stage_key
from surf.pipeline.clean import CleanStage, PayloadError
from surf.synthetic import SyntheticParams, make_synthetic_session

FRAME = LocalFrame(lat0=38.0, lon0=-9.0)
"""A neutral offshore origin, matching the synthetic generator. Not anyone's break."""


def make_session(positions, *, speeds=None, distances=None, times=None):
    """A 1 Hz session from (x, y) metre offsets. ``None`` is a second with no fix.

    Metres rather than degrees because every rule under test is geometric, and a test that
    stated its cases in degrees would be asserting the projection as much as the rule.
    """
    samples = []
    for index, point in enumerate(positions):
        lat = lon = None
        if point is not None:
            lat, lon = FRAME.to_degrees(float(point[0]), float(point[1]))
        samples.append(
            Sample(
                t=float(index if times is None else times[index]),
                lat=lat,
                lon=lon,
                speed_ms=None if speeds is None else speeds[index],
                distance_m=None if distances is None else distances[index],
            )
        )
    return Activity(
        activity_id="clean-test",
        sport="surfing",
        start_time=0.0,
        fidelity=Fidelity.FIT,
        samples=samples,
        blind_windows=derive_blind_windows(samples),
    )


def line(count, step=1.0):
    """A surfer travelling east at ``step`` metres per second."""
    return [(i * step, 0.0) for i in range(count)]


def one_bad_fix():
    """A line running east with one fix 100 m off it, and the line resuming after.

    Note what this shape is: a lone displaced fix seated between two good ones is an
    out-and-back by definition, so it is `jump_and_return` that convicts it. The tests
    below use it to exercise what a demotion *does*, which is the same whichever rule
    named it.
    """
    return [*line(5), (100.0, 0.0), *line(4)]


def reasons(report):
    """Every rejection reason in the report, in time order."""
    return [r.reason for r in report.rejections]


def at(report, t):
    """Rejections recorded against one second."""
    return [r for r in report.rejections if r.t == t]


@pytest.fixture(scope="module")
def synthetic_seeds():
    """Five seeded sessions, each carrying the intervals that are genuinely rides."""
    return [make_synthetic_session(SyntheticParams(seed=seed)) for seed in (7, 11, 23, 42, 101)]


def rides_demoted(session, stage):
    """True ride seconds this stage would take away. The number that must stay at zero."""
    report = stage.run(session.activity).report
    return sum(
        1
        for r in report.rejections
        if r.effect is RejectionEffect.DEMOTED_TO_BLIND
        and any(iv.t_start <= r.t < iv.t_end for iv in session.truth)
    )


# -- the position channel -------------------------------------------------------------


def test_a_fix_that_would_need_impossible_speed_is_demoted():
    """A one-way departure, with nothing after it to make it an out-and-back."""
    report = CleanStage().run(make_session([*line(6), (100.0, 0.0)])).report
    assert reasons(report) == [RejectionReason.IMPLIED_SPEED]
    assert report.rejections[0].t == 6.0
    assert report.rejections[0].value == pytest.approx(95.0)
    assert report.rejections[0].limit == 18.0


def test_a_teleport_the_track_never_returns_from_stops_rejecting_once_time_explains_it():
    """The greedy pass measures from the last accepted fix, so a genuine relocation costs
    a short cascade and then recovers. Worth pinning: a rule that kept measuring from a fix
    it had already refused would reject the entire rest of the session.
    """
    positions = [*line(5), *[(100.0 + i, 0.0) for i in range(12)]]
    report = CleanStage().run(make_session(positions)).report

    assert RejectionReason.IMPLIED_SPEED in reasons(report)
    assert all(r.effect is RejectionEffect.DEMOTED_TO_BLIND for r in report.rejections)
    assert len(report.rejections) < 8
    assert max(r.t for r in report.rejections) < 12.0


def test_a_fix_just_under_the_ceiling_is_kept():
    """The ceiling is a ceiling, not a mood. 17 m in a second stands; 19 m does not."""
    kept = CleanStage().run(make_session([(0.0, 0.0), (17.0, 0.0)])).report
    refused = CleanStage().run(make_session([(0.0, 0.0), (19.0, 0.0)])).report
    assert kept.rejections == []
    assert reasons(refused) == [RejectionReason.IMPLIED_SPEED]


def test_the_greedy_pass_measures_from_the_last_accepted_fix():
    """Two bad fixes in a row: the second must not be excused by the first.

    Measured against the *previous* fix, the second bad fix is one metre away and looks
    perfect. Measured against the last *accepted* one it is 499 m away, which is what it
    really is. This is the difference between a cleaner and a cleaner that can be walked
    off a cliff one metre at a time.
    """
    positions = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (500.0, 0.0), (501.0, 0.0), (3.0, 0.0)]
    report = CleanStage().run(make_session(positions)).report
    assert [r.t for r in report.rejections] == [3.0, 4.0]
    assert reasons(report) == [RejectionReason.IMPLIED_SPEED, RejectionReason.IMPLIED_SPEED]


def test_an_acceleration_spike_is_demoted():
    """Under the speed ceiling, over the acceleration one: still not a body in water."""
    report = CleanStage().run(make_session([(0.0, 0.0)] * 3 + [(17.0, 0.0)])).report
    assert reasons(report) == [RejectionReason.IMPLIED_ACCELERATION]
    assert report.rejections[0].value == pytest.approx(17.0)


def test_an_out_and_back_is_named_a_jump_rather_than_a_speed():
    """Both rules would remove it. Only one of them says what it was.

    The jump rule runs first for exactly this reason: left to the greedy pass, the outbound
    leg is rejected as `implied_speed` and the return leg is never compared to anything,
    so a reacquisition would be filed under the wrong reason and the UI would report it as
    a surfer briefly travelling at 108 km/h.
    """
    report = (
        CleanStage().run(make_session([(0.0, 0.0), (0.0, 0.0), (30.0, 0.0), (0.0, 0.0)])).report
    )
    assert reasons(report) == [RejectionReason.JUMP_AND_RETURN]
    assert report.rejections[0].t == 2.0


def test_a_wander_inside_gps_noise_is_not_a_jump():
    """At 3 m per-fix noise a 10 m out-and-back is an ordinary draw from a surfer sitting
    still. Convicting it would demote half of every lull in the session."""
    report = (
        CleanStage().run(make_session([(0.0, 0.0), (0.0, 0.0), (10.0, 0.0), (0.0, 0.0)])).report
    )
    assert report.rejections == []


# -- what a rejection does ------------------------------------------------------------


def test_rejection_is_a_demotion_and_never_a_deletion():
    """The row stays. Deleting it would shorten the session and move every later second."""
    activity = make_session(one_bad_fix())
    cleaned = CleanStage().run(activity).activity

    assert len(cleaned.samples) == len(activity.samples)
    assert [s.t for s in cleaned.samples] == [s.t for s in activity.samples]

    demoted = cleaned.samples[5]
    assert demoted.lat is None
    assert demoted.lon is None
    assert demoted.speed_ms is None
    assert demoted.confidence == 0.0
    assert demoted.has_position is False


def test_coverage_falls_by_exactly_what_was_demoted():
    """A fix we refuse to believe must stop counting as a second the watch saw."""
    activity = make_session(one_bad_fix())
    result = CleanStage().run(activity)
    report = result.report

    assert report.fixes_before - report.fixes_after == 1
    assert report.coverage_before > report.coverage_after
    assert result.activity.position_coverage == pytest.approx(report.coverage_after)


def test_blind_windows_are_redrawn_around_a_demoted_fix():
    """Otherwise coverage and the windows would disagree, and both would be quoted."""
    activity = make_session(one_bad_fix())
    assert activity.blind_windows == []

    cleaned = CleanStage().run(activity).activity
    assert [(w.t_start, w.t_end, w.cause) for w in cleaned.blind_windows] == [
        (5.0, 6.0, BlindCause.NO_FIX)
    ]


def test_a_missing_record_window_survives_cleaning():
    """This stage never removes a record, so a window that says one was never written
    cannot have changed -- and re-deriving it would mean guessing the gap tolerance L0 used."""
    positions = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    activity = make_session(positions, times=[0, 1, 20, 21])
    before = [w for w in activity.blind_windows if w.cause is BlindCause.MISSING_RECORD]
    assert len(before) == 1

    cleaned = CleanStage().run(activity).activity
    after = [w for w in cleaned.blind_windows if w.cause is BlindCause.MISSING_RECORD]
    assert after == before


# -- the speed channel ----------------------------------------------------------------


def test_a_speed_the_odometer_contradicts_is_dropped_but_the_position_stands():
    """The two-effect rule. The watch saw this second perfectly well; only the speedometer
    lied, and demoting the whole fix would report "we could not see" about a fix we have."""
    speeds = [1.0] * 11
    speeds[5] = 20.0
    activity = make_session(line(11), speeds=speeds, distances=[float(i) for i in range(11)])
    result = CleanStage().run(activity)

    assert reasons(result.report) == [RejectionReason.SPEED_VS_ODOMETER]
    rejected = result.report.rejections[0]
    assert rejected.effect is RejectionEffect.SPEED_DROPPED
    assert rejected.value == pytest.approx(1.0)
    assert rejected.limit == pytest.approx(7.0)

    sample = result.activity.samples[5]
    assert sample.speed_ms is None
    assert sample.has_position is True
    assert result.report.coverage_before == result.report.coverage_after


def test_a_speed_the_odometer_confirms_is_kept():
    """The odometer and the speed field never agree exactly. Differing is not disagreeing."""
    speeds = [9.0] * 11
    activity = make_session(
        line(11, 9.0), speeds=speeds, distances=[float(i * 9) for i in range(11)]
    )
    assert CleanStage().run(activity).report.rejections == []


def test_a_speed_below_the_checkable_floor_is_never_convicted():
    """A frozen odometer under a paddling speed proves nothing: at 3 m noise the
    corroboration is worth less than the reading, so checking it would manufacture
    rejections rather than find them."""
    speeds = [5.0] * 11
    activity = make_session(line(11), speeds=speeds, distances=[0.0] * 11)
    assert CleanStage().run(activity).report.rejections == []


def test_a_speed_beyond_anything_a_board_does_needs_no_corroboration():
    speeds = [1.0] * 11
    speeds[5] = 30.0
    activity = make_session(line(11), speeds=speeds)
    report = CleanStage().run(activity).report

    assert reasons(report) == [RejectionReason.SPEED_IMPOSSIBLE]
    assert report.rejections[0].effect is RejectionEffect.SPEED_DROPPED


def test_positions_contradict_a_speed_when_there_is_no_odometer():
    """The fallback for a format that records no distance, GPX among them."""
    speeds = [0.0] * 11
    speeds[5] = 20.0
    activity = make_session([(0.0, 0.0)] * 11, speeds=speeds)
    report = CleanStage().run(activity).report

    assert reasons(report) == [RejectionReason.SPEED_VS_POSITION]
    assert report.rejections[0].effect is RejectionEffect.SPEED_DROPPED


def test_an_isolated_second_is_not_convicted_by_positions_it_does_not_have():
    """Unverifiable is not the same as impossible.

    With the nearest fixes twenty seconds either side, nothing here can contradict a single
    second's speed -- so the stage leaves it alone and says nothing, rather than inventing a
    bracket wide enough to convict on.
    """
    positions = [(0.0, 0.0)] + [None] * 19 + [(1.0, 0.0)] + [None] * 19 + [(2.0, 0.0)]
    speeds = [None] * 41
    speeds[20] = 20.0
    assert CleanStage().run(make_session(positions, speeds=speeds)).report.rejections == []


def test_a_demoted_fix_is_not_convicted_twice():
    """Its speed is already gone. Counting it again would double the rejection total and
    make the confidence card overstate how much of the session was refused."""
    speeds = [1.0, 1.0, 20.0, 1.0]
    positions = [(0.0, 0.0), (1.0, 0.0), (500.0, 0.0), (1000.0, 0.0)]
    report = CleanStage().run(make_session(positions, speeds=speeds, distances=[0.0] * 4)).report

    assert len(at(report, 2.0)) == 1
    assert at(report, 2.0)[0].effect is RejectionEffect.DEMOTED_TO_BLIND


# -- what a rejection may carry -------------------------------------------------------


def test_a_rejection_carries_no_coordinates():
    """This repo is public and these records reach committed goldens. A lat/lon here would
    be a GPS trace in git (CLAUDE.md), so the field set itself is pinned."""
    assert set(RejectedFix.model_fields) == {"t", "reason", "effect", "value", "limit"}


# -- switching it off -----------------------------------------------------------------


def test_disabled_is_a_pass_through_that_still_reports():
    activity = make_session(one_bad_fix())
    result = replace(CleanStage(), enabled=False).run(activity)

    assert result.activity.samples == activity.samples
    assert result.report.rejections == []
    assert result.report.enabled is False
    assert result.report.coverage_before == result.report.coverage_after


def test_switching_the_cleaner_off_is_a_key_the_cache_notices(tmp_path):
    """PLAN.md's Done-when: a threshold sweep must be a re-key, never a re-ingest."""
    cache = StageCache(tmp_path)
    on = stage_key(CleanStage(), cache, "input")
    off = stage_key(replace(CleanStage(), enabled=False), cache, "input")
    loosened = stage_key(replace(CleanStage(), max_implied_speed_ms=25.0), cache, "input")

    assert len({on, off, loosened}) == 3


# -- payload --------------------------------------------------------------------------


def test_the_payload_round_trips_exactly():
    """A cache hit stands in for a run, so decoding one has to yield what a run yielded."""
    stage = CleanStage()
    result = stage.run(make_session(one_bad_fix()))
    restored = stage.decode(stage.encode(result))

    assert restored.activity == result.activity
    assert restored.report == result.report


def test_a_demoted_second_round_trips_as_null_and_never_as_zero():
    """The invariant L0 holds and this stage must not break: a missing position is null.
    Written as 0.0 it would read as a surfer stationary at the equator."""
    stage = CleanStage()
    result = stage.run(make_session(one_bad_fix()))
    restored = stage.decode(stage.encode(result))

    assert restored.activity.samples[5].lat is None
    assert restored.activity.samples[5].speed_ms is None


def test_a_payload_without_a_report_is_refused():
    """An L0 payload is a valid Parquet session and decodes fine -- which is the danger."""
    from surf.ingest.stage import encode_activity

    with pytest.raises(PayloadError, match="was not written by this stage"):
        CleanStage().decode(encode_activity(make_session(line(4))))


# -- swept against known truth --------------------------------------------------------


def test_the_ceiling_leaves_genuine_rides_alone(synthetic_seeds):
    """The failure nobody would notice: a cleaner that quietly eats the fastest seconds.

    Across five seeded sessions the default ceilings demote at most a couple of true ride
    seconds in total, and those come from the one seed whose GPS noise draw is extreme.
    """
    stage = CleanStage()
    damage = [rides_demoted(session, stage) for session in synthetic_seeds]

    assert sum(damage) <= 2
    assert sum(1 for d in damage if d == 0) >= 4


def test_l1s_gate_would_not_survive_as_a_removal_ceiling(synthetic_seeds):
    """Why L0.5's ceiling is 18 m/s while L1's is 12, in one assertion.

    L1 *softens* a suspect fix by inflating its variance, so a false positive there costs
    almost nothing and a tight gate is free. This stage *removes* the fix, so the same gate
    destroys measurements -- and on known truth it demonstrably does.
    """
    tight = replace(CleanStage(), max_implied_speed_ms=12.0)
    default = CleanStage()

    at_12 = sum(rides_demoted(session, tight) for session in synthetic_seeds)
    at_18 = sum(rides_demoted(session, default) for session in synthetic_seeds)

    assert at_12 > at_18
    assert at_12 >= 5


def test_the_jump_rule_does_not_fire_on_a_session_with_no_artefacts(synthetic_seeds):
    """The floor that keeps it off ordinary GPS wander is load-bearing, so it is pinned."""
    for session in synthetic_seeds:
        report = CleanStage().run(session.activity).report
        assert RejectionReason.JUMP_AND_RETURN not in reasons(report)


def test_injected_artefacts_are_each_caught_and_named(synthetic_seeds):
    """The only coverage `jump_and_return` and `implied_acceleration` have on a realistic
    session: neither fires on the reference recording, so absent an injected case they
    would ship untested."""
    session = synthetic_seeds[0]
    samples = [s.model_copy() for s in session.activity.samples]
    positioned = [i for i, s in enumerate(samples) if s.has_position]

    def move(index, x, y):
        lat, lon = FRAME.to_degrees(x, y)
        samples[index] = samples[index].model_copy(update={"lat": lat, "lon": lon})

    def where(index):
        return FRAME.to_metres(samples[index].lat, samples[index].lon)

    adjacent = [i for i in positioned if i - 1 in positioned and i + 1 in positioned]

    # a reacquisition: out 60 m and back, between two fixes a second apart either side
    jump = adjacent[5]
    jx, jy = where(jump)
    move(jump, jx + 60.0, jy)

    # a one-way departure: a whole run shifted 200 m, so the track leaves and *stays* gone.
    # A single displaced fix could not test this rule -- seated between two good ones it is
    # an out-and-back by definition, which is the distinction the two rules are drawing.
    leap = next(i for i in adjacent if i > jump + 50)
    for index in [i for i in positioned if leap <= i < leap + 10]:
        ox, oy = where(index)
        move(index, ox + 200.0, oy)

    activity = session.activity.model_copy(update={"samples": samples})
    report = CleanStage().run(activity).report
    caught = {r.t: r.reason for r in report.rejections}

    assert caught.get(samples[jump].t) is RejectionReason.JUMP_AND_RETURN
    assert caught.get(samples[leap].t) is RejectionReason.IMPLIED_SPEED
    assert all(
        r.effect is RejectionEffect.DEMOTED_TO_BLIND
        for r in report.rejections
        if r.t in (samples[jump].t, samples[leap].t)
    )


# -- the one real session we have -----------------------------------------------------


def test_the_reference_session_is_cleaned_to_known_numbers(sample_fit):
    """Pins what this stage does to real data, so a threshold change has to be deliberate.

    Note the top speed: 74.8 -> 74.5 km/h. Pass 1 removes nine of the twelve readings above
    54 km/h, but the highest survives because the speed field, the odometer and the
    positions all agree it was fast. It is one second inside a stretch that is not surfing
    at all, and removing a stretch is Pass 2's job, not per-fix physics (ADR-0014).
    """
    activity = parse_activity(sample_fit.read_bytes(), sample_fit.name)
    result = CleanStage().run(activity)
    report = result.report

    assert report.counts_by_reason == {
        "implied_speed": 24,
        "implied_acceleration": 1,
        "speed_vs_odometer": 18,
    }
    assert report.fixes_before == 1849
    assert report.fixes_after == 1824
    assert report.coverage_before == pytest.approx(0.4879, abs=5e-5)
    assert report.coverage_after == pytest.approx(0.4813, abs=5e-5)

    def above_54_kmh(session):
        return sum(1 for s in session.samples if s.speed_ms is not None and s.speed_ms > 15.0)

    assert above_54_kmh(activity) == 12
    assert above_54_kmh(result.activity) == 3


def test_the_reference_sessions_worst_positional_jump_is_gone(sample_fit):
    """109 m in one second, the artefact that draws a spike clean across the map."""
    activity = parse_activity(sample_fit.read_bytes(), sample_fit.name)

    def worst_step(session):
        fixes = [s for s in session.samples if s.has_position]
        frame = LocalFrame(lat0=fixes[0].lat, lon0=fixes[0].lon)
        points = [(s.t, *frame.to_metres(s.lat, s.lon)) for s in fixes]
        return max(
            math.hypot(bx - ax, by - ay) / (bt - at_)
            for (at_, ax, ay), (bt, bx, by) in pairwise(points)
            if bt > at_
        )

    assert worst_step(activity) > 100.0
    assert worst_step(CleanStage().run(activity).activity) <= 18.0
