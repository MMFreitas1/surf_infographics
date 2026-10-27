"""L1.5, peaks: the sitting as signal.

Three claims, and the first two are the measurement that changed the rule.

**A duration floor is not enough.** The first probe found a cluster lasting 170 s on ten
observed seconds. A stretch the watch barely saw is not evidence of sitting still, and the
floor that catches it has to be on the *fraction* of its span that was seen rather than on an
absolute count.

**Spread is not reported, because it cannot be anything but the radius.** The clusterer
extends a group while every member stays inside the radius, so the widest member lands at it
by construction. The model has no field for it and
`test_a_cluster_is_never_wider_than_the_radius_which_is_why_spread_is_not_served` is why.

**Nothing downstream may depend on this.** Peaks hang off L1 beside L2, not in front of it,
so retuning the clusterer cannot invalidate a bearing or a wave count (ADR-0022).
"""

import math

import pytest

from surf.models import AuditReport, SmoothedSample
from surf.pipeline.l1_5 import PayloadError, PeaksInput, PeaksStage
from surf.synthetic import ORIGIN_LAT, ORIGIN_LON

M_PER_DEG_LAT = 111_320.0


def at(east_m: float, north_m: float) -> tuple[float, float]:
    per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    return ORIGIN_LAT + north_m / M_PER_DEG_LAT, ORIGIN_LON + east_m / per_deg_lon


def sitting(
    t_start: float,
    seconds: int,
    *,
    east_m: float = 0.0,
    north_m: float = 0.0,
    every: int = 1,
    wobble_m: float = 2.0,
) -> list[SmoothedSample]:
    """A stretch held still at one place, with a fix every ``every`` seconds.

    ``every`` is how the observed *fraction* is driven: a sit the watch saw one second in
    four is the case the fraction floor exists to judge.
    """
    out = []
    for i in range(seconds):
        observed = i % every == 0
        lat, lon = at(east_m + wobble_m * math.sin(i / 3.0), north_m + wobble_m * math.cos(i / 5.0))
        out.append(
            SmoothedSample(
                t=t_start + i,
                lat=lat,
                lon=lon,
                vx_ms=0.1,
                vy_ms=0.1,
                position_sigma_m=2.0,
                confidence=0.9,
                observed=observed,
            )
        )
    return out


def travelling(t_start: float, seconds: int, *, speed_ms: float = 4.0):
    """Moving steadily away, so no cluster can hold."""
    return [
        SmoothedSample(
            t=t_start + i,
            lat=at(speed_ms * i, 0.0)[0],
            lon=at(speed_ms * i, 0.0)[1],
            vx_ms=speed_ms,
            vy_ms=0.0,
            position_sigma_m=2.0,
            confidence=0.9,
            observed=True,
        )
        for i in range(seconds)
    ]


def an_audit(t_start: float, t_end: float) -> AuditReport:
    return AuditReport(
        window_s=30.0,
        t_start=0.0,
        t_end=t_end + 1000.0,
        surfing_t_start=t_start,
        surfing_t_end=t_end,
    )


# -- finding a sit ------------------------------------------------------------------------


def test_a_minute_held_still_is_a_peak():
    found = PeaksStage().run(sitting(0.0, 120))

    assert len(found.peaks) == 1
    assert found.peaks[0].observed_s == 120
    assert found.peaks[0].duration_s == pytest.approx(119.0)
    assert found.held_s == pytest.approx(119.0)


def test_travelling_the_whole_time_yields_no_peak():
    assert PeaksStage().run(travelling(0.0, 300)).peaks == []


def test_a_sit_shorter_than_the_floor_is_not_a_peak():
    """Under a minute is a pause between paddle strokes."""
    assert PeaksStage().run(sitting(0.0, 45)).peaks == []


def test_two_sits_in_different_places_are_two_peaks():
    track = sitting(0.0, 100) + travelling(200.0, 30) + sitting(400.0, 100, east_m=300.0)

    found = PeaksStage().run(track)

    assert len(found.peaks) == 2
    assert found.peaks[0].t_start < found.peaks[1].t_start


def test_peaks_come_back_in_time_order():
    track = sitting(0.0, 90) + sitting(500.0, 90, east_m=400.0) + sitting(1000.0, 90)

    found = PeaksStage().run(track)

    times = [peak.t_start for peak in found.peaks]
    assert times == sorted(times)


# -- the floor the measurement added ------------------------------------------------------


def test_a_long_span_the_watch_barely_saw_is_not_a_peak():
    """The caveat the first probe raised, as a test.

    170 seconds on ten observed is a fraction of 0.06. An absolute seconds floor separates
    this worse: ten seconds is a plausible count for a genuinely blind sit, and the thing
    that makes it meaningless is how little of its *own span* it covers.
    """
    barely = sitting(0.0, 170, every=17)

    assert len([s for s in barely if s.observed]) == 10
    assert PeaksStage().run(barely).peaks == []


