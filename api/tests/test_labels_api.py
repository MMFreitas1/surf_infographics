"""The label endpoints: the only door ground truth comes through.

Two rules are worth more than the rest of this file put together. Nothing here may edit or
remove a label (ADR-0006), and a label made with L3's proposals on screen may never be
mistaken for one made without them (ADR-0012). Both are enforced server-side, because a
rule only the front end knows is a rule the next caller breaks.
"""

from fastapi.testclient import TestClient

from surf.main import create_app

WAVE = {"t_start": 100.0, "t_end": 107.0, "is_wave": True, "verified": True}


def post_label(client, activity_id, **overrides: object):
    return client.post(f"/activities/{activity_id}/labels", json=WAVE | overrides)


def complete_pass(client, activity_id, kind):
    return client.post(f"/activities/{activity_id}/label-passes", json={"kind": kind})


# -- the round trip ----------------------------------------------------------------------


def test_a_label_comes_back_as_it_went_in(client, stored_synthetic):
    created = post_label(client, stored_synthetic)
    assert created.status_code == 201
    body = created.json()
    assert body["t_start"] == 100.0
    assert body["source"] == "human"
    assert body["counts_as_truth"] is True
    assert body["label_id"] and body["created_at"] > 0.0

    listed = client.get(f"/activities/{stored_synthetic}/labels").json()
    assert listed == [body]


def test_labels_survive_a_restart(settings):
    """The store's durability through the endpoint, not just the repository's."""
    with TestClient(create_app(settings)) as first:
        from fit_builder import small_fit

        activity_id = first.post("/activities", content=small_fit()).json()["activity_id"]
        first.post(f"/activities/{activity_id}/labels", json=WAVE)

    with TestClient(create_app(settings)) as second:
        labels = second.get(f"/activities/{activity_id}/labels").json()
    assert len(labels) == 1
    assert labels[0]["t_start"] == 100.0


def test_a_not_a_wave_label_is_stored_as_truth_too(client, stored_synthetic):
    """ "I looked, and this is not a ride" is what makes a false positive measurable."""
    body = post_label(client, stored_synthetic, is_wave=False).json()
    assert body["is_wave"] is False
    assert body["counts_as_truth"] is True


# -- append-only -------------------------------------------------------------------------


def test_a_correction_adds_a_row_and_leaves_the_original_alone(client, stored_synthetic):
    original = post_label(client, stored_synthetic).json()
    corrected = post_label(
        client, stored_synthetic, t_start=101.0, t_end=109.0, supersedes=original["label_id"]
    ).json()

    everything = client.get(f"/activities/{stored_synthetic}/labels").json()
    assert [row["label_id"] for row in everything] == [
        original["label_id"],
        corrected["label_id"],
    ]
    assert everything[0] == original, "the superseded row was modified"

    current = client.get(f"/activities/{stored_synthetic}/labels?current=true").json()
    assert [row["label_id"] for row in current] == [corrected["label_id"]]


def test_a_correction_can_itself_be_corrected(client, stored_synthetic):
    first = post_label(client, stored_synthetic).json()
    second = post_label(client, stored_synthetic, supersedes=first["label_id"]).json()
    third = post_label(client, stored_synthetic, supersedes=second["label_id"]).json()

    assert len(client.get(f"/activities/{stored_synthetic}/labels").json()) == 3
    current = client.get(f"/activities/{stored_synthetic}/labels?current=true").json()
    assert [row["label_id"] for row in current] == [third["label_id"]]


def test_a_label_cannot_supersede_one_from_another_session(client, stored_synthetic):
    from fit_builder import small_fit

    other = client.post("/activities", content=small_fit()).json()["activity_id"]
    stray = client.post(f"/activities/{other}/labels", json=WAVE).json()

    response = post_label(client, stored_synthetic, supersedes=stray["label_id"])
    assert response.status_code == 400
    assert "belongs to activity" in response.json()["detail"]


def test_a_label_cannot_supersede_one_that_does_not_exist(client, stored_synthetic):
    response = post_label(client, stored_synthetic, supersedes="ffff")
    assert response.status_code == 400
    assert "no such label" in response.json()["detail"]


