"""Pure, content-addressed pipeline stages (L0-L6).

This package holds the machinery -- the stage contract, the cache and the runner.
Stage implementations live next to what they transform: L0 is
:class:`surf.ingest.stage.IngestStage`, and L1 onwards land in this package as they are
built. Keeping L0 in ``ingest`` matches the component map in docs/architecture.md and
keeps the dependency arrow pointing one way: ingest uses the pipeline, not the reverse.
"""

from surf.pipeline.cache import StageCache, content_hash
from surf.pipeline.runner import StageResult, run_stage, stage_key
from surf.pipeline.stage import Stage, StageMeta

__all__ = [
    "Stage",
    "StageCache",
    "StageMeta",
    "StageResult",
    "content_hash",
    "run_stage",
    "stage_key",
]
