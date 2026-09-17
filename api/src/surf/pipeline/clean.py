"""L0.5 -- clean signal: refuse the fixes and speeds that physics rules out.

This stage sits between ingest and the smoother because nothing downstream is worth drawing
until the impossible is gone. The reference session's raw track jumps **109 m/s** between
adjacent fixes, and its speed field reports **74.8 km/h** for a surfer who does 25-35.

**Rejection is a demotion, never a deletion** (ADR-0014). A refused fix becomes a second with
no position, exactly like a submerged wrist, and L1 estimates it like any other gap. Deleting
the row would shorten the session; keeping the row and lying about coverage would be worse.

Two channels, because a session records how fast the surfer was going in three independent
ways and they fail separately:

* the **positions**, differenced -- caught by ``implied_speed``, ``implied_acceleration`` and
  ``jump_and_return``, all of which demote the fix;
* the **speed field**, checked against the device's own odometer or against the fixes
  bracketing it -- caught by ``speed_vs_odometer``, ``speed_vs_position`` and
  ``speed_impossible``, all of which drop only the speed and leave the position standing.

The split matters. Demoting a good position because its speed reading is garbage would
report "we could not see" about a second the watch saw perfectly well, and coverage has to
keep meaning what it says in both directions.

What this stage deliberately does not do is judge *stretches*. A second that every channel
agrees is fast is not something per-fix physics can refuse, even when the surrounding minute
is obviously someone walking up the beach. That residue is Pass 2's job, and leaving it here
rather than inventing a rule for it is the difference between a cleaner and a fudge.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import pyarrow as pa
import pyarrow.parquet as pq

from surf.geo import LocalFrame
from surf.ingest import stage as l0
from surf.ingest.blind import blind_from_missing_positions
from surf.models import (
    Activity,
    BlindCause,
    BlindWindow,
    CleanReport,
    RejectedFix,
    RejectionEffect,
    RejectionReason,
    Sample,
)
from surf.pipeline.stage import StageMeta

NAME = "L0.5"
"""Cleaning is stage L0.5: after ingest, before anything that estimates."""

CODE_VERSION = "1"
"""Bump when the rules change what they reject, so cached sessions are not reused."""

_REPORT_KEY = b"surf.l05.report"
"""Parquet key-value metadata entry holding the :class:`CleanReport`."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class CleanedSession:
    """L0.5's output: the session with the impossible demoted, and what was demoted.

    The report travels with the samples rather than being fetched separately, for the same
    reason L3's frame travels with its candidates: a cleaned session is only interpretable
    alongside the record of what cleaning it took.
    """

    activity: Activity
    report: CleanReport


@dataclass(frozen=True)
class _Fix:
    """A positioned sample with its position already projected into metres."""

    t: float
    x: float
    y: float