# -- what the API refuses to write -------------------------------------------------------


def test_a_bootstrap_import_cannot_enter_through_the_api(client, stored_synthetic):
    """ADR-0006: the labeling UI is the only writer. Weak imports are not truth."""
    response = post_label(client, stored_synthetic, source="ciq_bootstrap")
    assert response.status_code == 400
    assert "human labels only" in response.json()["detail"]


def test_verified_has_to_be_stated(client, stored_synthetic):
    """Inherited it would default to False, and every label would silently count for nothing."""
    response = client.post(
        f"/activities/{stored_synthetic}/labels",
        json={"t_start": 1.0, "t_end": 2.0, "is_wave": True},
    )
    assert response.status_code == 422


def test_a_label_with_no_duration_is_refused(client, stored_synthetic):
    assert post_label(client, stored_synthetic, t_end=100.0).status_code == 422
    assert post_label(client, stored_synthetic, t_end=99.0).status_code == 422


def test_labelling_an_unknown_activity_is_a_404(client):
    assert client.post("/activities/nope/labels", json=WAVE).status_code == 404
    assert client.get("/activities/nope/labels").status_code == 404
    assert client.post("/activities/nope/label-passes", json={"kind": "blind"}).status_code == 404
    assert client.get("/activities/nope/label-passes").status_code == 404


# -- blind first, then assisted (ADR-0012) -----------------------------------------------


def test_an_assisted_label_is_refused_before_a_blind_pass_exists(client, stored_synthetic):
    response = post_label(client, stored_synthetic, source="human_assisted")
    assert response.status_code == 409
    assert "no blind pass" in response.json()["detail"]


def test_an_assisted_label_is_accepted_once_the_blind_pass_is_recorded(client, stored_synthetic):
    post_label(client, stored_synthetic)
    complete_pass(client, stored_synthetic, "blind")

    response = post_label(
        client, stored_synthetic, source="human_assisted", t_start=200.0, t_end=208.0
    )
    assert response.status_code == 201
    assert response.json()["source"] == "human_assisted"


def test_an_assisted_label_is_honest_judgement_that_still_does_not_count_as_truth(
    client, stored_synthetic
):
    """It is anchored to the detector's proposals, so scoring against it measures agreement."""
    post_label(client, stored_synthetic)
    complete_pass(client, stored_synthetic, "blind")
    body = post_label(client, stored_synthetic, source="human_assisted").json()

    assert body["verified"] is True
    assert body["counts_as_truth"] is False


def test_an_assisted_pass_cannot_run_before_a_blind_one(client, stored_synthetic):
    response = complete_pass(client, stored_synthetic, "assisted")
    assert response.status_code == 409
    assert "ADR-0012" in response.json()["detail"]


def test_a_pass_counts_the_labels_it_produced(client, stored_synthetic):
    post_label(client, stored_synthetic)
    post_label(client, stored_synthetic, t_start=200.0, t_end=206.0)
    body = complete_pass(client, stored_synthetic, "blind").json()
    assert body["label_count"] == 2
    assert body["kind"] == "blind"


def test_a_pass_that_found_nothing_is_still_a_pass(client, stored_synthetic):
    """The whole reason passes are recorded: this is not the same as nobody having looked."""
    body = complete_pass(client, stored_synthetic, "blind").json()
    assert body["label_count"] == 0
    assert client.get(f"/activities/{stored_synthetic}/label-passes").json() == [body]

    # ...and it opens the assisted pass, which a bare label count could never have done.
    assert post_label(client, stored_synthetic, source="human_assisted").status_code == 201


def test_each_pass_counts_only_its_own_labels(client, stored_synthetic):
    post_label(client, stored_synthetic)
    complete_pass(client, stored_synthetic, "blind")
    post_label(client, stored_synthetic, source="human_assisted", t_start=300.0, t_end=307.0)
    assisted = complete_pass(client, stored_synthetic, "assisted").json()

    assert assisted["label_count"] == 1
    kinds = [p["kind"] for p in client.get(f"/activities/{stored_synthetic}/label-passes").json()]
    assert kinds == ["blind", "assisted"]
