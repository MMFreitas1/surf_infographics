"""Detector evaluation: interval matching and precision/recall/F1.

Detections and ground truth are both time intervals, so scoring is an assignment
problem rather than a per-sample comparison. Two intervals match when their
intersection-over-union clears a threshold; matching is greedy on descending IoU,
which is standard for this shape of problem and is deterministic.

Only verified human labels may enter these metrics (ADR-0006). Enforcing that is the
caller's job -- this module scores whatever it is handed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from surf.models import WaveLabel


@dataclass(frozen=True)
class Interval:
    """A half-open time interval in seconds."""

    t_start: float
    t_end: float

    def __post_init__(self) -> None:
        if self.t_end < self.t_start:
            msg = f"interval ends before it starts: {self.t_start} > {self.t_end}"
            raise ValueError(msg)

    @property
    def duration(self) -> float:
        """Length in seconds."""
        return self.t_end - self.t_start


def iou(a: Interval, b: Interval) -> float:
    """Intersection over union of two intervals. 0.0 when they do not overlap."""
    lo = max(a.t_start, b.t_start)
    hi = min(a.t_end, b.t_end)
    intersection = max(0.0, hi - lo)
    if intersection == 0.0:
        return 0.0
    union = a.duration + b.duration - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


@dataclass(frozen=True)
class MatchResult:
    """Which predictions paired with which truths, and what was left over."""

    matched: list[tuple[int, int]] = field(default_factory=list)
    """(prediction index, truth index) pairs, ordered by descending IoU."""
    unmatched_predictions: list[int] = field(default_factory=list)
    unmatched_truths: list[int] = field(default_factory=list)


def match_intervals(
    predictions: list[Interval],
    truths: list[Interval],
    min_iou: float = 0.3,
) -> MatchResult:
    """Greedily pair predictions to truths by descending IoU.

    Each prediction and each truth is used at most once. Pairs scoring below
    ``min_iou`` are not matched at all.
    """
    scored: list[tuple[float, int, int]] = []
    for pi, p in enumerate(predictions):
        for ti, t in enumerate(truths):
            overlap = iou(p, t)
            if overlap >= min_iou:
                scored.append((overlap, pi, ti))
    # descending IoU; ties broken by index so the result is deterministic
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))

    used_p: set[int] = set()
    used_t: set[int] = set()
    matched: list[tuple[int, int]] = []
    for _, pi, ti in scored:
        if pi in used_p or ti in used_t:
            continue
        used_p.add(pi)
        used_t.add(ti)
        matched.append((pi, ti))

    return MatchResult(
        matched=matched,
        unmatched_predictions=[i for i in range(len(predictions)) if i not in used_p],
        unmatched_truths=[i for i in range(len(truths)) if i not in used_t],
    )


@dataclass(frozen=True)
class Scores:
    """Detection quality against ground truth."""

    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        """Of what we detected, how much was real. 1.0 when nothing was detected."""
        denom = self.true_positives + self.false_positives
        return 1.0 if denom == 0 else self.true_positives / denom

    @property
    def recall(self) -> float:
        """Of what was real, how much we found. 1.0 when there was nothing to find."""
        denom = self.true_positives + self.false_negatives
        return 1.0 if denom == 0 else self.true_positives / denom

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall."""
        p, r = self.precision, self.recall
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def score(
    predictions: list[Interval],
    truths: list[Interval],
    min_iou: float = 0.3,
) -> Scores:
    """Score a detector's output against ground truth."""
    result = match_intervals(predictions, truths, min_iou=min_iou)
    return Scores(
        true_positives=len(result.matched),
        false_positives=len(result.unmatched_predictions),
        false_negatives=len(result.unmatched_truths),
    )


def truth_intervals(labels: Iterable[WaveLabel]) -> list[Interval]:
    """The rides a person marked, as intervals a detector can be scored against.

    Two filters, and both matter. ``counts_as_truth`` keeps out unverified imports
    (ADR-0006) and labels made with L3's proposals on screen (ADR-0012). ``is_wave`` keeps
    out the other half of ground truth: a label saying "I looked, and this is not a ride"
    is a real judgement, but it is not a ride to be found.

    This is the whole join between the labeling UI and the eval harness. Human truth reaches
    :func:`score` through the identical path the synthetic golden uses, so a number measured
    against people and a number measured against the generator are directly comparable.
    """
    return [
        Interval(label.t_start, label.t_end)
        for label in labels
        if label.counts_as_truth and label.is_wave
    ]


def rejected_intervals(labels: Iterable[WaveLabel]) -> list[Interval]:
    """The stretches a person looked at and ruled out.

    Not the complement of :func:`truth_intervals`: everything unlabelled is simply unknown,
    while these are the intervals somebody actually examined and rejected. A detection here
    is a *confirmed* false positive rather than a merely unmatched one, which is the only
    kind precision can be measured on honestly.
    """
    return [
        Interval(label.t_start, label.t_end)
        for label in labels
        if label.counts_as_truth and not label.is_wave
    ]
