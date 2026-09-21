"""L5 -- classify: the stage that commits to a number.

Everything upstream of here refuses to judge. L3 proposes generously, L4 measures. This is
where the pipeline stops handing ambiguity forward and answers the question the product is
actually asked: **how many waves**.

That is a deliberate division of labour, not a technicality. A screen that renders "22
proposals, 2 of them entirely blind, none scored" has pushed the pipeline's work onto the
reader. One number, reached here, with the reasoning kept and inspectable, is the product.

**The ladder** (ADR-0005). A deterministic rule goes first and settles everything it can.
What it cannot settle falls into an ambiguous band, and *only* that band is offered to a
model. A candidate nobody settles is `UNRESOLVED` and is **not** counted -- an unsure rule
with no adjudicator is not a yes.

**The rule is meant to be argued with.** It is a handful of named thresholds over L4's
features, each with a reason it emits in words. That is worth more here than accuracy alone:
there are no labels to calibrate against (ADR-0013), so a rule whose mistakes are legible is
the only kind whose mistakes can be found.

**Boundaries are never touched.** No tier may move `t_start` or `t_end`. ADR-0016 measured
this model's verdicts as reproducible across identical temperature-0 runs and its span edges
as not, so the edges stay with the deterministic stage that produced them and the
content-addressed guarantee in `architecture.md` section 3 holds.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from surf.models import DecidedBy, SessionVerdict, WaveCandidate, WaveVerdict
from surf.pipeline.l4 import FeatureSet
from surf.pipeline.stage import StageMeta

NAME = "L5"
"""Classification is stage L5."""

CODE_VERSION = "1"
"""Bump when the rule changes its mind about anything, so cached verdicts are not reused."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class Judgement:
    """One adjudicator's answer about one candidate. A verdict, never a boundary."""

    is_wave: bool
    reason: str = ""


@runtime_checkable
class Adjudicator(Protocol):
    """Something that settles candidates the rule could not.

    ``identity`` goes into the stage's cache key, so a different model or a different prompt
    produces different cached verdicts rather than silently reusing the last one's.
    """

    @property
    def identity(self) -> dict[str, Any]:
        """Model, prompt version and anything else that changes the answer."""
        ...

    def judge(self, candidates: Sequence[WaveCandidate]) -> list[Judgement]:
        """One judgement per candidate, in the order given."""
        ...


def _ramp(value: float, low: float, high: float) -> float:
    """0 at or below ``low``, 1 at or above ``high``, linear between."""
    if high <= low:
        return 0.0
    return min(1.0, max(0.0, (value - low) / (high - low)))


@dataclass
class _Ruling:
    """A strength under construction, and the reasons that moved it."""

    strength: float
    reasons: list[str] = field(default_factory=list)

    def note(self, reason: str) -> None:
        self.reasons.append(reason)

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)


