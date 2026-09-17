"""One SQLite connection, several threads: does the store hand back honest rows.

FastAPI runs sync endpoints on a threadpool and each repository holds a single connection,
so concurrent reads are not a hypothetical here -- opening `/label/{id}` fires four requests
at once, which is how this surfaced.

Two threads running statements on one connection do not merely race for a row, they corrupt
each other's results. Before these reads were serialised, eight threads reading this
repository produced 17 failures in 960 reads in four flavours: a clean `InterfaceError`, a
blind window whose `cause` came back NULL, a summary whose counts came back NULL, and a
`samples_key` read from the wrong row -- which surfaces as "samples are missing from the
stage cache", a report of data loss that has not happened.

Not SQLite's fault, and worth knowing before anyone decides this lock is redundant: the
library is in serialized mode here. The damage comes from CPython's per-connection cache of
prepared statements, which hands two threads running the same SQL the same statement object
to overwrite. `ActivityRepository`'s docstring has the measurements.

Three of those four are silently wrong data rather than an error, which is the reason these
tests assert on the *content* of what comes back and not merely that nothing raised.
"""

import threading

import pytest

from surf.ingest.stage import IngestStage
from surf.models import LabelSource, PassKind, WaveLabel
from surf.pipeline import StageCache, stage_key
from surf.store import ActivityRepository, LabelRepository
from surf.synthetic import make_synthetic_session

THREADS = 8
ROUNDS = 40
"""Enough to trip the race reliably: it reproduced at 17 failures in 960 reads."""


def run_concurrently(work):
    """Run ``work`` on several threads, returning everything it raised.

    Exceptions are collected rather than allowed to escape, because a thread that dies in
    the background would otherwise leave the test passing on a silent failure.
    """
    failures: list[str] = []
    lock = threading.Lock()

    def loop():
        for _ in range(ROUNDS):
            try:
                work()
            except Exception as exc:  # catching anything at all is the point here
                with lock:
                    failures.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=loop) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return failures


@pytest.fixture
def stored(tmp_path):
    """A synthetic session in a real repository, with its payload in a real cache."""
    cache = StageCache(tmp_path / "cache")
    repo = ActivityRepository(tmp_path / "surf.db", cache)
    session = make_synthetic_session()

    stage = IngestStage()
    digest = "9" * 64
    key = stage_key(stage, cache, digest)
    cache.put(stage.meta.name, key, stage.encode(session.activity))
    repo.save(session.activity, source_sha256=digest, samples_key=key, ingested_at=0.0)

    yield repo, session.activity, key
    repo.close()


def test_concurrent_reads_do_not_fail(stored):
    """The clean half of the failure: `InterfaceError`, and a `StoreError` claiming the
    samples are missing when they are sitting in the cache."""
    repo, activity, _ = stored

    def read():
        repo.get(activity.activity_id)
        repo.samples_key(activity.activity_id)
        repo.summaries(10)

    assert run_concurrently(read) == []


def test_concurrent_reads_do_not_return_corrupted_rows(stored):
    """The half that would not have raised at all.

    Every field checked here came back NULL or belonging to another row while the reads
    were unserialised, so a test that only asserted "nothing raised" would have passed
    against the bug.
    """
    repo, activity, samples_key = stored
    expected_windows = len(activity.blind_windows)
    mismatches: list[str] = []
    lock = threading.Lock()

    def read():
        stored_activity = repo.get(activity.activity_id)
        summary = next(s for s in repo.summaries(10) if s.activity_id == activity.activity_id)
        problems = []
        if stored_activity is None:
            problems.append("get returned None for a stored activity")
        else:
            if len(stored_activity.blind_windows) != expected_windows:
                problems.append(f"windows {len(stored_activity.blind_windows)}")
            if len(stored_activity.samples) != len(activity.samples):
                problems.append(f"samples {len(stored_activity.samples)}")
            if stored_activity.sport != activity.sport:
                problems.append(f"sport {stored_activity.sport!r}")
        if summary.sample_count != len(activity.samples):
            problems.append(f"summary count {summary.sample_count}")
        if repo.samples_key(activity.activity_id) != samples_key:
            problems.append("samples_key came from another row")
        if problems:
            with lock:
                mismatches.extend(problems)

    failures = run_concurrently(read)
    assert failures == []
    assert mismatches == []


def test_a_writer_and_readers_together_keep_the_store_consistent(stored):
    """Re-ingesting a session while the UI reads it. `save` replaces the activity row and
    rewrites its blind windows, so a reader that caught it mid-write would see one
    session's metadata beside another's windows."""
    repo, activity, samples_key = stored
    mismatches: list[str] = []
    lock = threading.Lock()
    stop = threading.Event()

    def rewrite():
        while not stop.is_set():
            repo.save(activity, source_sha256="9" * 64, samples_key=samples_key, ingested_at=1.0)

    def read():
        stored_activity = repo.get(activity.activity_id)
        if stored_activity is not None and len(stored_activity.blind_windows) != len(
            activity.blind_windows
        ):
            with lock:
                mismatches.append(f"windows {len(stored_activity.blind_windows)}")

    writer = threading.Thread(target=rewrite, daemon=True)
    writer.start()
    try:
        failures = run_concurrently(read)
    finally:
        stop.set()
        writer.join(timeout=5)

    assert failures == []
    assert mismatches == []


def test_the_label_screens_four_concurrent_reads_are_safe(tmp_path):
    """The exact shape that surfaced this: `/label/{id}` fetches the activity, its track,
    its labels and its passes at once, so both repositories are read from several threads
    at the same moment."""
    cache = StageCache(tmp_path / "cache")
    activities = ActivityRepository(tmp_path / "surf.db", cache)
    labels = LabelRepository(tmp_path / "surf.db")
    session = make_synthetic_session()

    stage = IngestStage()
    digest = "8" * 64
    key = stage_key(stage, cache, digest)
    cache.put(stage.meta.name, key, stage.encode(session.activity))
    activities.save(session.activity, source_sha256=digest, samples_key=key, ingested_at=0.0)

    activity_id = session.activity.activity_id
    labels.append(
        activity_id,
        WaveLabel(t_start=10.0, t_end=18.0, is_wave=True, verified=True),
        created_at=1.0,
    )
    labels.complete_pass(activity_id, PassKind.BLIND, completed_at=2.0)

    def load_the_page():
        activities.get(activity_id)
        activities.samples_key(activity_id)
        assert len(labels.for_activity(activity_id)) == 1
        assert len(labels.passes_for(activity_id)) == 1
        assert labels.has_pass(activity_id, PassKind.BLIND) is True
        assert labels.count_by_source(activity_id, LabelSource.HUMAN) == 1

    try:
        assert run_concurrently(load_the_page) == []
    finally:
        activities.close()
        labels.close()
