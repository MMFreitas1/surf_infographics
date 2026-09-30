"""Running the L0.5->L3 chain for one stored session.

The chain rule this file exists to hold: **each stage keys on the key of the stage before
it**, never on the activity id. L0.5's input hash is L0's key, L1's is L0.5's, L2's is L1's,
L3's is L2's. So a track can never outlive the samples it was computed from, and re-ingesting
a session under new parse parameters -- or loosening a rejection threshold -- invalidates
everything downstream without anyone remembering to say so.
`tests/test_pipeline_spine.py` pins that property; this module is where the API inherits it
rather than re-deriving it per endpoint.

L0.5 is first in the chain because everything after it estimates, and an estimator handed an
impossible fix produces a confident wrong answer rather than an error (ADR-0014).

L0.6 is the exception to the single-file chain, and deliberately so: it hangs off L0.5
**beside** L1 rather than between them. The audit changes no sample -- it decides which
seconds count as session -- so keying L1 on it would mean retuning a coverage threshold
invalidated a smoothed track that cannot possibly have changed (ADR-0015).

Stage parameters stay at their defaults here. They are part of the cache key, so sweeping
one later means passing a differently configured stage in -- not clearing a cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from surf.models import Activity, AuditReport, CleanReport, SessionTrack, SessionVerdict
from surf.pipeline.audit import AuditStage
from surf.pipeline.cache import StageCache
from surf.pipeline.clean import CleanedSession, CleanStage
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FramedTrack, FrameStage
from surf.pipeline.l3 import CandidateSet, CandidateStage
from surf.pipeline.l4 import FeatureInput, FeatureSet, FeatureStage
from surf.pipeline.l5 import ClassifyStage
from surf.pipeline.runner import StageResult, run_stage, stage_key


@dataclass(frozen=True)
class ChainResult:
    """Where the chain got to, and whether the cache did the work.

    ``cached`` is false when any link had to run. It exists so "scrubbing is served from
    cache" is observable in the logs rather than asserted in a doc (architecture.md §7).
    """

    track: SessionTrack
    frame_key: str
    cached: bool
    report: CleanReport
    """What L0.5 refused to believe on the way through. Carried so that a caller drawing
    the track can say how much of it survived cleaning, without a second trip."""


def clean_session(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> StageResult[CleanedSession]:
    """L0.5 for one stored session: the head of every chain below."""
    return run_stage(CleanStage(), cache, input_hash=samples_key, data=activity)


def run_chain(activity: Activity, cache: StageCache, *, samples_key: str) -> ChainResult:
    """Clean the session, smooth it, and rotate it into its shore frame."""
    cleaned = clean_session(activity, cache, samples_key=samples_key)
    smoothed = run_stage(
        KinematicsStage(), cache, input_hash=cleaned.key, data=cleaned.output.activity
    )
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
        cached=cleaned.cached and smoothed.cached and framed.cached,
        report=cleaned.output.report,
    )


def track_for(activity: Activity, cache: StageCache, *, samples_key: str) -> ChainResult:
    """The L1 track and its L2 rotation, as one aligned pair the UI can draw."""
    return run_chain(activity, cache, samples_key=samples_key)


def audit_for(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[AuditReport, bool]:
    """Which span of this recording is the session, and whether the cache produced it.

    Runs the cleaner first, because coverage has to mean what we believe rather than what
    was recorded: a fix L0.5 refused must not go on counting as a second the watch saw, or
    the very signal this stage reads would be measuring the artefacts too.
    """
    cleaned = clean_session(activity, cache, samples_key=samples_key)
    audited = run_stage(AuditStage(), cache, input_hash=cleaned.key, data=cleaned.output.activity)
    return audited.output, cleaned.cached and audited.cached


def cleaning_for(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[CleanReport, bool]:
    """What L0.5 rejected on this session, and whether the cache produced it.

    Its own entry point rather than a field read off the track: device confidence is a
    question about the recording, and answering it must not require smoothing the session
    first (ADR-0014).
    """
    cleaned = clean_session(activity, cache, samples_key=samples_key)
    return cleaned.output.report, cleaned.cached


def _proposed(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[StageResult[CandidateSet], ChainResult]:
    """L3 for one stored session, with its key and the chain that produced it.

    Private because callers want one or the other: the API wants the proposals, L4 wants the
    key to hang off. Sharing the body is what keeps the two from drifting into computing
    candidates two slightly different ways.
    """
    chain = run_chain(activity, cache, samples_key=samples_key)
    framed = FramedTrack(frame=chain.track.frame, samples=chain.track.framed)
    proposed: StageResult[CandidateSet] = run_stage(
        CandidateStage(), cache, input_hash=chain.frame_key, data=framed
    )
    return proposed, chain


def candidates_for(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[CandidateSet, bool]:
    """L3's proposals for this session, and whether the whole chain came from cache."""
    proposed, chain = _proposed(activity, cache, samples_key=samples_key)
    return proposed.output, chain.cached and proposed.cached


def features_for(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[FeatureSet, bool]:
    """L4: every proposal measured against every channel, keyed on L3.

    The cleaned samples are passed alongside the track because the track carries neither
    heart rate nor the odometer, and those are the two channels that survive a blind window
    -- the whole reason L4 can say anything about a proposal the smoother had to estimate.
    """
    cleaned = clean_session(activity, cache, samples_key=samples_key)
    proposed, chain = _proposed(activity, cache, samples_key=samples_key)
    measured: StageResult[FeatureSet] = run_stage(
        FeatureStage(),
        cache,
        input_hash=proposed.key,
        data=FeatureInput(
            candidates=proposed.output,
            framed=chain.track.framed,
            samples=cleaned.output.activity.samples,
        ),
    )
    return measured.output, chain.cached and proposed.cached and measured.cached


def waves_for(
    activity: Activity, cache: StageCache, *, samples_key: str
) -> tuple[SessionVerdict, bool]:
    """L5: how many waves this session had, and how each candidate was settled.

    The end of the chain, and the only place a verdict exists. Ships with no adjudicator:
    ADR-0017 measured the local model against this rule and it did not clear the bar, so the
    band goes unresolved rather than being answered by something unmeasured.
    """
    measured, cached = features_for(activity, cache, samples_key=samples_key)
    proposed, _ = _proposed(activity, cache, samples_key=samples_key)
    stage = ClassifyStage()
    decided: StageResult[SessionVerdict] = run_stage(
        stage,
        cache,
        input_hash=stage_key(FeatureStage(), cache, proposed.key),
        data=measured,
    )
    return decided.output, cached and decided.cached
