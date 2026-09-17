"""The audit endpoint: which span of the recording is the session.

The contract these tests defend is the one that separates this from Pass 1. A rejected fix
is demoted and stops counting as coverage; an excluded stretch is *not* demoted, and every
sample in it is still served, still positioned, still `observed`. The difference matters
because the walk up the beach is measured perfectly well — better than the surfing is — and
saying otherwise would be a lie about the recording rather than a judgement about the session.
"""


def test_a_session_that_ends_in_the_water_excludes_nothing(client, stored_synthetic):
    """Nothing to trim is a result. The report still ships its span and its digest."""
    body = client.get(f"/activities/{stored_synthetic}/audit").json()

    assert body["decided"] is True
    assert body["not_surfing"] == []
    assert body["excluded_s"] == 0.0
    assert body["surfing_t_start"] == body["t_start"]
    assert body["surfing_t_end"] == body["t_end"]
    assert body["windows"], "the digest travels with the verdict so it can be argued with"


def test_a_walk_up_the_beach_is_excluded_with_its_reason(client, stored_walked_out):
    body = client.get(f"/activities/{stored_walked_out}/audit").json()

    assert body["decided"] is True
    excluded = body["not_surfing"]
    assert [w["reason"] for w in excluded] == ["after_exit"]
    assert excluded[0]["source"] == "baseline"
    assert 0.0 < excluded[0]["confidence"] < 1.0, "a good rule, not a certainty"
    assert body["surfing_t_end"] < body["t_end"]
    assert body["excluded_s"] > 240.0


def test_the_digest_never_carries_a_coordinate_over_the_wire(client, stored_walked_out):
    """What makes the opt-in hosted model path safe by construction: there is no location in
    the payload to send anywhere."""
    body = client.get(f"/activities/{stored_walked_out}/audit").json()

    assert set(body["windows"][0]) == {
        "t_start",
        "t_end",
        "sample_count",
        "coverage",
        "speed_mean_ms",
        "speed_max_ms",
        "speed_sd_ms",
        "odometer_rate_ms",
        "hr_mean_bpm",
        "duration_s",
    }


def test_an_excluded_second_is_still_served_in_full(client, stored_walked_out):
    """Exclusion, never demotion (ADR-0015). The API must keep saying what was recorded."""
    body = client.get(f"/activities/{stored_walked_out}/audit").json()
    activity = client.get(f"/activities/{stored_walked_out}").json()

    cut = body["not_surfing"][0]
    inside = [s for s in activity["samples"] if cut["t_start"] <= s["t"] < cut["t_end"]]
    assert inside
    assert all(s["has_position"] for s in inside)
    assert all(s["lat"] is not None and s["speed_ms"] is not None for s in inside)


def test_the_track_still_covers_the_whole_recording(client, stored_walked_out):
    """The audit decides what counts, not what exists. Trimming the track instead would make
    the excluded stretch unreviewable — and somebody has to be able to check the verdict."""
    body = client.get(f"/activities/{stored_walked_out}/audit").json()
    track = client.get(f"/activities/{stored_walked_out}/track").json()

    assert track["smoothed"][-1]["t"] == body["t_end"]
    assert track["smoothed"][-1]["t"] > body["surfing_t_end"]
    assert all(row["observed"] for row in track["smoothed"] if row["t"] >= body["surfing_t_end"])


def test_the_two_top_speeds_ship_side_by_side(client, stored_walked_out):
    """The number Phase 5 is about, and the number it is being compared against. Shipping
    only the second would hide what the exclusion did."""
    body = client.get(f"/activities/{stored_walked_out}/audit").json()

    assert body["top_speed_ms_all"] is not None
    assert body["top_speed_ms_surfing"] is not None
    assert body["top_speed_ms_surfing"] <= body["top_speed_ms_all"]


def test_asking_twice_does_no_extra_work(client, stored_walked_out, settings):
    client.get(f"/activities/{stored_walked_out}/audit")
    after_first = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    second = client.get(f"/activities/{stored_walked_out}/audit")
    after_second = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    assert second.status_code == 200
    assert after_second == after_first


def test_the_audit_does_not_smooth_the_session_to_answer(client, stored_walked_out, settings):
    """It hangs off the cleaner beside L1, not beneath it, so asking which minutes were
    surfing must not cost a Kalman pass over the whole recording."""
    client.get(f"/activities/{stored_walked_out}/audit")
    stages = {p.parent.name for p in settings.cache_dir.rglob("*") if p.is_file()}

    assert "L0.6" in stages
    assert "L1" not in stages


def test_an_unknown_activity_has_no_audit(client):
    assert client.get("/activities/nope/audit").status_code == 404