@dataclass(frozen=True)
class CleanStage:
    """L0.5: reject fixes and speed readings that physics rules out.

    Every threshold is in the cache key, so a sweep is a re-key and not a re-ingest.
    """

    enabled: bool = True
    """Switch the cleaner off. It is a param, so the cache key notices and a cached clean
    session is never served as an uncleaned one."""

    max_implied_speed_ms: float = 18.0
    """Speed from the last *accepted* fix above which a fix is not evidence about position.

    Deliberately looser than L1's ``max_speed_ms`` of 12.0, and the difference is the whole
    argument: L1 *softens* a suspect fix by inflating its variance, so a false positive
    there costs almost nothing, while this stage *removes* one, so a false positive here
    destroys a measurement. Sweeping the synthetic fixture across five seeds, 12.0 demotes
    3-7 genuine ride seconds per session and 18.0 demotes none on four of the five.
    """
    max_implied_accel_ms2: float = 15.0
    """Change in implied speed per second above which the track is not describing a body in
    water. Roughly 1.5 g, and chosen the same way: above anything the synthetic's take-offs
    produce, so it can only catch artefacts."""

    jump_window_s: float = 2.0
    """How far apart the fixes bracketing a suspected out-and-back may be."""
    jump_min_m: float = 20.0
    """Each leg of the out-and-back must be at least this long to count as a jump.

    This floor is doing one job: staying above GPS noise. Differencing two fixes at 3 m
    noise gives legs averaging ~5 m and routinely reaching 10 m, so a lower floor convicts
    a surfer sitting still -- swept across five synthetic seeds, 10.0 fires 7-14 times per
    session on nothing at all, and 20.0 fires zero times on any session we have.
    """
    jump_net_ratio: float = 0.35
    """Net displacement, as a fraction of the two legs, below which the track went nowhere."""

    max_recorded_speed_ms: float = 25.0
    """A reported speed beyond anything a surfboard does, refused with no corroboration."""
    min_checkable_speed_ms: float = 8.0
    """Below this a reported speed is plausible paddling, and corroboration is too noisy to
    convict on. Checking it would generate false positives, not truth."""
    speed_agreement_ratio: float = 0.35
    """How far the corroborating channel may fall short of the reported speed before the two
    are judged to disagree rather than merely differ.

    On the reference session's one genuine fast ride the odometer reads 0.51-0.81 of the
    speed field; across the end-of-session artefact cluster it reads 0.00-0.18. This sits
    in the gap, and it is a gap rather than a knife-edge.
    """
    speed_bracket_s: float = 10.0
    """Widest span of bracketing fixes that can still contradict a single second's speed."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Every threshold is here, because every one changes the output."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "enabled": self.enabled,
                "max_implied_speed_ms": self.max_implied_speed_ms,
                "max_implied_accel_ms2": self.max_implied_accel_ms2,
                "jump_window_s": self.jump_window_s,
                "jump_min_m": self.jump_min_m,
                "jump_net_ratio": self.jump_net_ratio,
                "max_recorded_speed_ms": self.max_recorded_speed_ms,
                "min_checkable_speed_ms": self.min_checkable_speed_ms,
                "speed_agreement_ratio": self.speed_agreement_ratio,
                "speed_bracket_s": self.speed_bracket_s,
            },
        )

    # -- the pass ---------------------------------------------------------------------

    def run(self, data: Activity) -> CleanedSession:
        """Demote what cannot be true, and report every demotion with its evidence."""
        samples = data.samples
        if not self.enabled or not samples:
            return CleanedSession(activity=data, report=_report(self.enabled, samples, samples, []))

        demoted = self._position_channel(samples)
        dropped = self._speed_channel(samples, demoted)

        cleaned = [
            _demote(s) if s.t in demoted else _drop_speed(s) if s.t in dropped else s
            for s in samples
        ]
        rejections = sorted(
            [*demoted.values(), *dropped.values()], key=lambda r: (r.t, r.reason.value)
        )
        return CleanedSession(
            activity=data.model_copy(
                update={"samples": cleaned, "blind_windows": _rewindow(data, cleaned)}
            ),
            report=_report(self.enabled, samples, cleaned, rejections),
        )

    # -- the position channel ---------------------------------------------------------

    def _position_channel(self, samples: Sequence[Sample]) -> dict[float, RejectedFix]:
        """Fixes the geometry rules out, keyed by timestamp.

        Greedy and forward: every comparison is against the last fix that was *accepted*,
        never merely the previous one, so a single bad fix cannot drag the reference along
        with it and convict the good fix that follows.
        """
        fixes = _project(samples)
        if len(fixes) < 2:
            return {}

        # Out-and-backs are claimed first, because the greedy pass below would otherwise
        # reject the outbound leg as `implied_speed` and the return would never be seen.
        # Both rules would remove the same fix; only this one names what it actually was.
        rejected: dict[float, RejectedFix] = {
            fix.t: _demoted(
                fix.t, RejectionReason.JUMP_AND_RETURN, net, self.jump_net_ratio * (out + back)
            )
            for fix, out, back, net in self._out_and_back(fixes)
        }
        remaining = [fix for fix in fixes if fix.t not in rejected]
        if len(remaining) < 2:
            return rejected

        accepted: list[_Fix] = [remaining[0]]
        last_v: float | None = None

        for fix in remaining[1:]:
            previous = accepted[-1]
            dt = fix.t - previous.t
            if dt <= 0.0:  # pragma: no cover - L0 emits samples in time order
                continue

            speed = math.hypot(fix.x - previous.x, fix.y - previous.y) / dt
            if speed > self.max_implied_speed_ms:
                rejected[fix.t] = _demoted(
                    fix.t, RejectionReason.IMPLIED_SPEED, speed, self.max_implied_speed_ms
                )
                continue

            if last_v is not None:
                accel = abs(speed - last_v) / dt
                if accel > self.max_implied_accel_ms2:
                    rejected[fix.t] = _demoted(
                        fix.t,
                        RejectionReason.IMPLIED_ACCELERATION,
                        accel,
                        self.max_implied_accel_ms2,
                    )
                    continue

            accepted.append(fix)
            last_v = speed

        return rejected

    def _out_and_back(self, fixes: Sequence[_Fix]) -> list[tuple[_Fix, float, float, float]]:
        """Fixes that left and came back, having travelled nowhere.

        The signature of a GPS reacquisition: the receiver locks onto a bad solution for a
        second and then recovers, so the track sprints out and sprints back. ``jump_min_m``
        is what separates that from the metre-scale wander of a stationary surfer -- at 3 m
        per-fix noise a 10 m leg is an ordinary draw, which is why the floor sits well above it.
        """
        found: list[tuple[_Fix, float, float, float]] = []
        for before, fix, after in zip(fixes, fixes[1:], fixes[2:], strict=False):
            if after.t - before.t > self.jump_window_s:
                continue
            out = math.hypot(fix.x - before.x, fix.y - before.y)
            back = math.hypot(after.x - fix.x, after.y - fix.y)
            if out < self.jump_min_m or back < self.jump_min_m:
                continue
            net = math.hypot(after.x - before.x, after.y - before.y)
            if net < self.jump_net_ratio * (out + back):
                found.append((fix, out, back, net))
        return found

    # -- the speed channel ------------------------------------------------------------

    def _speed_channel(
        self, samples: Sequence[Sample], demoted: dict[float, RejectedFix]
    ) -> dict[float, RejectedFix]:
        """Speed readings that something else on the device contradicts.

        Only reads the samples the position channel left alone -- a demoted fix has already
        lost its speed, and convicting it twice would double-count the same second.
        """
        odometer = _odometer_rates(samples)
        surviving = [s for s in samples if s.t not in demoted]
        bracket = _project(surviving)
        by_time = {fix.t: i for i, fix in enumerate(bracket)}

        rejected: dict[float, RejectedFix] = {}
        for sample in surviving:
            speed = sample.speed_ms
            if speed is None:
                continue
            if speed > self.max_recorded_speed_ms:
                rejected[sample.t] = _speed_dropped(
                    sample.t, RejectionReason.SPEED_IMPOSSIBLE, speed, self.max_recorded_speed_ms
                )
                continue
            if speed < self.min_checkable_speed_ms:
                continue

            floor = self.speed_agreement_ratio * speed
            rate = odometer.get(sample.t)
            if rate is not None:
                if rate < floor:
                    rejected[sample.t] = _speed_dropped(
                        sample.t, RejectionReason.SPEED_VS_ODOMETER, rate, floor
                    )
                continue

            implied = self._bracketed_speed(bracket, by_time.get(sample.t))
            if implied is not None and implied < floor:
                rejected[sample.t] = _speed_dropped(
                    sample.t, RejectionReason.SPEED_VS_POSITION, implied, floor
                )
        return rejected

    def _bracketed_speed(self, fixes: Sequence[_Fix], index: int | None) -> float | None:
        """Average speed the fixes either side of this one allow, or None if they cannot say.

        The fallback for a recording with no odometer. None is a real answer and the common
        one: where the fixes either side are a minute away, the positions cannot contradict
        a single second and this stage does not pretend otherwise.
        """
        if index is None or index == 0 or index + 1 >= len(fixes):
            return None
        before, after = fixes[index - 1], fixes[index + 1]
        span = after.t - before.t
        if span <= 0.0 or span > self.speed_bracket_s:
            return None
        return math.hypot(after.x - before.x, after.y - before.y) / span

    # -- payload ----------------------------------------------------------------------

    def encode(self, output: CleanedSession) -> bytes:
        """Serialise the cleaned session, with its report as file metadata.

        The sample columns are written by L0's own encoder rather than a second one here.
        That keeps one serialisation of a session in the codebase -- including the invariant
        that an absent value round-trips as null and never as 0.0 -- and means this stage
        cannot drift from the shape the ingest cache already holds.
        """
        table = pq.read_table(pa.BufferReader(l0.encode_activity(output.activity)))
        metadata = dict(table.schema.metadata or {})
        metadata[_REPORT_KEY] = output.report.model_dump_json().encode("utf-8")
        sink = pa.BufferOutputStream()
        pq.write_table(table.replace_schema_metadata(metadata), sink, compression="zstd")
        return bytes(sink.getvalue().to_pybytes())

    def decode(self, payload: bytes) -> CleanedSession:
        """Rebuild the cleaned session ``encode`` wrote, report included."""
        table = pq.read_table(pa.BufferReader(payload))
        raw = (table.schema.metadata or {}).get(_REPORT_KEY)
        if raw is None:
            msg = f"{NAME} payload carries no clean report: it was not written by this stage"
            raise PayloadError(msg)
        return CleanedSession(
            activity=l0.decode_activity(payload),
            report=CleanReport.model_validate_json(raw),
        )


# -- helpers --------------------------------------------------------------------------


def _project(samples: Sequence[Sample]) -> list[_Fix]:
    """Positioned samples in the session's local metric frame.

    Differencing degrees would weight a metre of latitude differently from a metre of
    longitude, so every geometric rule here works in metres (:mod:`surf.geo`).
    """
    positioned = [s for s in samples if s.has_position]
    if not positioned:
        return []
    origin = positioned[0]
    frame = LocalFrame(lat0=origin.lat or 0.0, lon0=origin.lon or 0.0)
    fixes: list[_Fix] = []
    for sample in positioned:
        x, y = frame.to_metres(sample.lat or 0.0, sample.lon or 0.0)
        fixes.append(_Fix(t=sample.t, x=x, y=y))
    return fixes


def _odometer_rates(samples: Sequence[Sample]) -> dict[float, float]:
    """Metres per second from the device's own distance counter, per sample.

    The strongest corroboration available: on the reference session ``distance_m`` is
    present for every one of the 3790 samples, so it survives the blind half that the
    positions do not. Speed and odometer are the same device measuring the same quantity
    twice, which is why a disagreement between them is physics rather than a threshold.
    """
    rates: dict[float, float] = {}
    for earlier, later in pairwise(samples):
        dt = later.t - earlier.t
        if dt <= 0.0 or earlier.distance_m is None or later.distance_m is None:
            continue
        rates[later.t] = (later.distance_m - earlier.distance_m) / dt
    return rates


def _demoted(t: float, reason: RejectionReason, value: float, limit: float) -> RejectedFix:
    """A rejection that takes the position with it."""
    return RejectedFix(
        t=t, reason=reason, effect=RejectionEffect.DEMOTED_TO_BLIND, value=value, limit=limit
    )


def _speed_dropped(t: float, reason: RejectionReason, value: float, limit: float) -> RejectedFix:
    """A rejection that leaves the position standing."""
    return RejectedFix(
        t=t, reason=reason, effect=RejectionEffect.SPEED_DROPPED, value=value, limit=limit
    )


def _demote(sample: Sample) -> Sample:
    """Turn a refused fix into a blind second, which is what it always was."""
    return sample.model_copy(update={"lat": None, "lon": None, "speed_ms": None, "confidence": 0.0})


def _drop_speed(sample: Sample) -> Sample:
    """Clear a contradicted speed reading, leaving the position it came with intact."""
    return sample.model_copy(update={"speed_ms": None})


def _rewindow(activity: Activity, cleaned: Sequence[Sample]) -> list[BlindWindow]:
    """Redraw the blind windows so coverage tells the truth about what we now believe.

    Only the ``NO_FIX`` windows are re-derived. A ``MISSING_RECORD`` window says a record
    was never written, and this stage never removes a record -- so re-deriving those would
    be recomputing a fact that cannot have changed, under a gap tolerance this stage would
    have had to guess at.
    """
    windows = [w for w in activity.blind_windows if w.cause is BlindCause.MISSING_RECORD]
    windows += blind_from_missing_positions(cleaned)
    windows.sort(key=lambda window: window.t_start)
    return windows


def _report(
    enabled: bool,
    before: Sequence[Sample],
    after: Sequence[Sample],
    rejections: list[RejectedFix],
) -> CleanReport:
    """Count what went in against what came out, so nobody has to take the rules on trust."""
    return CleanReport(
        enabled=enabled,
        sample_count=len(before),
        fixes_before=sum(1 for s in before if s.has_position),
        fixes_after=sum(1 for s in after if s.has_position),
        speeds_before=sum(1 for s in before if s.speed_ms is not None),
        speeds_after=sum(1 for s in after if s.speed_ms is not None),
        rejections=rejections,
    )
