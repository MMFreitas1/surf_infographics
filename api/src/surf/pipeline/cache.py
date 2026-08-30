"""Content-addressed cache for pipeline stage outputs.

A stage's output is keyed by ``sha256(input_hash, params, code_version)``. Change a
threshold and the key changes; change nothing and the result is reused. This is what
makes re-analysis instant and any published number exactly reproducible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def content_hash(*parts: Any) -> str:
    """Stable hash over arbitrary JSON-serialisable parts.

    Mappings are serialised with sorted keys so that ordering never affects the key.
    """
    h = hashlib.sha256()
    for part in parts:
        payload = json.dumps(part, sort_keys=True, default=str, separators=(",", ":"))
        h.update(payload.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class StageCache:
    """Filesystem cache mapping stage keys to opaque byte payloads."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def key(self, *, input_hash: str, params: Mapping[str, Any], code_version: str) -> str:
        """Compute the cache key for one stage invocation."""
        return content_hash(input_hash, dict(params), code_version)

    def path_for(self, stage: str, key: str) -> Path:
        """Location on disk for a given stage and key."""
        return self.root / stage / f"{key}.bin"

    def get(self, stage: str, key: str) -> bytes | None:
        """Return the cached payload, or None on a miss."""
        path = self.path_for(stage, key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def put(self, stage: str, key: str, payload: bytes) -> Path:
        """Store a payload and return where it landed."""
        path = self.path_for(stage, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        tmp.replace(path)
        return path
