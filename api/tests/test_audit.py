"""L0.6: does the audit find the session inside the recording, without eating any of it.

Two mistakes are possible and they are not equally bad. Leaving the walk up the beach in the
session skews a duration and a distance. Trimming a real ride out of it destroys the thing the
product exists to measure, and leaves no trace that it happened.

So the tests that matter most here are the ones that watch the boundary from the inside:
`test_a_dry_but_fast_window_is_not_trimmed` pins the case that made the first version of this
rule wrong, and `test_no_genuine_ride_is_ever_trimmed_away` sweeps five seeded sessions whose
rides are known exactly.
"""

import json
from dataclasses import replace

import pytest

from surf.geo import LocalFrame
from surf.ingest import parse_activity
from surf.ingest.blind import derive_blind_windows
from surf.models import Activity, AuditSource, Fidelity, NotSurfingReason, Sample, SessionWindow
from surf.pipeline.audit import AuditStage, PayloadError
from surf.pipeline.clean import CleanStage
from surf.synthetic import SyntheticParams, make_synthetic_session

FRAME = LocalFrame(lat0=38.0, lon0=-9.0)


def block(seconds, *, fix_every=1, speed=0.0, drift=0.5):
    """``seconds`` seconds where one second in ``fix_every`` carries a position.

    ``fix_every=1`` is a dry window at coverage 1.0; ``fix_every=3`` is an in-water one at
    0.33. Stating it this way keeps each case's coverage readable at the call site, which is
    the whole variable under test.
    """
    return [(index % fix_every == 0, speed, drift) for index in range(seconds)]


def make_session(*blocks: list):
    """A 1 Hz session assembled from blocks, with positions marching slowly east."""
    samples = []
    x = 0.0
    for seconds in blocks:
        for has_fix, speed, drift in seconds:
            x += drift
            lat = lon = None
            if has_fix:
                lat, lon = FRAME.to_degrees(x, 0.0)
            samples.append(
                Sample(
                    t=float(len(samples)),
                    lat=lat,
                    lon=lon,
                    speed_ms=speed if has_fix else None,
                )
            )
    return Activity(
        activity_id="audit-test",
        sport="surfing",
        start_time=0.0,
        fidelity=Fidelity.FIT,
        samples=samples,
        blind_windows=derive_blind_windows(samples),
    )


def surfing(report):
    """The span the audit calls the session."""
    return report.surfing_t_start, report.surfing_t_end


def excluded(report, reason):
    """Excluded stretches carrying one reason."""
    return [w for w in report.not_surfing if w.reason is reason]


@pytest.fixture(scope="module")
def dry_tailed_seeds():
    """Five seeded sessions, each ending in a known walk up the beach."""
    return [
        make_synthetic_session(SyntheticParams(seed=seed, walk_out_s=120, idle_s=180))
        for seed in (7, 11, 23, 42, 101)
    ]


# -- the digest -----------------------------------------------------------------------


def test_the_digest_carries_no_location_whatsoever():
    """The property that makes the opt-in hosted model path safe by construction rather than
    by policy: there is no coordinate in the payload to leak, and no bearing either."""
    fields = set(SessionWindow.model_fields)
    assert not fields & {"lat", "lon", "origin_lat", "origin_lon", "bearing", "heading"}
    assert fields == {
        "t_start",
        "t_end",
        "sample_count",
        "coverage",
        "speed_mean_ms",
        "speed_max_ms",
        "speed_sd_ms",
        "odometer_rate_ms",
        "hr_mean_bpm",
    }


def test_the_digest_measures_coverage_per_window():
    activity = make_session(block(60, fix_every=1), block(60, fix_every=4))
    windows = AuditStage().digest(activity.samples)

    assert [w.coverage for w in windows] == [1.0, 0.25]
    assert [w.sample_count for w in windows] == [60, 60]
    assert [w.duration_s for w in windows] == [60.0, 60.0]


def test_a_window_with_no_fix_at_all_reports_no_speed_rather_than_zero():
    """Zero would read as "the surfer was stationary", which is a different claim."""
    window = AuditStage().digest(make_session(block(60, fix_every=1000)).samples)[0]
    assert window.coverage == pytest.approx(1 / 60)
    assert window.speed_sd_ms is None


# -- finding the session --------------------------------------------------------------


