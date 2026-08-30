"""The track and candidate endpoints: what the labeling UI draws a session from.

The property these tests exist to protect is the one the whole product rests on: a second
the watch measured and a second the smoother invented must be distinguishable at the API
boundary, not merely inside the pipeline (ADR-0010). If ``observed`` ever stops matching
the recorded fixes, a labeller marks an interpolated stretch believing they saw it.
"""

from surf.synthetic import make_synthetic_session


def test_the_track_returns_one_row_per_second_of_the_session(client, stored_synthetic):
    activity = client.get(f"/activities/{stored_synthetic}").json()
    body = client.get(f"/activities/{stored_synthetic}/track").json()

    assert len(body["smoothed"]) == len(activity["samples"])
    assert len(body["framed"]) == len(body["smoothed"])


def test_the_two_tracks_are_index_aligned(client, stored_synthetic):
    """The UI zips them by index, so the API has to guarantee they line up."""
    body = client.get(f"/activities/{stored_synthetic}/track").json()
    for smoothed, framed in zip(body["smoothed"], body["framed"], strict=True):
        assert smoothed["t"] == framed["t"]
        assert smoothed["observed"] == framed["observed"]
        assert smoothed["confidence"] == framed["confidence"]


def test_observed_matches_the_seconds_that_actually_carried_a_fix(client, stored_synthetic):
    """The measured/estimated line, checked against the recorded samples themselves."""
    activity = client.get(f"/activities/{stored_synthetic}").json()
    body = client.get(f"/activities/{stored_synthetic}/track").json()

    recorded = [sample["has_position"] for sample in activity["samples"]]
    served = [row["observed"] for row in body["smoothed"]]
    assert served == recorded
    assert False in recorded, "fixture must contain blind seconds or this proves nothing"


def test_every_second_carries_a_position_and_a_stated_uncertainty(client, stored_synthetic):
    """An estimate exists even where a fix did not -- and says how loose it is, in metres."""
    body = client.get(f"/activities/{stored_synthetic}/track").json()
    assert all(row["lat"] is not None and row["lon"] is not None for row in body["smoothed"])
    assert all(row["position_sigma_m"] >= 0.0 for row in body["smoothed"])

    blind = [r for r in body["smoothed"] if not r["observed"]]
    seen = [r for r in body["smoothed"] if r["observed"]]
    worst_blind = max(r["position_sigma_m"] for r in blind)
    best_seen = min(r["position_sigma_m"] for r in seen)
    assert worst_blind > best_seen, "an invented second must not look as certain as a measured one"


def test_the_frame_is_served_with_its_reliability_not_without_it(client, stored_synthetic):
    """An unreliable bearing is an answer (ADR-0011). The UI needs it to refuse to draw."""
    frame = client.get(f"/activities/{stored_synthetic}/track").json()["frame"]
    assert set(frame) == {
        "shore_bearing_deg",
        "coherence",
        "reliable",
        "contributing_seconds",
        "effective_seconds",
        "origin_lat",
        "origin_lon",
    }
    assert isinstance(frame["reliable"], bool)


def test_scrubbing_a_session_twice_does_no_extra_work(client, stored_synthetic, settings):
    """architecture.md §7: interactive scrubbing is served from the stage cache."""
    client.get(f"/activities/{stored_synthetic}/track")
    after_first = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    second = client.get(f"/activities/{stored_synthetic}/track")
    after_second = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    assert second.status_code == 200
    assert after_second == after_first, "a second scrub re-ran a stage instead of reading the cache"


def test_candidates_come_back_with_the_frame_they_were_measured_against(client, stored_synthetic):
    """A proposal is only as trustworthy as the axis behind it, so the two travel together."""
    track = client.get(f"/activities/{stored_synthetic}/track").json()
    proposed = client.get(f"/activities/{stored_synthetic}/candidates").json()

    assert proposed["frame"] == track["frame"]
    assert proposed["candidates"], "the synthetic session has rides; L3 should propose something"


def test_candidates_propose_but_do_not_judge(client, stored_synthetic):
    """L3 has no ground truth to justify a score or a direction, so it claims neither."""
    for candidate in client.get(f"/activities/{stored_synthetic}/candidates").json()["candidates"]:
        assert candidate["score"] is None
        assert candidate["direction"] == "unknown"
        assert candidate["duration_s"] > 0.0
        assert 0.0 <= candidate["position_coverage"] <= 1.0


def test_a_candidate_built_from_estimated_seconds_says_so(client, stored_synthetic):
    """position_coverage is what tells a labeller which proposals to distrust."""
    proposed = client.get(f"/activities/{stored_synthetic}/candidates").json()["candidates"]
    assert any(c["position_coverage"] < 1.0 for c in proposed)


def test_the_track_covers_the_same_span_the_session_does(client, stored_synthetic):
    session = make_synthetic_session()
    body = client.get(f"/activities/{stored_synthetic}/track").json()
    assert body["smoothed"][0]["t"] == session.activity.samples[0].t
    assert body["smoothed"][-1]["t"] == session.activity.samples[-1].t


def test_an_unknown_activity_has_no_track_and_no_candidates(client):
    assert client.get("/activities/nope/track").status_code == 404
    assert client.get("/activities/nope/candidates").status_code == 404
