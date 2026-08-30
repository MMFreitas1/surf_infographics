"""Running the L1->L3 chain for one stored session.

The chain rule this file exists to hold: **each stage keys on the key of the stage before
it**, never on the activity id. L1's input hash is L0's key, L2's is L1's, L3's is L2's. So
a track can never outlive the samples it was computed from, and re-ingesting a session
under new parse parameters invalidates everything downstream without anyone remembering to
say so. `tests/test_pipeline_spine.py` pins that property; this module is where the API
inherits it rather than re-deriving it per endpoint.

Stage parameters stay at their defaults here. They are part of the cache key, so sweeping
one later means passing a differently configured stage in -- not clearing a cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from surf.models import Activity, SessionTrack
from surf.pipeline.cache import StageCache
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FramedTrack, FrameStage
from surf.pipeline.l3 import CandidateSet, CandidateStage
from surf.pipeline.runner import StageResult, run_stage


@dataclass(frozen=True)
class ChainResult:
    """Where the chain got to, and whether the cache did the work.

    ``cached`` is false when any link had to run. It exists so "scrubbing is served from
    cache" is observable in the logs rather than asserted in a doc (architecture.md §7).
    """

    track: SessionTrack
    frame_key: str
    cached: bool


def run_chain(activity: Activity, cache: StageCache, *, samples_key: str) -> ChainResult:
    """Smooth the session and rotate it into its shore frame."""
    smoothed = run_stage(KinematicsStage(), cache, input_hash=samples_key, data=activity)
    framed: StageResult[FramedTrack] = run_stage(
        FrameStage(), cache, input_hash=smoothed.key, data=smoothed.output
    )
    return ChainResult(
        track=SessionTrack(
            frame=framed.output.frame,
            smoothed=smoothed.output,
            framed=framed.output.samples,
        ),
        frame_key=framed.key,
        cached=smoothed.cached and framed.cached,
    )


def track_for(activity: Activity, cache: StageCache, *, samples_key: str) -> ChainResult:
    """The L1 track and its L2 rotation, as one aligned pair the UI can draw."""
    return run_chain(activity, cache, samples_key=samples_key)


def candidates_for(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[CandidateSet, bool]:
    """L3's proposals for this session, and whether the whole chain came from cache."""
    chain = run_chain(activity, cache, samples_key=samples_key)
    framed = FramedTrack(frame=chain.track.frame, samples=chain.track.framed)
    proposed: StageResult[CandidateSet] = run_stage(
        CandidateStage(), cache, input_hash=chain.frame_key, data=framed
    )
    return proposed.output, chain.cached and proposed.cached