def test_an_ordinarily_blind_sit_still_counts():
    """The floor is 0.25 against a session that averages 0.40, so a normally submerged
    wrist does not cost a peak. A floor set at the session's own coverage would."""
    found = PeaksStage().run(sitting(0.0, 160, every=3))

    assert len(found.peaks) == 1
    assert 0.25 <= found.peaks[0].observed_fraction < 0.40


def test_the_fraction_floor_is_what_rejects_it_not_the_duration():
    """Same span, same place; only how much of it was seen differs."""
    stage = PeaksStage()
    seen = sitting(0.0, 170, every=2)
    unseen = sitting(0.0, 170, every=17)

    assert len(stage.run(seen).peaks) == 1
    assert stage.run(unseen).peaks == []
    assert PeaksStage(min_observed_fraction=0.0).run(unseen).peaks != []


# -- one bank, not several peaks ----------------------------------------------------------


def test_sits_near_each_other_are_one_area():
    """Centroids 4-80 m apart are one sandbank. Measured: the reference session's eleven
    clusters collapse to a single area at every merge distance at or above 50 m."""
    track = sitting(0.0, 90) + sitting(200.0, 90, east_m=35.0) + sitting(400.0, 90, east_m=70.0)

    found = PeaksStage().run(track)

    assert len(found.peaks) == 3
    assert len(found.areas) == 1
    assert found.areas[0].peaks == 3
    assert {peak.area for peak in found.peaks} == {0}


def test_sits_far_apart_are_different_areas():
    track = sitting(0.0, 90) + sitting(400.0, 90, east_m=600.0)

    found = PeaksStage().run(track)

    assert len(found.areas) == 2
    assert {peak.area for peak in found.peaks} == {0, 1}


def test_merging_is_single_link_so_a_strung_out_bank_stays_one_place():
    """Three sits 40 m apart in a line are one bank even though the ends are 80 m apart."""
    track = sitting(0.0, 90) + sitting(200.0, 90, east_m=40.0) + sitting(400.0, 90, east_m=80.0)

    assert len(PeaksStage(merge_m=50.0).run(track).areas) == 1


def test_an_area_centroid_is_weighted_by_how_long_each_sit_lasted():
    """A twenty-minute sit and a one-minute sit are not the same evidence about where the
    peak is, and the measured stability of this point is what lets nothing depend on the
    clusterer's parameters."""
    track = sitting(0.0, 600) + sitting(700.0, 70, east_m=40.0)

    area = PeaksStage().run(track).areas[0]
    near, far = at(0.0, 0.0), at(40.0, 0.0)

    assert abs(area.lon - near[1]) < abs(area.lon - far[1])


# -- what is not reported -----------------------------------------------------------------


def test_a_cluster_is_never_wider_than_the_radius_which_is_why_spread_is_not_served():
    """Spread equalled the radius at every radius swept, because the rule guarantees it.

    So there is no field for it: reporting it would be handing the parameter back as a
    finding. This test is the reason, written down where someone would come to add it.
    """
    from surf.models import Peak

    assert "spread_m" not in Peak.model_fields
    assert "spread" not in Peak.model_fields

    stage = PeaksStage(radius_m=12.0)
    track = sitting(0.0, 200, wobble_m=30.0)

    per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    for peak in stage.run(track).peaks:
        members = [s for s in track if peak.t_start <= s.t <= peak.t_end and s.observed]
        widest = max(
            math.hypot((s.lon - peak.lon) * per_deg_lon, (s.lat - peak.lat) * M_PER_DEG_LAT)
            for s in members
        )
        assert widest <= stage.radius_m + 1e-6


# -- the audit, and the key ---------------------------------------------------------------


def test_the_walk_up_the_beach_is_not_a_peak():
    """Standing still on the sand for eight minutes is the most convincing sit in the file,
    and it is not surfing. The audit is what excludes it (ADR-0015)."""
    track = sitting(0.0, 300, east_m=400.0) + sitting(400.0, 300)

    with_audit = PeaksStage().run(PeaksInput(track=track, audit=an_audit(400.0, 800.0)))
    without = PeaksStage().run(track)

    assert len(with_audit.peaks) == 1
    assert len(without.peaks) == 2


def test_the_audit_key_travels_in_the_params():
    """ADR-0015's pattern, the third place it appears: a peak sited in the walk is not a
    peak, so a different audit re-keys -- but the audit changes no sample."""
    params = PeaksStage(audit_key="xyz").meta.params

    assert params["audit_key"] == "xyz"
    assert params != PeaksStage().meta.params


