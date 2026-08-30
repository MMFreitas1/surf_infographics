"""The label repository, below the REST surface.

What is tested here is what the endpoints cannot see: that the table only ever grows, that
two sessions' truth never mixes, and that a pass is a recorded fact rather than something
inferred from a row count.
"""

import pytest

from surf.ingest.stage import IngestStage
from surf.models import LabelSource, PassKind, WaveLabel
from surf.pipeline import StageCache, stage_key
from surf.store import ActivityRepository, LabelRepository, StoreError
from test_store import make_activity


@pytest.fixture
def cache(tmp_path):
    return StageCache(tmp_path / "cache")


@pytest.fixture
def activities(tmp_path, cache):
    repo = ActivityRepository(tmp_path / "surf.db", cache)
    yield repo
    repo.close()


@pytest.fixture
def labels(tmp_path, activities):
    """A label repository over the same file the activities live in."""
    repo = LabelRepository(tmp_path / "surf.db")
    yield repo
    repo.close()


@pytest.fixture
def activity_id(activities, cache):
    activity = make_activity("a1")
    stage = IngestStage()
    key = stage_key(stage, cache, "d" * 64)
    cache.put(stage.meta.name, key, stage.encode(activity))
    activities.save(activity, source_sha256="d" * 64, samples_key=key, ingested_at=1.0)
    return activity.activity_id


def wave(t_start=10.0, t_end=17.0, **overrides: object):
    return WaveLabel(t_start=t_start, t_end=t_end, is_wave=True, verified=True, **overrides)


def test_appending_returns_the_row_as_stored(labels, activity_id):
    stored = labels.append(activity_id, wave(), created_at=5.0)
    assert stored.activity_id == activity_id
    assert stored.created_at == 5.0
    assert stored.label_id
    assert labels.for_activity(activity_id) == [stored]


def test_every_label_gets_its_own_identity(labels, activity_id):
    first = labels.append(activity_id, wave(), created_at=1.0)
    second = labels.append(activity_id, wave(), created_at=2.0)
    assert first.label_id != second.label_id


def test_labels_come_back_oldest_first(labels, activity_id):
    late = labels.append(activity_id, wave(t_start=90.0, t_end=96.0), created_at=9.0)
    early = labels.append(activity_id, wave(), created_at=1.0)
    assert [row.label_id for row in labels.for_activity(activity_id)] == [
        early.label_id,
        late.label_id,
    ]


def test_a_correction_never_touches_the_row_it_replaces(labels, activity_id):
    original = labels.append(activity_id, wave(), created_at=1.0)
    labels.append(
        activity_id, wave(t_start=11.0, t_end=19.0), created_at=2.0, supersedes=original.label_id
    )
    kept = next(r for r in labels.for_activity(activity_id) if r.label_id == original.label_id)
    assert kept == original


def test_two_sessions_do_not_share_truth(labels, activities, cache, activity_id):
    other = make_activity("a2")
    stage = IngestStage()
    key = stage_key(stage, cache, "e" * 64)
    cache.put(stage.meta.name, key, stage.encode(other))
    activities.save(other, source_sha256="e" * 64, samples_key=key, ingested_at=1.0)

    labels.append(activity_id, wave(), created_at=1.0)
    labels.append("a2", wave(), created_at=1.0)

    assert len(labels.for_activity(activity_id)) == 1
    assert len(labels.for_activity("a2")) == 1


def test_labelling_a_session_that_is_not_stored_is_refused(labels):
    with pytest.raises(StoreError, match="not stored"):
        labels.append("ghost", wave(), created_at=1.0)


def test_a_pass_over_a_session_that_is_not_stored_is_refused(labels):
    with pytest.raises(StoreError, match="not stored"):
        labels.complete_pass("ghost", PassKind.BLIND, completed_at=1.0)


def test_counting_is_by_provenance(labels, activity_id):
    labels.append(activity_id, wave(), created_at=1.0)
    labels.append(activity_id, wave(), created_at=2.0)
    labels.complete_pass(activity_id, PassKind.BLIND, completed_at=3.0)
    labels.append(activity_id, wave(source=LabelSource.HUMAN_ASSISTED), created_at=4.0)

    assert labels.count_by_source(activity_id, LabelSource.HUMAN) == 2
    assert labels.count_by_source(activity_id, LabelSource.HUMAN_ASSISTED) == 1


def test_a_superseded_label_still_counts_toward_the_pass_that_produced_it(labels, activity_id):
    """The pass records what the sweep did, and a correction is part of what it did."""
    first = labels.append(activity_id, wave(), created_at=1.0)
    labels.append(activity_id, wave(), created_at=2.0, supersedes=first.label_id)
    completed = labels.complete_pass(activity_id, PassKind.BLIND, completed_at=3.0)
    assert completed.label_count == 2
    assert len(labels.for_activity(activity_id, current=True)) == 1


def test_sweeping_a_session_again_appends_another_pass(labels, activity_id):
    labels.complete_pass(activity_id, PassKind.BLIND, completed_at=1.0)
    labels.complete_pass(activity_id, PassKind.BLIND, completed_at=2.0)
    assert [p.completed_at for p in labels.passes_for(activity_id)] == [1.0, 2.0]


def test_has_pass_is_per_kind(labels, activity_id):
    assert labels.has_pass(activity_id, PassKind.BLIND) is False
    labels.complete_pass(activity_id, PassKind.BLIND, completed_at=1.0)
    assert labels.has_pass(activity_id, PassKind.BLIND) is True
    assert labels.has_pass(activity_id, PassKind.ASSISTED) is False


def test_the_repository_offers_no_way_to_change_or_remove_a_label(labels):
    """ADR-0006 as an API surface, not only as a promise in a document."""
    public = {name for name in dir(labels) if not name.startswith("_")}
    assert not {"update", "edit", "delete", "remove", "clear"} & public
