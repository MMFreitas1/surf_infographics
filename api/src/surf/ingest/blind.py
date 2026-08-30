"""Where the session has no usable position.

A blind window is a first-class object, not an absence (ADR-0003). Roughly half of a surf
session lands in one, so how their bounds are drawn decides every coverage number the app
reports. Two things can hide a position, and they are not the same failure:

* the record exists and its position field is empty -- the wrist was underwater
  (:class:`~surf.models.BlindCause.NO_FIX`);
* the record is not there at all -- a lossy export, or the device stopped logging
  (:class:`~surf.models.BlindCause.MISSING_RECORD`).

**Bounds convention:** a sample describes the interval that *starts* at its timestamp and
runs until the next sample. So a run of blind samples ends where the next positioned
sample begins, and a run of *n* blind samples in a 1 Hz recording is *n* seconds blind.
This is what makes the two derivations agree: the reference session's FIT reports 1941
blind samples and its GPX -- which drops those records entirely -- reports 1941 s of gaps.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

from surf.models import BlindCause, BlindWindow, Sample

DEFAULT_INTERVAL_S = 1.0
"""Assumed sampling period when a session is too short to measure one."""

GAP_TOLERANCE = 1.5
"""A step longer than this many nominal intervals means a record is missing, not late."""


def nominal_interval(samples: Sequence[Sample]) -> float:
    """The session's typical sampling period, measured rather than assumed.

    The *most common* step, not the median: a cadence repeats and a gap does not, so the
    mode survives a session that is mostly gaps. A median would sit between the two -- on
    samples one second and then four seconds apart it reports 2.5 s, which is neither the
    cadence nor the gap, and would then mis-draw every window it is used to bound.
    Ties break towards the shortest step, the best evidence of cadence when nothing repeats.
    """
    deltas = [b.t - a.t for a, b in pairwise(samples) if b.t > a.t]
    if not deltas:
        return DEFAULT_INTERVAL_S
    counts = Counter(deltas)
    most_common = max(counts.values())
    return min(delta for delta, count in counts.items() if count == most_common)


def blind_from_missing_positions(
    samples: Sequence[Sample], *, interval_s: float | None = None
) -> list[BlindWindow]:
    """Windows where a record exists but carries no fix."""
    interval = nominal_interval(samples) if interval_s is None else interval_s
    windows: list[BlindWindow] = []
    index = 0
    count = len(samples)
    while index < count:
        if samples[index].has_position:
            index += 1
            continue
        last = index
        while last + 1 < count and not samples[last + 1].has_position:
            last += 1
        end = samples[last + 1].t if last + 1 < count else samples[last].t + interval
        windows.append(BlindWindow(t_start=samples[index].t, t_end=end, cause=BlindCause.NO_FIX))
        index = last + 1
    return windows


def blind_from_time_gaps(
    samples: Sequence[Sample], *, interval_s: float | None = None
) -> list[BlindWindow]:
    """Windows where no record was written at all.

    The window opens one interval after the last sample we have -- that sample's own second
    is not blind -- and closes when recording resumes.
    """
    interval = nominal_interval(samples) if interval_s is None else interval_s
    windows: list[BlindWindow] = []
    for earlier, later in pairwise(samples):
        if later.t - earlier.t > interval * GAP_TOLERANCE:
            windows.append(
                BlindWindow(
                    t_start=earlier.t + interval,
                    t_end=later.t,
                    cause=BlindCause.MISSING_RECORD,
                )
            )
    return windows


def derive_blind_windows(samples: Sequence[Sample]) -> list[BlindWindow]:
    """Every window with no usable position, from both causes, in time order.

    Both derivations run for every fidelity: a FIT can still contain a gap where the device
    stopped logging, and a TCX can contain a trackpoint with no position.
    """
    interval = nominal_interval(samples)
    windows = blind_from_missing_positions(samples, interval_s=interval)
    windows += blind_from_time_gaps(samples, interval_s=interval)
    windows.sort(key=lambda window: window.t_start)
    return windows
