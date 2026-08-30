"""RAM lifecycle for the local quantized model.

The model saturates memory only while in use. It loads on demand, and unloads either
automatically once it has been idle past a TTL, or immediately on explicit command.

The logic here is deliberately pure: the clock and the model backend are both injected,
so the whole lifecycle is testable offline with no Ollama running.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

Clock = Callable[[], float]
"""Monotonic seconds source."""


class ModelBackend(Protocol):
    """Whatever actually holds the weights in memory (Ollama in production)."""

    def load(self, model: str) -> None:
        """Bring the model into memory."""
        ...

    def unload(self, model: str) -> None:
        """Evict the model from memory."""
        ...

    def is_loaded(self, model: str) -> bool:
        """True while the weights are resident."""
        ...


@dataclass(frozen=True)
class LlmStatus:
    """Snapshot of the lifecycle, surfaced by GET /llm/status."""

    model: str
    loaded: bool
    idle_seconds: float
    idle_ttl_seconds: float
    in_use: int

    @property
    def unloads_in_seconds(self) -> float | None:
        """Seconds until automatic unload, or None when not applicable."""
        if not self.loaded or self.in_use > 0:
            return None
        return max(0.0, self.idle_ttl_seconds - self.idle_seconds)


class LlmLifecycle:
    """Load-on-demand, unload-when-idle manager for a single local model."""

    def __init__(
        self,
        backend: ModelBackend,
        model: str,
        idle_ttl_seconds: float,
        clock: Clock,
    ) -> None:
        self._backend = backend
        self._model = model
        self._idle_ttl = idle_ttl_seconds
        self._clock = clock
        self._last_used: float = clock()
        self._in_use = 0

    def acquire(self) -> _Lease:
        """Reserve the model for a unit of work, loading it if necessary."""
        if not self._backend.is_loaded(self._model):
            self._backend.load(self._model)
        self._in_use += 1
        self._last_used = self._clock()
        return _Lease(self)

    def _release(self) -> None:
        self._in_use = max(0, self._in_use - 1)
        self._last_used = self._clock()

    def tick(self) -> bool:
        """Unload if the model has been idle past its TTL. Returns True if it unloaded.

        Safe to call on a timer; it is a no-op while work is in flight.
        """
        if self._in_use > 0 or not self._backend.is_loaded(self._model):
            return False
        if self._clock() - self._last_used < self._idle_ttl:
            return False
        self._backend.unload(self._model)
        return True

    def unload_now(self) -> bool:
        """Evict the model immediately, on user command. Returns True if it unloaded.

        Refuses while work is in flight -- the caller should retry rather than corrupt
        an in-progress adjudication.
        """
        if self._in_use > 0 or not self._backend.is_loaded(self._model):
            return False
        self._backend.unload(self._model)
        return True

    def status(self) -> LlmStatus:
        """Current lifecycle snapshot."""
        return LlmStatus(
            model=self._model,
            loaded=self._backend.is_loaded(self._model),
            idle_seconds=self._clock() - self._last_used,
            idle_ttl_seconds=self._idle_ttl,
            in_use=self._in_use,
        )


class _Lease:
    """Context manager returned by :meth:`LlmLifecycle.acquire`."""

    def __init__(self, owner: LlmLifecycle) -> None:
        self._owner = owner

    def __enter__(self) -> _Lease:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._owner._release()
