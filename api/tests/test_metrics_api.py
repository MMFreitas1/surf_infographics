"""`GET /activities/{id}/metrics` -- the session as its cards show it.

`/waves` commits to a count; this route describes what was counted. The promise that makes
the pair safe is that they can never disagree, so most of what is checked here is the
relationship between the two routes rather than the arithmetic inside either.

Runs against the committed synthetic fixture, so the REST surface is covered in CI where the
reference session is absent.
"""

import pytest


def metrics(client, activity_id: str) -> dict:
    response = client.get(f"/activities/{activity_id}/metrics")
    assert response.status_code == 200
    return response.json()


def test_the_two_routes_report_the_same_count(client, stored_synthetic):
    """One answer, two routes. L6 reads L5's verdicts and re-decides nothing."""
    body = metrics(client, stored_synthetic)
    waves = client.get(f"/activities/{stored_synthetic}/waves").json()

    assert body["wave_count"] == waves["wave_count"]
    assert len(body["waves"]) == waves["wave_count"]


def test_every_card_matches_a_wave_the_pipeline_settled(client, stored_synthetic):
    """Same spans, in order: no boundary moved on the way here (ADR-0016)."""
    body = metrics(client, stored_synthetic)
    settled = [
        (v["t_start"], v["t_end"])
        for v in client.get(f"/activities/{stored_synthetic}/waves").json()["verdicts"]
        if v["is_wave"]
    ]

    assert [(w["t_start"], w["t_end"]) for w in body["waves"]] == sorted(settled)


def test_the_waves_are_numbered_from_one(client, stored_synthetic):
    """The index is what the card shows, assigned here so the UI never decides it."""
    body = metrics(client, stored_synthetic)

    assert [w["index"] for w in body["waves"]] == list(range(1, len(body["waves"]) + 1))


def test_coverage_rides_through_onto_every_card(client, stored_synthetic):
    """A wave the watch never saw has to stay distinguishable from one it watched."""
    for wave in metrics(client, stored_synthetic)["waves"]:
        assert 0.0 <= wave["position_coverage"] <= 1.0


def test_the_session_reports_its_own_coverage_once(client, stored_synthetic):
    body = metrics(client, stored_synthetic)

    assert 0.0 <= body["coverage"] <= 1.0
    assert body["session_s"] > 0.0


def test_a_figure_the_recording_cannot_support_is_null(client, stored_synthetic):
    """The default synthetic session carries no distance field, so there is no distance to
    report. `0` would say the surfer never moved."""
    body = metrics(client, stored_synthetic)

    assert body["distance_m"] is None
    assert body["ride_m"] is None
    assert body["swim_m"] is None
    assert all(wave["ride_m"] is None for wave in body["waves"])


def test_the_speed_distribution_ships_with_its_summary(client, stored_synthetic):
    """Both forms, so the card can draw the session's shape and still mark its mean."""
    speed = metrics(client, stored_synthetic)["speed"]

    assert speed is not None
    assert len(speed["bin_edges_ms"]) == len(speed["counts"]) + 1
    assert sum(speed["counts"]) == speed["n_seconds"]
    assert speed["mean_ms"] > 0.0


def test_the_cadence_adds_up_to_the_count(client, stored_synthetic):
    body = metrics(client, stored_synthetic)

    assert sum(bucket["waves"] for bucket in body["cadence"]) == body["wave_count"]
    assert body["bucket_s"] == 600.0


def test_the_returns_are_one_fewer_than_the_waves(client, stored_synthetic):
    """There is no paddle back out after the last ride of the day."""
    body = metrics(client, stored_synthetic)

    assert len(body["returns"]) == max(0, body["wave_count"] - 1)


def test_asking_twice_gives_the_same_answer(client, stored_synthetic):
    """Served from the stage cache the second time, and cached means identical."""
    assert metrics(client, stored_synthetic) == metrics(client, stored_synthetic)


def test_an_unknown_activity_is_a_404(client):
    assert client.get("/activities/nope/metrics").status_code == 404


def test_a_session_with_an_odometer_reports_both_distances(client, stored_metered):
    """The Distancia card's pair: what the odometer attributed, and the part of it the watch
    actually saw. One is always a part of the other."""
    body = metrics(client, stored_metered)

    assert body["distance_m"] is not None
    assert body["ride_m"] is not None
    assert body["ride_measured_m"] <= body["ride_m"]
    assert body["swim_m"] == pytest.approx(body["distance_m"] - body["ride_m"])

    for wave in body["waves"]:
        if wave["ride_measured_m"] is not None:
            assert wave["ride_measured_m"] <= wave["ride_m"]


