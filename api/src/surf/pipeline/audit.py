"""L0.6 -- audit: which part of the recording was actually the session.

A recording starts when the watch does and stops when the surfer remembers to stop it, so a
surf file routinely opens on the walk down and closes on the walk back. On the reference
session the **last eight minutes** are coverage 1.00 at ~0 m/s: the watch is on dry land,
sitting still, and every second of it is perfectly measured.

Those seconds are not bad data and this stage does not treat them as such. **Exclusion, never
demotion** (ADR-0015): the samples keep their position, their speed and ``observed=True``,
because the watch could see -- better than usual, in fact. What changes is which seconds a
session metric is entitled to count. Distance ridden, session duration and waves per ten
minutes are all wrong if they include the walk up the beach.

**Coverage is the signal, and the inversion is the point.** The thing that makes this project
hard -- a wrist underwater half the time -- is exactly what makes this easy. An in-water
window on the reference session runs about 0.39; carry the watch onto the sand and it goes to
1.00. Nothing else in the file separates the two states so cleanly.

This stage hangs off L0.5 in **parallel** with the smoother rather than in series with it.
The audit changes no sample, so making L1 key on its output would mean retuning a coverage
threshold silently invalidated the smoothed track it cannot possibly have changed.

The deterministic baseline here only trims the **ends**. An interior stretch of high coverage
is far more likely to be a surfer sitting up on the board with a dry wrist than one who left
the beach and came back, and guessing otherwise would cut real surfing out of the middle of a
session. Interior stretches are what the audit pass is for, and it has to beat this baseline
before it gets to make that call (ADR-0005).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean, pstdev

from surf.models import (
    Activity,
    AuditReport,
    AuditSource,
    NotSurfingReason,
    NotSurfingWindow,
    Sample,
    SessionWindow,
)
from surf.pipeline.stage import StageMeta

NAME = "L0.6"
"""The audit is stage L0.6: after cleaning, alongside the smoother rather than beneath it."""

CODE_VERSION = "1"
"""Bump when the audit changes what it excludes, so cached verdicts are not reused."""

_REPORT_KEY = "surf.l06.report"
"""Envelope key, so a payload written by something else is refused rather than parsed."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class AuditStage:
    """L0.6: decide which span of the recording is the session.

    Every threshold is in the cache key, so arguing with a boundary is a re-key rather than
    a re-ingest -- and because this stage sits beside L1 rather than above it, doing so
    leaves the smoothed track alone.
    """

    window_s: float = 60.0
    """Digest resolution. A minute is long enough that one lull does not read as an exit and
    short enough to place the boundary to within a minute, which is all the precision the
    question has: nobody enters the water on a particular second."""
    wet_coverage_max: float = 0.85
    """At or below this, the window looks like it was recorded in the water.

    In-water windows on the reference session average 0.39 and dry ones sit at 1.00, so this
    is not a knife-edge -- it is a line drawn across an empty gap. It sits nearer the dry end
    on purpose: the cost of calling a wet window dry is cutting real surfing out of a session,
    and the cost of the opposite is a minute of walking left in.
    """
    out_of_water_speed_max: float = 3.0
    """A window can only be trimmed if nothing in it moved faster than this, m/s.

    Coverage alone is not enough, and the generator's own docstring says why: a rider
    standing up has the wrist clear of the water, so the final ride of a session can be the
    best-covered window in the file. Trimming on dryness alone would cut it off. A surfer
    rides at 4-10 m/s and walks at about 1.3, so this separates the two -- while the coverage
    term handles paddling, which is the same speed as walking and nothing like as dry.
    """
    baseline_confidence: float = 0.7
    """What the baseline claims for its own verdicts. Deliberately not 1.0 -- trimming on
    coverage is a good rule, not a certainty, and a number that says so leaves room for the
    audit pass to be visibly more or less sure."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "window_s": self.window_s,
                "wet_coverage_max": self.wet_coverage_max,
                "out_of_water_speed_max": self.out_of_water_speed_max,
                "baseline_confidence": self.baseline_confidence,
            },
        )

    def run(self, data: Activity) -> AuditReport:
        """Digest the recording and trim it to the part that is the session."""
        samples = data.samples
        if not samples:
            return AuditReport(
                window_s=self.window_s,
                t_start=0.0,
                t_end=0.0,
                surfing_t_start=0.0,
                surfing_t_end=0.0,
            )

        t_start, t_end = samples[0].t, samples[-1].t
        windows = self.digest(samples)
        span = self._surfing_span(windows)

        if span is None:
            # No stretch looked like it was recorded in the water. That is an absent answer,
            # not an empty one: nothing is excluded and the report says it could not tell.
            return AuditReport(
                decided=False,
                window_s=self.window_s,
                windows=windows,
                t_start=t_start,
                t_end=t_end,
                surfing_t_start=t_start,
                surfing_t_end=t_end,
                top_speed_ms_all=_top_speed(samples),
                top_speed_ms_surfing=_top_speed(samples),
            )

        surfing_start, surfing_end = self._settle(span, t_start, t_end)
        excluded: list[NotSurfingWindow] = []
        if surfing_start > t_start:
            excluded.append(self._excluded(t_start, surfing_start, NotSurfingReason.BEFORE_ENTRY))
        if surfing_end < t_end:
            excluded.append(self._excluded(surfing_end, t_end, NotSurfingReason.AFTER_EXIT))

        return AuditReport(
            window_s=self.window_s,
            windows=windows,
            not_surfing=excluded,
            t_start=t_start,
            t_end=t_end,
            surfing_t_start=surfing_start,
            surfing_t_end=surfing_end,
            top_speed_ms_all=_top_speed(samples),
            top_speed_ms_surfing=_top_speed(
                [s for s in samples if surfing_start <= s.t < surfing_end]
            ),
        )

    # -- the digest -------------------------------------------------------------------

    def digest(self, samples: Sequence[Sample]) -> list[SessionWindow]:
        """Slice the recording into windows of numbers, carrying no location whatsoever.

        Shared deliberately: the baseline below and the audit pass that has to beat it read
        exactly this, so the two are compared on identical evidence rather than on two views
        that might differ in some way nobody noticed.
        """
        if not samples:
            return []
        origin = samples[0].t
        windows: list[SessionWindow] = []
        index = 0
        edge = origin
        while index < len(samples):
            edge += self.window_s
            group: list[Sample] = []
            while index < len(samples) and samples[index].t < edge:
                group.append(samples[index])
                index += 1
            if group:
                windows.append(_window(edge - self.window_s, edge, group))
        return windows

    # -- the baseline -----------------------------------------------------------------

    def _surfing_span(self, windows: Sequence[SessionWindow]) -> tuple[float, float] | None:
        """First and last moment that looks like it was recorded in the water.

        Trimmed inward from each end, stopping at the first window that does not look like
        dry land. Deliberately *not* "the longest stretch that looks wet": a session has
        interior dry spells -- a surfer sitting up with the wrist clear reads exactly like
        one standing on the sand -- and treating those as boundaries fragments a one-hour
        session into an eleven-minute one. Measured on the reference recording before this
        was written.

        Returns None when every window looks dry, which is not a session with nothing in it
        but a recording this rule cannot read.
        """
        dry = [self._looks_like_dry_land(w) for w in windows]
        if all(dry):
            return None

        first = dry.index(False)
        last = len(dry) - 1 - dry[::-1].index(False)
        return windows[first].t_start, windows[last].t_end

    def _settle(
        self, span: tuple[float, float], t_start: float, t_end: float
    ) -> tuple[float, float]:
        """Hold the span to the recording, and refuse to claim a boundary too small to see.

        Two corrections, both learned from the tests below. A window is a fixed slice of
        clock time, so the last one runs past the final sample and would otherwise place the
        end of the session after the end of the recording.

        And a leftover shorter than one window is not a walk up the beach -- it is the ragged
        end of the digest. The generator's default session finishes in the water, yet its
        last seven samples fall in a window of their own and read as dry; claiming a
        six-second exit from that is a rounding artefact wearing a verdict's clothes.
        """
        start = max(span[0], t_start)
        end = min(span[1], t_end)
        if start - t_start < self.window_s:
            start = t_start
        if t_end - end < self.window_s:
            end = t_end
        return start, end

    def _looks_like_dry_land(self, window: SessionWindow) -> bool:
        """True when this window has the signature of a watch out of the water.

        Both halves are required. Good reception alone is a lull; slow movement alone is
        paddling. Together, and only together, they are the walk up the beach.
        """
        fast = window.speed_max_ms is not None and window.speed_max_ms > self.out_of_water_speed_max
        return window.coverage > self.wet_coverage_max and not fast

    def _excluded(self, start: float, end: float, reason: NotSurfingReason) -> NotSurfingWindow:
        """One stretch the baseline is trimming, with the confidence it actually has."""
        return NotSurfingWindow(
            t_start=start,
            t_end=end,
            reason=reason,
            source=AuditSource.BASELINE,
            confidence=self.baseline_confidence,
        )

    # -- payload ----------------------------------------------------------------------

    def encode(self, output: AuditReport) -> bytes:
        """Serialise the report. It is a nested document, so it is stored as one.

        The other stages write Parquet because their outputs are tables; forcing this one
        into columns would mean flattening a report and rebuilding it on the way out, which
        is two chances to disagree with itself for no gain.
        """
        return json.dumps({_REPORT_KEY: output.model_dump(mode="json")}).encode("utf-8")

    def decode(self, payload: bytes) -> AuditReport:
        """Rebuild the report ``encode`` wrote."""
        try:
            envelope = json.loads(payload)
            body = envelope[_REPORT_KEY]
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            msg = f"{NAME} payload carries no audit report: it was not written by this stage"
            raise PayloadError(msg) from exc
        return AuditReport.model_validate(body)


# -- helpers --------------------------------------------------------------------------


def _window(start: float, end: float, group: Sequence[Sample]) -> SessionWindow:
    """Digest one slice. Every field is a rate, a fraction or a count -- never a place."""
    speeds = [s.speed_ms for s in group if s.speed_ms is not None]
    hrs = [s.hr_bpm for s in group if s.hr_bpm is not None]
    return SessionWindow(
        t_start=start,
        t_end=end,
        sample_count=len(group),
        coverage=sum(1 for s in group if s.has_position) / len(group),
        speed_mean_ms=fmean(speeds) if speeds else None,
        speed_max_ms=max(speeds) if speeds else None,
        speed_sd_ms=pstdev(speeds) if len(speeds) > 1 else None,
        odometer_rate_ms=_odometer_rate(group, end - start),
        hr_mean_bpm=fmean(hrs) if hrs else None,
    )


def _odometer_rate(group: Sequence[Sample], span_s: float) -> float | None:
    """Mean ground speed from the device's distance counter across this window.

    Worth carrying even though the baseline does not read it: the counter survives the blind
    half of a session, so it is the one speed signal that does not thin out exactly where the
    surfing happens.
    """
    readings = [s.distance_m for s in group if s.distance_m is not None]
    if len(readings) < 2 or span_s <= 0.0:
        return None
    return (readings[-1] - readings[0]) / span_s


def _top_speed(samples: Sequence[Sample]) -> float | None:
    """Fastest recorded second in this set, or None when none of them recorded a speed."""
    speeds = [s.speed_ms for s in samples if s.speed_ms is not None]
    return max(speeds) if speeds else None
