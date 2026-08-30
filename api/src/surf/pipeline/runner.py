"""Running a stage against the content-addressed cache.

A stage is pure, so its output is a function of its input, its params and its code version.
Running one therefore means: compute the key, hand back the cached output if it is there,
otherwise do the work and store it.

Every stage from L0 upwards goes through :func:`run_stage`, so "is the pipeline actually
wired together" stays a property of one call site that one test can pin, rather than a
claim each phase makes for itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from surf.pipeline.cache import StageCache
from surf.pipeline.stage import Stage


@dataclass(frozen=True)
class StageResult[Out]:
    """What a stage produced, where it is cached, and whether the cache produced it."""

    output: Out
    key: str
    cached: bool
    """False when this run did the work. Nothing downstream should behave differently --
    it exists so that "the cache is actually being hit" is observable rather than assumed."""


def stage_key(stage: Stage[Any], cache: StageCache, input_hash: str) -> str:
    """The key this stage's output is addressed by, for the given input."""
    return cache.key(
        input_hash=input_hash,
        params=stage.meta.params,
        code_version=stage.meta.code_version,
    )


def run_stage[Out](
    stage: Stage[Out], cache: StageCache, *, input_hash: str, data: Any
) -> StageResult[Out]:
    """Run a stage, reusing the stored output when one exists for these exact inputs."""
    key = stage_key(stage, cache, input_hash)
    payload = cache.get(stage.meta.name, key)
    if payload is not None:
        return StageResult(output=stage.decode(payload), key=key, cached=True)
    output = stage.run(data)
    cache.put(stage.meta.name, key, stage.encode(output))
    return StageResult(output=output, key=key, cached=False)