def test_the_reference_session_reports_eight_waves(client, stored_reference):
    """The number the pipeline commits to, from the route that describes them.

    It was eleven from Phase 7 until 2026-10-24, when Miguel labelled the session and three
    of those eleven turned out not to be waves: two were the smoother bridging a blind gap
    between distant fixes, one was him waiting for a wave that never walled up. L5 now
    refuses a candidate the device's own speedometer contradicts (ADR-0023), and
    `test_speed_corroboration.py` is where that cut is checked against the labels.

    What this still defends is the older claim, which the change did not touch: **L6 adds no
    feature to L4 and moves no threshold in L5, so it cannot move the count.** Eight is L5's
    integer, and this route only renders it.
    """
    body = metrics(client, stored_reference)

    assert body["wave_count"] == 8
    assert len(body["waves"]) == 8


def test_the_reference_session_rides_are_physically_plausible(client, stored_reference):
    """Phase 5 convicted a 74.8 km/h artefact. Nothing on a card may come from that family."""
    for wave in metrics(client, stored_reference)["waves"]:
        if wave["top_speed_ms"] is not None:
            assert wave["top_speed_ms"] < 15.0, f"wave {wave['index']} tops {wave['top_speed_ms']}"
        if wave["ride_m"] is not None:
            assert 0.0 <= wave["ride_m"] < 500.0


def test_the_peaks_route_serves_the_sits_and_their_grouping(client, stored_synthetic):
    """Its own route rather than a field on /track: a peak is a place, not a track row."""
    body = client.get(f"/activities/{stored_synthetic}/peaks").json()

    assert set(body) == {"peaks", "areas", "held_s"}
    for peak in body["peaks"]:
        assert set(peak) == {
            "lat",
            "lon",
            "t_start",
            "t_end",
            "observed_s",
            "area",
            "duration_s",
            "observed_fraction",
        }
        assert peak["observed_fraction"] >= 0.25
        assert peak["area"] < len(body["areas"])


def test_a_peak_never_reports_a_spread(client, stored_synthetic):
    """The clusterer guarantees the widest member sits at its radius, so a spread would be
    the parameter handed back as a finding (ADR-0022). There is no field for it anywhere."""
    body = client.get(f"/activities/{stored_synthetic}/peaks").json()

    for peak in body["peaks"]:
        assert "spread_m" not in peak
        assert "spread" not in peak


def test_asking_for_peaks_does_not_recompute_the_frame(client, stored_synthetic, settings):
    """Peaks hang off L1 beside L2. Fetching them must not touch a bearing (ADR-0022)."""
    client.get(f"/activities/{stored_synthetic}/track")
    before = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    client.get(f"/activities/{stored_synthetic}/peaks")
    client.get(f"/activities/{stored_synthetic}/track")
    after = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    assert set(before) <= set(after), "a frame entry disappeared when peaks were asked for"


def test_peaks_for_an_unknown_activity_is_a_404(client):
    assert client.get("/activities/nope/peaks").status_code == 404


def test_every_wave_carries_a_direction_or_says_it_has_none(client, stored_reference):
    """The point of Phase 6, on the one real recording there is.

    Miguel labelled this session a right-hand point on 2026-10-24 and said he does not ride
    straight. Seven rights and one wave with no direction at all is what that looks like:
    the eighth is three seconds the watch missed entirely, so it publishes no direction
    rather than guessing one.
    """
    waves = metrics(client, stored_reference)["waves"]
    directions = [wave["direction"] for wave in waves]

    assert directions.count("right") == 7
    assert directions.count("unknown") == 1
    assert directions.count("straight") == 0
    assert directions.count("left") == 0

    for wave in waves:
        if wave["direction"] == "unknown":
            assert wave["direction_confidence"] is None
        else:
            assert 0.0 <= wave["direction_confidence"] <= 1.0


def test_a_direction_confidence_is_never_served_as_a_calibrated_number(client, stored_reference):
    """It is a product of three stated factors, not a probability (ADR-0013). What this
    pins is that the thinnest call in the session comes back *thin* rather than confident:
    ride 11 is a right 9.1 degrees off dead-shoreward, which is real and marginal."""
    waves = metrics(client, stored_reference)["waves"]
    handed = [w for w in waves if w["direction_confidence"] is not None]

    assert min(w["direction_confidence"] for w in handed) < 0.2
    assert max(w["direction_confidence"] for w in handed) < 1.0
