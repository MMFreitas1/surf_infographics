"""Eval fixtures. Offline, deterministic, and free of any third-party derived data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from surf.synthetic import SyntheticSession, make_synthetic_session

GOLDEN_DIR = Path(__file__).parent / "goldens"


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers this suite uses.

    `api/pyproject.toml` declares them too, but the eval gate runs with this directory as
    its root, so pytest never reads that file and would warn on every run. A warning nobody
    can act on is how real ones get ignored.
    """
    config.addinivalue_line(
        "markers", "llm: requires a running local LLM (skipped unless SURF_LLM_EVAL=1)"
    )


@pytest.fixture(scope="session")
def synthetic_golden() -> dict[str, Any]:
    """The committed expectations for the reference synthetic session."""
    return json.loads((GOLDEN_DIR / "synthetic_session_v1.json").read_text())


@pytest.fixture(scope="session")
def synthetic() -> SyntheticSession:
    """A freshly generated session, which must match the golden exactly."""
    return make_synthetic_session()
