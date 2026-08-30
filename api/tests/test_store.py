"""Persistence: SQLite metadata, indexing a payload the pipeline wrote.

The store no longer serialises samples on the caller's behalf -- that belongs to the L0
stage (see `test_pipeline_spine.py`). What is tested here is the other half: that a row
and its cached payload come back as the session that went in, that blind windows survive
as first-class rows, and that a missing payload is an error rather than a session
reported as empty.
"""

import pytest

from surf.ingest.stage import IngestStage
from surf.models import Activity, BlindCause, BlindWindow, Fidelity, Sample
from surf.pipeline import StageCache, stage_key
from surf.store import SCHEMA_VERSION, ActivityRepository, StoreError


@pytest.fixture
def cache(tmp_path):
    return StageCache(tmp_path / "cache")


@pytest.fixture
def repo(tmp_path, cache):
    store = ActivityRepository(tmp_path / "surf.db", cache)
    yield store
    store.close()


def store(repo, cache, activity, *, digest="d" * 64, ingested_at=1.0):
    """Persist an activity the way the ingest path does.

    The pipeline writes the L0 payload; the repository records the key it landed under.
    Both halves have to happen, which is exactly the point of splitting them.
    """
    stage = IngestStage()
    key = stage_key(stage, cache, digest)
    cache.put(stage.meta.name, key, stage.encode(activity))
    return repo.save(activity, source_sha256=digest, samples_key=key, ingested_at=ingested_at)


def make_activity(activity_id="a1", samples=None, windows=None):
    """A small but complete activity: some fixes, some not."""
    if samples is None:
        samples = [
            Sample(t=0.0, lat=10.0, lon=20.0, speed_ms=1.5, hr_bpm=100, distance_m=0.0),
            Sample(t=1.0, hr_bpm=101),  # no fix, no speed, no distance
            Sample(t=2.0, lat=10.001, lon=20.001, speed_ms=2.0, hr_bpm=102, distance_m=3.0),
        ]
    if windows is None:
        windows = [BlindWindow(t_start=1.0, t_end=2.0, cause=BlindCause.NO_FIX)]
    return Activity(
        activity_id=activity_id,
        sport="surfing",
        start_time=0.0,
        fidelity=Fidelity.FIT,
        samples=samples,
        blind_windows=windows,
        device="garmin:3291",
        source_file="x.fit",
    )


def test_schema_version_is_stamped(repo):
    assert repo.schema_version == SCHEMA_VERSION


def test_save_and_get_returns_an_identical_activity(repo, cache):
    activity = make_activity()
    store(repo, cache, activity)
    assert repo.get(activity.activity_id).model_dump() == activity.model_dump()


def test_blind_windows_survive_with_their_causes(repo, cache):
    activity = make_activity(
        windows=[
            BlindWindow(t_start=1.0, t_end=2.0, cause=BlindCause.NO_FIX),
            BlindWindow(t_start=5.0, t_end=9.0, cause=BlindCause.MISSING_RECORD),
        ]
    )
    store(repo, cache, activity)
    stored = repo.get(activity.activity_id)
    assert [w.cause for w in stored.blind_windows] == [
        BlindCause.NO_FIX,
        BlindCause.MISSING_RECORD,
    ]
    assert stored.blind_seconds == 5.0


def test_the_l0_key_is_readable_so_a_later_stage_can_chain_onto_it(repo, cache):
    """L1 keys its track on this, so a track cannot outlive the samples behind it."""
    activity = make_activity()
    store(repo, cache, activity)
    key = repo.samples_key(activity.activity_id)
    assert key == stage_key(IngestStage(), cache, "d" * 64)
    assert cache.get(IngestStage().meta.name, key) is not None
    assert repo.samples_key("nope") is None


def test_unknown_activity_is_none_not_an_error(repo):
    assert repo.get("nope") is None


def test_the_same_bytes_resolve_to_the_activity_already_stored(repo, cache):
    activity = make_activity()
    store(repo, cache, activity)
    assert repo.id_for_digest("d" * 64) == activity.activity_id
    assert repo.id_for_digest("e" * 64) is None


def test_resaving_replaces_rather_than_duplicating(repo, cache):
    activity = make_activity()
    store(repo, cache, activity, ingested_at=1.0)
    store(repo, cache, activity, ingested_at=2.0)
    assert len(repo.summaries()) == 1
    assert len(repo.get(activity.activity_id).blind_windows) == 1


def test_an_activity_survives_a_restart(tmp_path):
    """Reopening the same files must find the session, or persistence means nothing."""
    activity = make_activity()
    cache = StageCache(tmp_path / "cache")
    first = ActivityRepository(tmp_path / "surf.db", cache)
    store(first, cache, activity)
    first.close()

    second = ActivityRepository(tmp_path / "surf.db", StageCache(tmp_path / "cache"))
    try:
        assert second.get(activity.activity_id).model_dump() == activity.model_dump()
    finally:
        second.close()


def test_deleting_an_activity_takes_its_windows_with_it(repo, cache):
    activity = make_activity()
    store(repo, cache, activity)
    assert repo.delete(activity.activity_id) is True
    assert repo.get(activity.activity_id) is None
    assert repo.delete(activity.activity_id) is False
    orphans = repo._db.execute("SELECT COUNT(*) FROM blind_windows").fetchone()[0]
    assert orphans == 0


def test_metadata_without_its_samples_raises_rather_than_reporting_an_empty_session(
    repo, cache, tmp_path
):
    activity = make_activity()
    store(repo, cache, activity)
    for cached in (tmp_path / "cache").rglob("*.bin"):
        cached.unlink()
    with pytest.raises(StoreError, match="missing from the stage cache"):
        repo.get(activity.activity_id)


def test_summaries_carry_coverage_without_reading_any_samples(repo, cache):
    store(repo, cache, make_activity("a1"))
    summary = repo.summaries()[0]
    assert summary.sample_count == 3
    assert summary.position_coverage == pytest.approx(2 / 3)
    assert summary.blind_seconds == 1.0
    assert summary.ingested_at == 1.0
    assert not hasattr(summary, "samples")


def test_summaries_are_newest_session_first(repo, cache):
    older = make_activity("old")
    newer = make_activity("new", samples=[Sample(t=500.0, lat=10.0, lon=20.0)], windows=[])
    newer = newer.model_copy(update={"start_time": 500.0})
    store(repo, cache, older, digest="a" * 64, ingested_at=1.0)
    store(repo, cache, newer, digest="b" * 64, ingested_at=2.0)
    assert [s.activity_id for s in repo.summaries()] == ["new", "old"]


def test_an_activity_with_no_samples_reports_zero_coverage_not_a_crash(repo, cache):
    empty = make_activity("empty", samples=[], windows=[])
    store(repo, cache, empty, digest="c" * 64)
    assert repo.get("empty").samples == []
    assert repo.summaries()[0].position_coverage == 0.0
