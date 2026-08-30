"""The activity endpoints, end to end through the app.

These run against committed fixtures, so they cover the REST surface in CI where the
reference session is absent.
"""

from pathlib import Path

from fit_builder import small_fit

FIXTURES = Path(__file__).parent / "fixtures"
GPX_BYTES = (FIXTURES / "minimal.gpx").read_bytes()
TCX_BYTES = (FIXTURES / "minimal.tcx").read_bytes()


def test_posting_a_file_returns_the_canonical_activity(client):
    response = client.post("/activities?filename=session.fit", content=small_fit())
    assert response.status_code == 201
    body = response.json()
    assert body["fidelity"] == "fit"
    assert body["sport"] == "surfing"
    assert body["source_file"] == "session.fit"
    assert len(body["samples"]) == 2
    assert body["samples"][0]["has_position"] is True
    assert body["samples"][1]["has_position"] is False
    assert body["samples"][1]["lat"] is None
    assert body["blind_windows"]


def test_an_ingested_activity_can_be_read_back(client):
    activity_id = client.post("/activities", content=small_fit()).json()["activity_id"]
    response = client.get(f"/activities/{activity_id}")
    assert response.status_code == 200
    assert response.json()["activity_id"] == activity_id
    assert len(response.json()["samples"]) == 2


def test_posting_the_same_bytes_twice_yields_one_activity(client):
    first = client.post("/activities", content=small_fit())
    second = client.post("/activities", content=small_fit())
    assert first.status_code == 201
    assert second.status_code == 200  # already stored, not created again
    assert first.json()["activity_id"] == second.json()["activity_id"]
    assert len(client.get("/activities").json()) == 1


def test_the_list_endpoint_omits_samples(client):
    client.post("/activities?filename=session.fit", content=small_fit())
    rows = client.get("/activities").json()
    assert len(rows) == 1
    assert "samples" not in rows[0]
    assert rows[0]["sample_count"] == 2
    assert rows[0]["position_coverage"] == 0.5
    assert rows[0]["source_file"] == "session.fit"


def test_gpx_and_tcx_ingest_and_are_labelled_degraded(client):
    gpx = client.post("/activities?filename=s.gpx", content=GPX_BYTES)
    tcx = client.post("/activities?filename=s.tcx", content=TCX_BYTES)
    assert gpx.json()["fidelity"] == "gpx"
    assert tcx.json()["fidelity"] == "tcx"
    assert {row["fidelity"] for row in client.get("/activities").json()} == {"gpx", "tcx"}


def test_the_format_is_read_from_content_not_from_the_filename(client):
    """A GPX uploaded as .fit is still a GPX, and is still labelled degraded."""
    response = client.post("/activities?filename=lying.fit", content=GPX_BYTES)
    assert response.json()["fidelity"] == "gpx"


def test_an_unknown_activity_is_a_404(client):
    assert client.get("/activities/does-not-exist").status_code == 404


def test_an_empty_body_is_rejected(client):
    response = client.post("/activities", content=b"")
    assert response.status_code == 400
    assert "empty body" in response.json()["detail"]


def test_bytes_that_are_not_an_activity_file_are_rejected(client):
    response = client.post("/activities", content=b"this is not an activity")
    assert response.status_code == 400
    assert "FIT, GPX or TCX" in response.json()["detail"]


def test_a_corrupt_fit_is_rejected_at_ingest(client):
    """A bad CRC must fail here, not surface as nonsense in Phase 2."""
    corrupt = bytearray(small_fit())
    corrupt[-1] ^= 0xFF
    response = client.post("/activities", content=bytes(corrupt))
    assert response.status_code == 400
    assert "CRC" in response.json()["detail"]


def test_a_file_over_the_limit_is_refused(client, settings):
    oversized = b"\x00" * (settings.max_upload_bytes + 1)
    assert client.post("/activities", content=oversized).status_code == 413


def test_ingested_activities_survive_a_new_client_on_the_same_data_dir(settings):
    """The endpoint's durability, not just the repository's."""
    from fastapi.testclient import TestClient

    from surf.main import create_app

    with TestClient(create_app(settings)) as first:
        activity_id = first.post("/activities", content=small_fit()).json()["activity_id"]
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/activities/{activity_id}").status_code == 200
