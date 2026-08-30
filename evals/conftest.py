"""Eval fixtures. Offline, deterministic, and free of any third-party derived data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from surf.synthetic import SyntheticSession, make_synthetic_session

GOLDEN_DIR = Path(__file__).parent / "goldens"


@pytest.fixture(scope="session")
def synthetic_golden() -> dict[str, Any]:
    """The committed expectations for the reference synthetic session."""
    return json.loads((GOLDEN_DIR / "synthetic_session_v1.json").read_text())


@pytest.fixture(scope="session")
def synthetic() -> SyntheticSession:
    """A freshly generated session, which must match the golden exactly."""
    return make_synthetic_session()