def test_a_dry_still_tail_is_excluded():
    activity = make_session(
        block(600, fix_every=3, speed=2.0),
        block(300, fix_every=1, speed=0.2, drift=0.0),
    )
    report = AuditStage().run(activity)

    assert surfing(report) == (0.0, 600.0)
    after = excluded(report, NotSurfingReason.AFTER_EXIT)
    assert [(w.t_start, w.t_end) for w in after] == [(600.0, 899.0)]
    assert after[0].source is AuditSource.BASELINE


def test_a_dry_still_head_is_excluded():
    activity = make_session(
        block(120, fix_every=1, speed=0.3, drift=0.0),
        block(600, fix_every=3, speed=2.0),
    )
    report = AuditStage().run(activity)

    assert report.surfing_t_start == 120.0
    assert [w.reason for w in report.not_surfing] == [NotSurfingReason.BEFORE_ENTRY]


def test_an_interior_dry_stretch_is_left_alone():
    """The decision this rule turns on. A surfer sitting up with the wrist clear of the water
    reads exactly like one standing on the sand, and cutting the session at every lull
    fragmented a 63-minute recording into 11 minutes when I tried it on the real one.
    """
    activity = make_session(
        block(300, fix_every=3, speed=2.0),
        block(180, fix_every=1, speed=0.2, drift=0.0),
        block(300, fix_every=3, speed=2.0),
    )
    report = AuditStage().run(activity)

    assert surfing(report) == (0.0, 779.0)
    assert report.not_surfing == []


def test_a_dry_but_fast_window_is_not_trimmed():
    """A rider standing up has a dry wrist, so the last ride of a session can be the
    best-covered window in the file. Trimming on coverage alone cut it off."""
    activity = make_session(
        block(300, fix_every=3, speed=2.0),
        block(60, fix_every=1, speed=7.0),
        block(300, fix_every=1, speed=0.2, drift=0.0),
    )
    report = AuditStage().run(activity)

    assert report.surfing_t_end == 360.0, "the ride at 300..360 was trimmed away"


def test_a_recording_that_never_looks_wet_is_not_judged():
    """An absent answer, stated. Nothing is excluded and `decided` says why."""
    report = AuditStage().run(make_session(block(600, fix_every=1, speed=0.3, drift=0.0)))

    assert report.decided is False
    assert report.not_surfing == []
    assert surfing(report) == (report.t_start, report.t_end)


def test_a_recording_that_is_all_session_excludes_nothing():
    report = AuditStage().run(make_session(block(600, fix_every=3, speed=2.0)))

    assert report.decided is True
    assert report.not_surfing == []
    assert report.excluded_s == 0.0


# -- what exclusion does, and does not, do --------------------------------------------


def test_exclusion_leaves_every_sample_exactly_as_it_was():
    """The whole of ADR-0015 in one assertion. These seconds were measured perfectly; the
    watch could see, the surfer simply was not surfing. Demoting them would claim blindness
    we did not have and would drop coverage by a fifth on the reference session."""
    activity = make_session(
        block(600, fix_every=3, speed=2.0),
        block(300, fix_every=1, speed=0.2, drift=0.0),
    )
    before = [s.model_dump() for s in activity.samples]
    AuditStage().run(activity)

    assert [s.model_dump() for s in activity.samples] == before
    assert all(s.has_position for s in activity.samples[600:])


def test_the_top_speed_is_reported_over_the_session_and_over_everything():
    """The number Phase 5 is about, computed where the span is decided."""
    activity = make_session(
        block(600, fix_every=3, speed=4.0),
        block(300, fix_every=1, speed=9.0, drift=0.0),
    )
    stage = replace(AuditStage(), out_of_water_speed_max=12.0)
    report = stage.run(activity)

    assert report.top_speed_ms_all == pytest.approx(9.0)
    assert report.top_speed_ms_surfing == pytest.approx(4.0)
    assert report.surfing_s == 600.0
    assert report.excluded_s == 299.0


# -- payload --------------------------------------------------------------------------


def test_the_payload_round_trips_exactly():
    stage = AuditStage()
    report = stage.run(
        make_session(block(600, fix_every=3, speed=2.0), block(300, fix_every=1, drift=0.0))
    )
    assert stage.decode(stage.encode(report)) == report


def test_a_payload_from_somewhere_else_is_refused():
    with pytest.raises(PayloadError, match="was not written by this stage"):
        AuditStage().decode(json.dumps({"something": "else"}).encode("utf-8"))


