"""The stage contract every pipeline step implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class StageMeta:
    """Identity of a stage, used to build its cache key."""

    name: str
    code_version: str
    params: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Stage[Out](Protocol):
    """A pure transformation `f(input, params) -> output`, and how to store the result.

    Implementations must be deterministic: the same input and params must always
    produce the same output, with no reliance on wall-clock time, network or randomness.

    ``encode`` and ``decode`` must round-trip. A cached payload stands in for running the
    stage, so decoding one has to yield what a run would have yielded -- otherwise the
    cache stops being an optimisation and becomes a second, quietly different answer.
    That is also why a payload has to be self-describing: decoding must not depend on a
    database row that a cache-only re-run may not have.
    """

    @property
    def meta(self) -> StageMeta:
        """Stage identity."""
        ...

    def run(self, data: Any) -> Out:
        """Transform the input."""
        ...

    def encode(self, output: Out) -> bytes:
        """Serialise an output for the cache."""
        ...

    def decode(self, payload: bytes) -> Out:
        """Rebuild the output ``encode`` wrote."""
        ...