@dataclass(frozen=True)
class ClassifyStage:
    """L5: settle every proposal, and say how each one was settled."""

    paddle_ceiling_ms: float = 2.5
    """At or under this, the candidate never exceeded paddling pace.

    Paddling is a physical fact rather than a session-relative one -- roughly 1.0-1.5 m/s
    prone, and the synthetic generator integrates 1.0 -- so unlike L3's threshold this one
    is absolute. The reference session's slow proposals top out at 1.3-2.6 m/s and its
    plausible rides at 6.2-9.2, so the gap this sits in is wide and empty.
    """
    ride_floor_ms: float = 4.0
    """At or over this, the candidate moved at a speed paddling does not reach."""
    takeoff_floor_ms2: float = 0.5
    """Shoreward acceleration at the onset that says a wave picked the surfer up."""
    hr_drop_bpm: float = 4.0
    """A fall in heart rate after the candidate: the rest that follows a ride, not paddling."""
    latched_variance: float = 0.05
    """Speed variance at or under this, over a long enough run, is a stale latched reading
    rather than a measurement -- the trap `prompts/wave_adjudicator` has always warned of."""
    latched_min_s: float = 8.0
    """How long a run has to be before flat speed is suspicious rather than merely short."""
    frozen_fraction: float = 0.5
    """Fraction of a candidate's seconds that may be frozen-blind before it is refused.

    The strongest signal in the set and the reason L4 computes it: the watch's own odometer
    recorded no movement at all. On the reference session 59 of 127 blind runs sit here --
    the surfer waiting for a set -- and four of the 22 proposals are mostly made of them.
    """
    band: tuple[float, float] = (0.15, 0.85)
    """The ambiguous band, and the only thing a model is ever shown (ADR-0005)."""
    adjudicator: Adjudicator | None = None
    """Who to ask inside the band. None means the band goes unresolved, which is honest."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity. The adjudicator is in the key: a different model, a different answer."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "paddle_ceiling_ms": self.paddle_ceiling_ms,
                "ride_floor_ms": self.ride_floor_ms,
                "takeoff_floor_ms2": self.takeoff_floor_ms2,
                "hr_drop_bpm": self.hr_drop_bpm,
                "latched_variance": self.latched_variance,
                "latched_min_s": self.latched_min_s,
                "frozen_fraction": self.frozen_fraction,
                "band": list(self.band),
                "adjudicator": self.adjudicator.identity if self.adjudicator else {},
            },
        )

    def run(self, data: FeatureSet) -> SessionVerdict:
        """Settle every candidate: rule first, model only inside the band."""
        low, high = self.band
        rulings = [self._rule(c) for c in data.candidates]

        undecided = [
            candidate
            for candidate, ruling in zip(data.candidates, rulings, strict=True)
            if low < ruling.strength < high
        ]
        judged = self._adjudicate(undecided)

        verdicts: list[WaveVerdict] = []
        for candidate, ruling in zip(data.candidates, rulings, strict=True):
            verdicts.append(self._verdict(candidate, ruling, judged))

        return SessionVerdict(
            verdicts=verdicts,
            adjudicated=sum(1 for v in verdicts if v.decided_by is DecidedBy.MODEL),
            model=str(self.adjudicator.identity.get("model", "")) if self.adjudicator else "",
            prompt_version=(
                str(self.adjudicator.identity.get("prompt_version", "")) if self.adjudicator else ""
            ),
        )

    def _adjudicate(
        self, undecided: Sequence[WaveCandidate]
    ) -> dict[tuple[float, float], Judgement]:
        """Ask the model about the band, keyed by the boundaries it was never allowed to move."""
        if self.adjudicator is None or not undecided:
            return {}
        judgements = self.adjudicator.judge(undecided)
        return {(c.t_start, c.t_end): j for c, j in zip(undecided, judgements, strict=True)}

    def _verdict(
        self,
        candidate: WaveCandidate,
        ruling: _Ruling,
        judged: dict[tuple[float, float], Judgement],
    ) -> WaveVerdict:
        """Turn a strength into an answer, naming the tier that reached it."""
        low, high = self.band
        strength = ruling.strength

        if strength >= high:
            decided_by, is_wave, reason = DecidedBy.RULE, True, ruling.reason
        elif strength <= low:
            decided_by, is_wave, reason = DecidedBy.RULE, False, ruling.reason
        elif (judgement := judged.get((candidate.t_start, candidate.t_end))) is not None:
            decided_by, is_wave = DecidedBy.MODEL, judgement.is_wave
            reason = (
                f"{ruling.reason}; model: {judgement.reason}"
                if ruling.reason
                else (f"model: {judgement.reason}")
            )
        else:
            decided_by, is_wave = DecidedBy.UNRESOLVED, False
            reason = f"{ruling.reason}; no adjudicator, so not counted"

        return WaveVerdict(
            t_start=candidate.t_start,
            t_end=candidate.t_end,
            is_wave=is_wave,
            strength=strength,
            decided_by=decided_by,
            reason=reason,
            position_coverage=candidate.position_coverage,
        )

    def _rule(self, candidate: WaveCandidate) -> _Ruling:
        """The deterministic tier, in the order a person would apply it."""
        f = candidate.features
        duration = candidate.duration_s

        frozen = f.get("frozen_blind_s", 0.0)
        if duration > 0.0 and frozen >= self.frozen_fraction * duration:
            return _Ruling(
                strength=0.02,
                reasons=[
                    f"the odometer recorded no movement through {frozen:.0f} of {duration:.0f} s"
                ],
            )

        speed, source = self._claimable_speed(f)
        if speed is None:
            return _Ruling(strength=0.5, reasons=["no speed this candidate can claim"])

        ruling = _Ruling(
            strength=0.05 + 0.85 * _ramp(speed, self.paddle_ceiling_ms, self.ride_floor_ms)
        )
        ruling.note(f"{source} {speed:.1f} m/s")

        if f.get("takeoff_accel_ms2", 0.0) >= self.takeoff_floor_ms2:
            ruling.strength += 0.08
            ruling.note("accelerated shoreward at the onset")

        if f.get("hr_delta_after_bpm", 0.0) <= -self.hr_drop_bpm:
            ruling.strength += 0.08
            ruling.note("heart rate fell afterwards")

        variance = f.get("measured_speed_variance")
        if (
            variance is not None
            and variance <= self.latched_variance
            and duration >= self.latched_min_s
        ):
            ruling.strength -= 0.25
            ruling.note("speed barely varied, which reads as a latched value")

        ruling.strength = min(1.0, max(0.0, ruling.strength))
        return ruling

    def _claimable_speed(self, features: dict[str, float]) -> tuple[float | None, str]:
        """The fastest speed this candidate is entitled to claim, and where it came from.

        Measured seconds first: a speed the watch actually saw beats one inferred from a
        distance total. Failing that, the blind run's **average** -- never a back-fill step
        read as one second, which L4 is built to make impossible.
        """
        if (measured := features.get("measured_speed_max_ms")) is not None:
            return measured, "measured top speed"
        if (blind := features.get("blind_run_mean_ms")) is not None:
            return blind, "odometer average across the blind stretch"
        return None, ""

    def encode(self, output: SessionVerdict) -> bytes:
        """JSON, not Parquet: a verdict set is tens of rows and carries prose."""
        return output.model_dump_json().encode("utf-8")

    def decode(self, payload: bytes) -> SessionVerdict:
        """Rebuild the verdict ``encode`` wrote."""
        try:
            return SessionVerdict.model_validate_json(payload)
        except ValueError as exc:
            msg = f"{NAME} payload is not a SessionVerdict: it was not written by this stage"
            raise PayloadError(msg) from exc