def test_a_threshold_change_is_a_different_stage_identity():
    """Arguing with a boundary has to be a re-key, not a re-ingest."""
    default = AuditStage().meta.params
    loosened = replace(AuditStage(), wet_coverage_max=0.5).meta.params
    assert default != loosened


# -- against known truth --------------------------------------------------------------


def test_no_genuine_ride_is_ever_trimmed_away(dry_tailed_seeds):
    """The failure that would leave no trace. Five seeded sessions, rides known exactly."""
    stage = AuditStage()
    for session in dry_tailed_seeds:
        cleaned = CleanStage().run(session.activity).activity
        report = stage.run(cleaned)
        lost = [
            ride
            for ride in session.truth
            if ride.t_start < report.surfing_t_start or ride.t_end > report.surfing_t_end
        ]
        assert lost == [], f"trimmed {len(lost)} real rides out of {session.activity.activity_id}"


def test_the_known_walk_up_the_beach_is_recovered(dry_tailed_seeds):
    """Within the digest's own resolution -- the boundary cannot be sharper than a window."""
    stage = AuditStage()
    for session in dry_tailed_seeds:
        cleaned = CleanStage().run(session.activity).activity
        report = stage.run(cleaned)
        truth = session.out_of_water[0]
        found = excluded(report, NotSurfingReason.AFTER_EXIT)

        assert found, f"missed the walk entirely on {session.activity.activity_id}"
        assert abs(found[0].t_start - truth.t_start) <= 2 * stage.window_s
        left_in = max(0.0, min(report.surfing_t_end, truth.t_end) - truth.t_start)
        assert left_in <= stage.window_s


def test_a_session_with_no_walk_has_nothing_to_exclude_at_the_end():
    """The generator's default session ends in the water, so a tail found there is a false
    positive rather than a boundary."""
    session = make_synthetic_session()
    cleaned = CleanStage().run(session.activity).activity
    report = AuditStage().run(cleaned)

    assert excluded(report, NotSurfingReason.AFTER_EXIT) == []


# -- the one real session we have -----------------------------------------------------


def test_the_reference_session_is_trimmed_to_known_bounds(sample_fit):
    """Pins the boundary on real data, so moving a threshold has to be deliberate.

    The last 430 seconds are coverage 1.00 at roughly zero speed -- the watch is on the sand
    with the recording still running. The first 60 are the walk down.
    """
    activity = parse_activity(sample_fit.read_bytes(), sample_fit.name)
    cleaned = CleanStage().run(activity).activity
    report = AuditStage().run(cleaned)
    origin = cleaned.samples[0].t

    assert report.decided is True
    assert len(report.windows) == 64
    assert report.surfing_t_start - origin == 60.0
    assert report.surfing_t_end - origin == 3360.0
    assert report.excluded_s == 490.0
    assert [w.reason for w in report.not_surfing] == [
        NotSurfingReason.BEFORE_ENTRY,
        NotSurfingReason.AFTER_EXIT,
    ]


def test_the_reference_sessions_excluded_tail_really_is_dry_and_still(sample_fit):
    """Guards the verdict rather than the threshold: whatever number produced this span, the
    stretch it cut off has to actually look like a watch sitting on the sand."""
    activity = parse_activity(sample_fit.read_bytes(), sample_fit.name)
    cleaned = CleanStage().run(activity).activity
    report = AuditStage().run(cleaned)

    tail = [w for w in report.windows if w.t_start >= report.surfing_t_end]
    assert tail
    assert all(w.coverage > 0.9 for w in tail)
    assert all((w.speed_max_ms or 0.0) < 2.0 for w in tail)


def test_the_reference_sessions_top_speed_is_unchanged_by_the_trim(sample_fit):
    """Honest bookkeeping: on this session the artefact was already gone before the audit ran
    (ADR-0014's amendment), so trimming the walk changes the duration and not the top speed.
    The two numbers ship side by side precisely so that is visible rather than assumed."""
    activity = parse_activity(sample_fit.read_bytes(), sample_fit.name)
    cleaned = CleanStage().run(activity).activity
    report = AuditStage().run(cleaned)

    assert report.top_speed_ms_all == pytest.approx(report.top_speed_ms_surfing)
    assert report.top_speed_ms_surfing * 3.6 == pytest.approx(54.1, abs=0.1)
    assert report.surfing_s == 3300.0
