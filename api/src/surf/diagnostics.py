"""Local error capture.

This project has no SaaS error tracking (ADR-0007). It is a single-user localhost app,
so errors are kept where both the developer and an assisting agent can actually read
them: an in-memory ring buffer exposed over HTTP, plus an append-only JSONL log on disk.

The buffer is bounded so a crash loop cannot exhaust memory.
"""

from __future__ import annotations

import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class CapturedError:
    """One captured exception, in a shape that survives JSON."""

    timestamp: str
    kind: str
    message: str
    traceback: str
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form, for the diagnostics endpoint."""
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "message": self.message,
            "traceback": self.traceback,
            "context": self.context,
        }


class ErrorBuffer:
    """Bounded, newest-last ring buffer of recent errors."""

    def __init__(self, capacity: int = 200) -> None:
        if capacity <= 0:
            msg = "capacity must be positive"
            raise ValueError(msg)
        self._items: deque[CapturedError] = deque(maxlen=capacity)
        self._total = 0

    @property
    def capacity(self) -> int:
        """Maximum retained errors."""
        return self._items.maxlen or 0

    @property
    def total_seen(self) -> int:
        """Errors captured since start, including ones evicted from the buffer."""
        return self._total

    def capture(self, exc: BaseException, **context: Any) -> CapturedError:
        """Record a Python exception and return what was stored."""
        return self.record(
            kind=type(exc).__name__,
            message=str(exc),
            traceback_text="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).rstrip(),
            **context,
        )

    def record(
        self,
        kind: str,
        message: str,
        traceback_text: str = "",
        **context: Any,
    ) -> CapturedError:
        """Record an error that did not originate as a Python exception.

        Browser errors arrive already formatted, with their own type and stack. Wrapping
        them in a synthetic Python exception would mislabel them -- a TypeError in the UI
        must not be reported as a RuntimeError here.
        """
        captured = CapturedError(
            timestamp=datetime.now(UTC).isoformat(),
            kind=kind,
            message=message,
            traceback=traceback_text,
            context=dict(context),
        )
        self._items.append(captured)
        self._total += 1
        return captured

    def recent(self, limit: int | None = None) -> list[CapturedError]:
        """Most recent errors, newest first."""
        items = list(reversed(self._items))
        return items if limit is None else items[:limit]

    def clear(self) -> None:
        """Drop retained errors. Does not reset ``total_seen``."""
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
