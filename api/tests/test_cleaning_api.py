"""The cleaning endpoint: what the pipeline refused to believe, and why.

A cleaner that silently drops data is indistinguishable from a bug, so the rejections have
to be *servable* rather than merely logged. These tests hold the endpoint to that, and to
the one contract the rest of the app depends on: the raw activity keeps saying what the
device recorded, the track says what we believe, and this endpoint is what reconciles them.
"""


def test_a_clean_session_reports_nothing_and_says_so(client, stored_synthetic):
    """Zero rejections is a result, not an empty response. The counts still have to ship."""
    body = client.get(f"/activities/{stored_synthetic}/cleaning").json()

    assert body["rejections"] == []
    assert body["counts_by_reason"] == {}
    assert body["enabled"] is True
    assert body["fixes_before"] == body["fixes_after"] > 0
    assert body["coverage_before"] == body["coverage_after"]


def test_an_impossible_fix_is_reported_with_the_evidence_that_convicted_it(client, stored_dirty):
    body = client.get(f"/activities/{stored_dirty}/cleaning").json()

    assert len(body["rejections"]) == 1
    rejected = body["rejections"][0]
    assert rejected["effect"] == "demoted_to_blind"
    assert rejected["value"] > rejected["limit"]
    assert sum(body["counts_by_reason"].values()) == 1


def test_a_rejection_never_carries_coordinates_over_the_wire(client, stored_dirty):
    """The repo is public and these bodies reach goldens and logs (CLAUDE.md)."""
    body = client.get(f"/activities/{stored_dirty}/cleaning").json()
    assert set(body["rejections"][0]) == {"t", "reason", "effect", "value", "limit"}


def test_coverage_falls_by_exactly_the_fixes_that_were_demoted(client, stored_dirty):
    """The number that makes the cleaner arguable: what went in against what came out."""
    body = client.get(f"/activities/{stored_dirty}/cleaning").json()

    demoted = [r for r in body["rejections"] if r["effect"] == "demoted_to_blind"]
    assert body["fixes_before"] - body["fixes_after"] == len(demoted)
    assert body["coverage_after"] < body["coverage_before"]


def test_the_raw_activity_still_reports_what_the_device_recorded(client, stored_dirty):
    """The store holds the recording, not our opinion of it. Cleaning is a stage, and the
    endpoint above is what explains the difference between the two."""
    body = client.get(f"/activities/{stored_dirty}/cleaning").json()
    activity = client.get(f"/activities/{stored_dirty}").json()

    rejected_at = {r["t"] for r in body["rejections"] if r["effect"] == "demoted_to_blind"}
    still_positioned = {
        s["t"] for s in activity["samples"] if s["has_position"] and s["t"] in rejected_at
    }
    assert still_positioned == rejected_at


def test_the_track_stops_calling_a_rejected_second_observed(client, stored_dirty):
    """The other half of that contract, and the one that matters for honesty: nothing
    downstream may go on treating a refused fix as a second the watch saw (ADR-0010)."""
    body = client.get(f"/activities/{stored_dirty}/cleaning").json()
    track = client.get(f"/activities/{stored_dirty}/track").json()

    rejected_at = {r["t"] for r in body["rejections"] if r["effect"] == "demoted_to_blind"}
    observed_at = {row["t"] for row in track["smoothed"] if row["observed"]}
    assert rejected_at and not (rejected_at & observed_at)


def test_asking_twice_does_no_extra_work(client, stored_dirty, settings):
    """Device confidence is read on every session screen, so it comes from the cache."""
    client.get(f"/activities/{stored_dirty}/cleaning")
    after_first = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    second = client.get(f"/activities/{stored_dirty}/cleaning")
    after_second = sorted(p.name for p in settings.cache_dir.rglob("*") if p.is_file())

    assert second.status_code == 200
    assert after_second == after_first


def test_reading_the_report_does_not_require_smoothing_the_session(client, stored_dirty, settings):
    """Its own entry point, not a field on the track: asking what the recording was worth
    must not cost a Kalman pass over the whole session."""
    client.get(f"/activities/{stored_dirty}/cleaning")
    stages = {p.parent.name for p in settings.cache_dir.rglob("*") if p.is_file()}
    assert "L1" not in stages


def test_an_unknown_activity_has_no_cleaning_report(client):
    assert client.get("/activities/nope/cleaning").status_code == 404
