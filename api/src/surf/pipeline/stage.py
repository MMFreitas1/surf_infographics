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
class Stage(Protocol):
    """A pure transformation `f(input, params) -> output`.

    Implementations must be deterministic: the same input and params must always
    produce the same output, with no reliance on wall-clock time, network or randomness.
    """

    @property
    def meta(self) -> StageMeta:
        """Stage identity."""
        ...

    def run(self, data: Any) -> Any:
        """Transform the input."""
        ...
