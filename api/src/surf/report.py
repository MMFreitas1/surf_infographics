"""What the human labels say — including the one question Phase 4 exists to settle.

`surf.synthetic` drops GPS independently of what the surfer is doing. The standing
hypothesis is that a real watch does not: during a ride the rider is up, the wrist comes
clear of the water, and the fix comes back. Phase 3 measured the consequence of assuming
otherwise — every ride L3 missed on the synthetic was one that was mostly blind — but
nothing before human labels could tell us which world we are in.

This module is the measurement. Point it at a labelled session and it reports position
coverage *during labelled rides* against coverage across the session as a whole. If rides
are better observed, position availability is a feature and L3's ceiling rises on its own.
If they are not, a mostly-submerged ride may be genuinely undetectable from GPS alone, and
that is a product fact worth knowing before Phase 5 tunes anything.

It reports; it does not gate. There is no threshold here that fails a build, because the
answer is a property of the sport and the watch, not of our code.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from surf.config import get_settings
from surf.evaluation import Interval, Scores, iou, rejected_intervals, score, truth_intervals
from surf.models import LabelSource, WaveCandidate, WaveLabel
from surf.pipeline import StageCache
from surf.pipeline.session import candidates_for, track_for
from surf.store import ActivityRepository, LabelRepository

MIN_RIDES_FOR_A_VERDICT = 5
"""Below this, the comparison is reported but no verdict is offered. Three rides can point
anywhere, and a tool that says "confirmed" off three rides teaches you to trust it wrongly."""

MATERIAL_LIFT = 0.05
"""Coverage differences smaller than five points are called what they are: not material."""

MIN_IOU = 0.3
"""Overlap at which a proposal is judged to be *about* a labelled interval. Matches the
default in :func:`surf.evaluation.score`, so the two halves of this report agree."""


class ObservedSample(Protocol):
    """Anything carrying a time and whether that second had a fix."""

    @property
    def t(self) -> float: ...

    @property
    def observed(self) -> bool: ...


@dataclass(frozen=True)
class CoverageComparison:
    """Position coverage inside labelled rides, against the session as a whole."""

    rides: int
    ride_seconds: int
    ride_coverage: float
    session_seconds: int
    session_coverage: float

    @property
    def lift(self) -> float:
        """How much better observed a ride is than the session it sits in."""
        return self.ride_coverage - self.session_coverage

    @property
    def verdict(self) -> str:
        """A sentence, hedged exactly as far as the evidence requires.

        This is a description of one session, not a significance test. It says what the
        numbers are and refuses to say more than that.
        """
        if self.rides < MIN_RIDES_FOR_A_VERDICT:
            return f"too few labelled rides ({self.rides}) to say anything"
        if self.lift > MATERIAL_LIFT:
            return "rides are better observed than the session — consistent with recovery"
        if self.lift < -MATERIAL_LIFT:
            return "rides are *worse* observed than the session — the opposite of the hypothesis"
        return "no material difference between rides and the session"


@dataclass(frozen=True)
class SessionReport:
    """Everything the labels on one session support saying."""

    activity_id: str
    labels_total: int
    rides: int
    rejections: int
    assisted: int
    uncounted: int
    """Labels that exist but cannot enter a metric: unverified, or candidate-assisted."""
    coverage: CoverageComparison | None
    candidates: int
    scores: Scores | None
    """L3 against this session's human truth. None when there is no truth to score against."""
    confirmed_false_positives: int
    """Proposals landing on a stretch a person examined and rejected. Unlike an unmatched
    proposal, which may simply be unlabelled, this one is wrong on the record."""


def coverage_of(
    samples: Sequence[ObservedSample], intervals: Sequence[Interval]
) -> tuple[int, float]:
    """How many seconds those intervals cover, and what fraction of them had a fix."""
    during = [
        sample for sample in samples if any(i.t_start <= sample.t < i.t_end for i in intervals)
    ]
    if not during:
        return 0, 0.0
    return len(during), sum(1 for s in during if s.observed) / len(during)


