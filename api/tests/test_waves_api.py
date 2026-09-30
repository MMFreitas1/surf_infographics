"""`GET /activities/{id}/waves` -- the one route that answers rather than proposes.

Everything else the API serves hands back evidence: a track, a digest, a set of unjudged
proposals. This hands back a **count**, and the tests here are mostly about the promises that
come with committing to one.

Runs against the committed synthetic fixture, so it covers the REST surface in CI where the
reference session is absent.
"""

from surf.models import DecidedBy


def waves(client, activity_id: str) -> dict:
    response = client.get(f"/activities/{activity_id}/waves")
    assert response.status_code == 200
    return response.json()


def test_it_commits_to_a_count(client, stored_synthetic):
    """One integer, always -- the thing the screen renders at 104px."""
    body = waves(client, stored_synthetic)

    assert isinstance(body["wave_count"], int)
    assert body["wave_count"] >= 0


def test_every_proposal_comes_back_with_a_verdict(client, stored_synthetic):
    """The count can be taken apart. Nothing is dropped on the way to it."""
    body = waves(client, stored_synthetic)
    proposals = client.get(f"/activities/{stored_synthetic}/candidates").json()["candidates"]

    assert body["proposed_count"] == len(proposals)
    assert len(body["verdicts"]) == len(proposals)


def test_no_tier_moved_a_boundary(client, stored_synthetic):
    """L3 owns the intervals. ADR-0016 is why that matters, and this is it from outside."""
    body = waves(client, stored_synthetic)
    proposals = client.get(f"/activities/{stored_synthetic}/candidates").json()["candidates"]

    assert [(v["t_start"], v["t_end"]) for v in body["verdicts"]] == [
        (c["t_start"], c["t_end"]) for c in proposals
    ]


def test_every_verdict_says_who_decided_it_and_why(client, stored_synthetic):
    """A count nobody can argue with is a count nobody can check."""
    for verdict in waves(client, stored_synthetic)["verdicts"]:
        assert verdict["decided_by"] in {t.value for t in DecidedBy}
        assert verdict["reason"], "a verdict with no reason is not inspectable"


def test_an_unresolved_candidate_is_not_counted(client, stored_synthetic):
    """An unsure rule with nobody to ask is not a yes."""
    body = waves(client, stored_synthetic)

    for verdict in body["verdicts"]:
        if verdict["decided_by"] == DecidedBy.UNRESOLVED.value:
            assert verdict["is_wave"] is False
    assert body["wave_count"] == sum(1 for v in body["verdicts"] if v["is_wave"])


def test_no_model_stands_behind_the_count(client, stored_synthetic):
    """ADR-0017: the local model did not clear its bar, so nothing is named here.

    If this ever fails, a model has been wired in -- which is allowed, but only with a
    measurement and a rewritten ADR behind it.
    """
    body = waves(client, stored_synthetic)

    assert body["model"] == ""
    assert body["adjudicated"] == 0


def test_coverage_survives_onto_every_verdict(client, stored_synthetic):
    """The UI has to draw a wave the watch never saw differently from one it watched."""
    for verdict in waves(client, stored_synthetic)["verdicts"]:
        assert 0.0 <= verdict["position_coverage"] <= 1.0


def test_asking_twice_gives_the_same_answer(client, stored_synthetic):
    """Served from the stage cache the second time, and cached means identical."""
    assert waves(client, stored_synthetic) == waves(client, stored_synthetic)


def test_an_unknown_activity_is_a_404(client):
    assert client.get("/activities/nope/waves").status_code == 404