def test_every_parameter_that_moves_a_peak_is_in_the_key():
    base = PeaksStage().meta.params

    assert PeaksStage(radius_m=25.0).meta.params != base
    assert PeaksStage(min_duration_s=90.0).meta.params != base
    assert PeaksStage(min_observed_fraction=0.4).meta.params != base
    assert PeaksStage(merge_m=80.0).meta.params != base


# -- the payload ---------------------------------------------------------------------------


def test_the_payload_round_trips_the_areas_as_well_as_the_peaks():
    """A cache hit has to return everything a run would, so the grouping travels too."""
    stage = PeaksStage()
    track = sitting(0.0, 120) + sitting(400.0, 120, east_m=500.0)
    found = stage.run(track)

    restored = stage.decode(stage.encode(found))

    assert restored == found
    assert len(restored.areas) == 2


def test_an_empty_result_round_trips():
    stage = PeaksStage()
    empty = stage.run(travelling(0.0, 100))

    assert stage.decode(stage.encode(empty)) == empty


def test_a_payload_this_stage_did_not_write_is_refused():
    import pyarrow as pa
    import pyarrow.parquet as pq

    sink = pa.BufferOutputStream()
    pq.write_table(pa.table({"lat": pa.array([1.0])}), sink)

    with pytest.raises(PayloadError):
        PeaksStage().decode(bytes(sink.getvalue().to_pybytes()))


def test_a_session_with_no_positions_at_all_yields_nothing_rather_than_failing():
    blind = [
        SmoothedSample(
            t=float(i),
            lat=ORIGIN_LAT,
            lon=ORIGIN_LON,
            vx_ms=0.0,
            vy_ms=0.0,
            position_sigma_m=50.0,
            confidence=0.1,
            observed=False,
        )
        for i in range(200)
    ]

    found = PeaksStage().run(blind)

    assert found.peaks == []
    assert found.areas == []
    assert found.held_s == 0.0


# -- the reference session, which is where these numbers came from -------------------------


def test_the_reference_session_reproduces_the_measured_peaks(sample_fit):
    """The known-answer test. Skips without ``sample_data/``, which is every CI run.

    These are the numbers PLAN.md records, and they are pinned here so that a change to the
    clusterer, the cleaner or the smoother has to be argued with rather than absorbed.
    """
    from surf.ingest import parse_file
    from surf.pipeline.audit import AuditStage
    from surf.pipeline.clean import CleanStage
    from surf.pipeline.l1 import KinematicsStage

    cleaned = CleanStage().run(parse_file(sample_fit))
    audit = AuditStage().run(cleaned.activity)
    track = KinematicsStage().run(cleaned.activity)
    payload = PeaksInput(track=track, audit=audit)

    found = PeaksStage().run(payload)

    assert len(found.peaks) == 8
    assert len(found.areas) == 1, "eleven clusters on one bank, not eleven peaks"
    assert found.areas[0].observed_s == 482
    assert round(found.held_s) == 1004
    assert all(peak.observed_fraction >= 0.25 for peak in found.peaks)


def test_dropping_the_fraction_floor_reproduces_the_first_probe(sample_fit):
    """2026-10-22, before any Phase 6 code existed: 11 clusters holding 41.4% of the
    session, the thinnest of them 170 s on 10 observed seconds. That probe is what the
    fraction floor was added in response to, so it is worth being able to reproduce."""
    from surf.ingest import parse_file
    from surf.pipeline.audit import AuditStage
    from surf.pipeline.clean import CleanStage
    from surf.pipeline.l1 import KinematicsStage

    cleaned = CleanStage().run(parse_file(sample_fit))
    audit = AuditStage().run(cleaned.activity)
    track = KinematicsStage().run(cleaned.activity)
    session_s = audit.surfing_t_end - audit.surfing_t_start

    probe = PeaksStage(min_observed_fraction=0.0).run(PeaksInput(track=track, audit=audit))

    assert len(probe.peaks) == 11
    assert round(probe.held_s) == 1366
    assert probe.held_s / session_s == pytest.approx(0.414, abs=0.002)
    assert min(peak.observed_fraction for peak in probe.peaks) == pytest.approx(0.059, abs=0.002)


def test_the_bank_is_one_place_at_every_merge_distance_the_measurement_swept(sample_fit):
    from surf.ingest import parse_file
    from surf.pipeline.audit import AuditStage
    from surf.pipeline.clean import CleanStage
    from surf.pipeline.l1 import KinematicsStage

    cleaned = CleanStage().run(parse_file(sample_fit))
    audit = AuditStage().run(cleaned.activity)
    track = KinematicsStage().run(cleaned.activity)
    payload = PeaksInput(track=track, audit=audit)

    for merge_m in (50.0, 80.0, 125.0):
        assert len(PeaksStage(merge_m=merge_m).run(payload).areas) == 1
