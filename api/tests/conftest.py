"""Shared fixtures. All tests run offline; nothing here touches the network."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from surf.config import Settings
from surf.llm.lifecycle import ModelBackend
from surf.main import create_app

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
