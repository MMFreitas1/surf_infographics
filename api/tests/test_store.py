"""Persistence: SQLite metadata plus Parquet samples.

The load-bearing assertion here is that an absent measurement survives storage as ``None``.
Parquet has a null, and we use it: writing 0.0 for a sample with no fix would turn "we could
not see" into "the surfer was at the equator, stationary", and every coverage number
downstream would quietly become a lie.
"""

import pytest

from surf.models import Activity, BlindCause, BlindWindow, Fidelity, Sample
from surf.pipeline import StageCache
from surf.store import (
    SCHEMA_VERSION,
    ActivityRepository,
    StoreError,
    samples_from_parquet,
    samples_to_parquet,
)


@pytest.fixture
def repo(tmp_path):
    store = ActivityRepository(tmp_path / "surf.db", StageCache(tmp_path / "cache"))
    yield store
    store.close()


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


def test_absent_measurements_round_trip_as_none_not_zero():
    """The invariant this whole module exists to protect."""
    samples = [Sample(t=0.0, lat=10.0, lon=20.0, speed_ms=0.0), Sample(t=1.0)]
    restored = samples_from_parquet(samples_to_parquet(samples))

    assert restored[0].speed_ms == 0.0  # a real, measured zero survives as zero
    assert restored[1].lat is None
    assert restored[1].lon is None
    assert restored[1].speed_ms is None  # and an absence survives as an absence
    assert restored[1].hr_bpm is None
    assert restored[1].has_position is False


def test_parquet_round_trip_is_exact():
    samples = make_activity().samples
    assert [s.model_dump() for s in samples_from_parquet(samples_to_parquet(samples))] == [
        s.model_dump() for s in samples
    ]


def test_save_and_get_returns_an_identical_activity(repo):
    activity = make_activity()
    repo.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    assert repo.get(activity.activity_id).model_dump() == activity.model_dump()


def test_blind_windows_survive_with_their_causes(repo):
    activity = make_activity(
        windows=[
            BlindWindow(t_start=1.0, t_end=2.0, cause=BlindCause.NO_FIX),
            BlindWindow(t_start=5.0, t_end=9.0, cause=BlindCause.MISSING_RECORD),
        ]
    )
    repo.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    stored = repo.get(activity.activity_id)
    assert [w.cause for w in stored.blind_windows] == [
        BlindCause.NO_FIX,
        BlindCause.MISSING_RECORD,
    ]
    assert stored.blind_seconds == 5.0


def test_unknown_activity_is_none_not_an_error(repo):
    assert repo.get("nope") is None


def test_the_same_bytes_resolve_to_the_activity_already_stored(repo):
    activity = make_activity()
    repo.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    assert repo.id_for_digest("d" * 64) == activity.activity_id
    assert repo.id_for_digest("e" * 64) is None


def test_resaving_replaces_rather_than_duplicating(repo):
    activity = make_activity()
    repo.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    repo.save(activity, source_sha256="d" * 64, ingested_at=2.0)
    assert len(repo.summaries()) == 1
    assert len(repo.get(activity.activity_id).blind_windows) == 1


def test_an_activity_survives_a_restart(tmp_path):
    """Reopening the same files must find the session, or persistence means nothing."""
    activity = make_activity()
    first = ActivityRepository(tmp_path / "surf.db", StageCache(tmp_path / "cache"))
    first.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    first.close()

    second = ActivityRepository(tmp_path / "surf.db", StageCache(tmp_path / "cache"))
    try:
        assert second.get(activity.activity_id).model_dump() == activity.model_dump()
    finally:
        second.close()


def test_deleting_an_activity_takes_its_windows_with_it(repo):
    activity = make_activity()
    repo.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    assert repo.delete(activity.activity_id) is True
    assert repo.get(activity.activity_id) is None
    assert repo.delete(activity.activity_id) is False
    orphans = repo._db.execute("SELECT COUNT(*) FROM blind_windows").fetchone()[0]
    assert orphans == 0


def test_metadata_without_its_samples_raises_rather_than_reporting_an_empty_session(repo, tmp_path):
    activity = make_activity()
    repo.save(activity, source_sha256="d" * 64, ingested_at=1.0)
    for cached in (tmp_path / "cache").rglob("*.bin"):
        cached.unlink()
    with pytest.raises(StoreError, match="missing from the stage cache"):
        repo.get(activity.activity_id)


def test_summaries_carry_coverage_without_reading_any_samples(repo):
    repo.save(make_activity("a1"), source_sha256="d" * 64, ingested_at=1.0)
    summary = repo.summaries()[0]
    assert summary.sample_count == 3
    assert summary.position_coverage == pytest.approx(2 / 3)
    assert summary.blind_seconds == 1.0
    assert summary.ingested_at == 1.0
    assert not hasattr(summary, "samples")


def test_summaries_are_newest_session_first(repo):
    older = make_activity("old")
    newer = make_activity("new", samples=[Sample(t=500.0, lat=10.0, lon=20.0)], windows=[])
    newer = newer.model_copy(update={"start_time": 500.0})
    repo.save(older, source_sha256="a" * 64, ingested_at=1.0)
    repo.save(newer, source_sha256="b" * 64, ingested_at=2.0)
    assert [s.activity_id for s in repo.summaries()] == ["new", "old"]


def test_an_activity_with_no_samples_reports_zero_coverage_not_a_crash(repo):
    empty = make_activity("empty", samples=[], windows=[])
    repo.save(empty, source_sha256="c" * 64, ingested_at=1.0)
    assert repo.get("empty").samples == []
    assert repo.summaries()[0].position_coverage == 0.0