def compare_coverage(
    samples: Sequence[ObservedSample], rides: Sequence[Interval]
) -> CoverageComparison | None:
    """The hypothesis check: coverage inside rides against coverage overall."""
    if not samples or not rides:
        return None
    ride_seconds, ride_coverage = coverage_of(samples, rides)
    if ride_seconds == 0:
        return None
    return CoverageComparison(
        rides=len(rides),
        ride_seconds=ride_seconds,
        ride_coverage=ride_coverage,
        session_seconds=len(samples),
        session_coverage=sum(1 for s in samples if s.observed) / len(samples),
    )


def build_report(
    activity_id: str,
    samples: Sequence[ObservedSample],
    labels: Iterable[WaveLabel],
    candidates: Sequence[WaveCandidate],
) -> SessionReport:
    """Assemble everything one labelled session supports saying. Pure; no I/O."""
    rows = list(labels)
    rides = truth_intervals(rows)
    rejected = rejected_intervals(rows)
    proposals = [Interval(c.t_start, c.t_end) for c in candidates]

    return SessionReport(
        activity_id=activity_id,
        labels_total=len(rows),
        rides=len(rides),
        rejections=len(rejected),
        assisted=sum(1 for r in rows if r.source is LabelSource.HUMAN_ASSISTED),
        uncounted=sum(1 for r in rows if not r.counts_as_truth),
        coverage=compare_coverage(samples, rides),
        candidates=len(proposals),
        scores=score(proposals, rides) if rides else None,
        confirmed_false_positives=len(
            [p for p in proposals if any(iou(p, r) >= MIN_IOU for r in rejected)]
        ),
    )


def format_report(report: SessionReport) -> str:
    """The report as something a person reads in a terminal."""
    lines = [
        f"session {report.activity_id}",
        f"  labels          {report.labels_total} "
        f"({report.rides} rides, {report.rejections} rejections, "
        f"{report.assisted} assisted, {report.uncounted} not counted as truth)",
    ]

    if report.coverage is None:
        lines.append("  coverage        no labelled rides yet — nothing to compare")
    else:
        c = report.coverage
        lines += [
            f"  during rides    {c.ride_coverage:.1%} of {c.ride_seconds} s measured",
            f"  whole session   {c.session_coverage:.1%} of {c.session_seconds} s measured",
            f"  lift            {c.lift:+.1%}  →  {c.verdict}",
        ]

    if report.scores is None:
        lines.append("  L3 vs truth     no human truth on this session yet")
    else:
        s = report.scores
        lines += [
            f"  L3 proposals    {report.candidates}",
            f"  L3 vs truth     recall {s.recall:.3f} · precision {s.precision:.3f} · "
            f"F1 {s.f1:.3f}",
            f"  confirmed FPs   {report.confirmed_false_positives} "
            f"(proposals on stretches a person ruled out)",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Report on every labelled session in the local store.

    Reads the store directly rather than over HTTP, so it works with the API stopped.
    """
    wanted = list(argv if argv is not None else sys.argv[1:])
    settings = get_settings()
    cache = StageCache(settings.cache_dir)
    activities = ActivityRepository(settings.db_path, cache)
    labels = LabelRepository(settings.db_path)

    try:
        summaries = activities.summaries()
        chosen = [s for s in summaries if not wanted or s.activity_id in wanted]
        if not chosen:
            # Nothing to report is a state, not a failure -- until you asked for something
            # specific, which is the one case where silence would be misleading.
            if wanted:
                print(f"no session matching {wanted}")
                return 1
            print("no sessions stored — ingest one first")
            return 0

        reported = 0
        for summary in chosen:
            rows = labels.for_activity(summary.activity_id, current=True)
            if not rows:
                continue
            activity = activities.get(summary.activity_id)
            samples_key = activities.samples_key(summary.activity_id)
            if activity is None or samples_key is None:  # pragma: no cover - defensive
                continue
            chain = track_for(activity, cache, samples_key=samples_key)
            proposed, _ = candidates_for(activity, cache, samples_key=samples_key)
            print(
                format_report(
                    build_report(
                        summary.activity_id, chain.track.smoothed, rows, proposed.candidates
                    )
                )
            )
            reported += 1

        if reported == 0:
            print("no labelled sessions yet — label one at http://127.0.0.1:3000")
        return 0
    finally:
        activities.close()
        labels.close()


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
