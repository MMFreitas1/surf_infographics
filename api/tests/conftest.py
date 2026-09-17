"""Shared fixtures. All tests run offline; nothing here touches the network."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from surf.config import Settings
from surf.geo import M_PER_DEG_LAT
from surf.ingest.stage import IngestStage
from surf.llm.lifecycle import ModelBackend
from surf.main import create_app
from surf.pipeline import stage_key
from surf.synthetic import make_synthetic_session

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "sample_data"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at an isolated temp data directory."""
    return Settings(SURF_DATA_DIR=tmp_path / "data")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """TestClient with hermetic settings and lifespan run."""
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def stored_synthetic(client: TestClient) -> str:
    """The seeded synthetic session, stored through the app's own repository.

    The REST fixtures elsewhere are two samples long, which is enough to test ingest and
    far too short to test a track: a smoother, a bearing and a candidate rule all need a
    session with shape. This puts the generated session into the running app the same way
    an ingest would -- payload through the cache, key recorded on the row -- so the track
    endpoints run the real chain over something that looks like surfing.
    """
    session = make_synthetic_session()
    app = client.app
    stage = IngestStage()
    digest = "5" * 64
    key = stage_key(stage, app.state.cache, digest)
    app.state.cache.put(stage.meta.name, key, stage.encode(session.activity))
    app.state.activities.save(
        session.activity, source_sha256=digest, samples_key=key, ingested_at=0.0
    )
    return session.activity.activity_id


@pytest.fixture
def stored_dirty(client: TestClient) -> str:
    """The synthetic session with one physically impossible fix injected, stored as above.

    ``stored_synthetic`` is clean -- the generator produces no artefacts -- so it can never
    show what the cleaner does at the API boundary. This one can: one fix is moved 25 m in a
    second, which is the artefact class that made Phase 5 necessary.

    25 m rather than something spectacular, and between two fixes a second either side, so
    that the damage is exactly one second. A larger displacement is rejected too, but the
    fixes after it are then measured against a fix a long way back and fall until enough
    time passes to explain the distance -- true to life, and useless for a test that wants
    to say "one rejection" and mean it.
    """
    session = make_synthetic_session()
    samples = list(session.activity.samples)
    victim = next(
        i
        for i, s in enumerate(samples)
        if i > 20 and s.has_position and samples[i - 1].has_position and samples[i + 1].has_position
    )
    samples[victim] = samples[victim].model_copy(
        update={"lat": (samples[victim].lat or 0.0) + 25.0 / M_PER_DEG_LAT}
    )
    activity = session.activity.model_copy(
        update={"activity_id": "synthetic-dirty", "samples": samples}
    )

    app = client.app
    stage = IngestStage()
    digest = "6" * 64
    key = stage_key(stage, app.state.cache, digest)
    app.state.cache.put(stage.meta.name, key, stage.encode(activity))
    app.state.activities.save(activity, source_sha256=digest, samples_key=key, ingested_at=0.0)
    return activity.activity_id


@pytest.fixture
def sample_fit() -> Path:
    """Reference FIT session. Skips the test when the file is not present."""
    path = SAMPLE_DIR / "24151923839_ACTIVITY.fit"
    if not path.is_file():
        pytest.skip("reference FIT not available")
    return path


@pytest.fixture
def sample_gpx() -> Path:
    """Reference GPX session (degraded fidelity). Skips when absent."""
    path = SAMPLE_DIR / "activity_24151923839.gpx"
    if not path.is_file():
        pytest.skip("reference GPX not available")
    return path


class FakeClock:
    """Manually advanced clock, so idle-TTL behaviour is tested without sleeping."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move time forward."""
        self.now += seconds


class FakeBackend(ModelBackend):
    """In-memory stand-in for Ollama. Records every load/unload."""

    def __init__(self) -> None:
        self.resident: set[str] = set()
        self.loads = 0
        self.unloads = 0

    def load(self, model: str) -> None:
        self.resident.add(model)
        self.loads += 1

    def unload(self, model: str) -> None:
        self.resident.discard(model)
        self.unloads += 1

    def is_loaded(self, model: str) -> bool:
        return model in self.resident


@pytest.fixture
def fake_clock() -> FakeClock:
    """A clock the test drives by hand."""
    return FakeClock()


@pytest.fixture
def fake_backend() -> FakeBackend:
    """A model backend that never touches real memory."""
    return FakeBackend()
