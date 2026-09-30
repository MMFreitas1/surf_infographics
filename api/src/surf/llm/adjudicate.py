"""Asking a local model about the candidates the rule could not settle.

An :class:`~surf.pipeline.l5.Adjudicator`, so it plugs into L5's ladder and nothing else
about the pipeline changes when it is absent. It is absent by default: ADR-0005 says a model
ships only if it measurably beats the tier below it, and ADR-0016 records what happened the
last time that was tested here -- the same model lost to a deterministic rule 0.07 to 0.63 on
the session audit, and destroyed 181 seconds of real surfing doing it.

So this exists to be **measured** (`evals/test_wave_adjudication.py`), and it ships only if
the measurement says to. ADR-0017 records the answer either way.

Two things are deliberately narrow, both earned from ADR-0016:

**It returns verdicts, never boundaries.** That ADR ran the same measurement twice at
temperature 0 with a fixed seed: the verdicts came back identical and the *span edges* moved.
A stage whose output shifts between identical runs cannot be content-addressed
(`architecture.md` section 3), so the model is never shown an interval it could adjust. It
answers yes or no about intervals L3 fixed.

**It sees no coordinates.** Every field in the payload is a duration, a rate, a fraction or a
count -- the same discipline ADR-0015 put on the audit digest. That is what would make a
hosted fallback safe to offer rather than merely policed, and it means the model and the rule
are scored on identical evidence rather than two views that might differ in some unnoticed
way.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from surf.models import WaveCandidate
from surf.pipeline.l5 import Judgement

PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / "wave_adjudicator.v2.md"
PROMPT_VERSION = "wave_adjudicator.v2"
"""Identifies the prompt in a result. A verdict is only interpretable next to it."""

REASONED = "reasoned"
"""Variant A: the physics stated, the model asked to apply it. The candidate."""
RULED = "ruled"
"""Variant B: the rule handed over outright. A control -- a model given the rule is executing
it, not adjudicating. ADR-0016 found the control beat the candidate, which is how it became
clear the model was pattern-matching rather than reasoning."""

DEFAULT_MODEL = "qwen2.5:7b-instruct-q4_K_M"
DEFAULT_HOST = "http://127.0.0.1:11434"


class PromptError(RuntimeError):
    """The prompt file is not in the shape this module expects."""


class ModelError(RuntimeError):
    """The model did not return something this module will act on."""


class CandidateVerdict(BaseModel):
    """One answer about one candidate, addressed by index.

    No boundaries by construction: the model is never given them and there is nowhere in
    this shape to put one back.
    """

    model_config = ConfigDict(extra="forbid")

    i: int = Field(ge=0)
    is_wave: bool
    why: str = ""


class AdjudicationVerdict(BaseModel):
    """What the model must return. Anything else is a failure, not a retry.

    ``extra="forbid"`` is doing real work and is not defensive habit. Without it this model
    accepted ``{"0": false, "1": true}`` -- the shape qwen2.5 actually returned the first
    time this ran -- by ignoring both keys and defaulting ``verdicts`` to empty. Every
    candidate then came back "the model returned no answer", the measurement showed the model
    changing nothing, and the conclusion would have been that it adds nothing. It had never
    been asked a question it could answer.
    """

    model_config = ConfigDict(extra="forbid")

    verdicts: list[CandidateVerdict]


def load_prompt(variant: str, path: Path | None = None) -> str:
    """The system prompt for one variant, read from the versioned file.

    Parsed out of the markdown by heading rather than kept in a Python string, so the file a
    reviewer reads is the file the model is sent (CLAUDE.md).
    """
    source = (path or PROMPT_PATH).read_text(encoding="utf-8")
    match = re.search(
        rf"^## Variant [AB] — `{re.escape(variant)}`\s*$(.*?)^---\s*$|"
        rf"^## Variant [AB] — `{re.escape(variant)}`\s*$(.*)\Z",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        msg = f"no variant {variant!r} in {path or PROMPT_PATH}"
        raise PromptError(msg)
    body = match.group(1) or match.group(2) or ""
    system = re.search(r"^### System\s*$(.*)", body, re.MULTILINE | re.DOTALL)
    if system is None:
        msg = f"variant {variant!r} has no '### System' section"
        raise PromptError(msg)
    return system.group(1).strip()


def candidate_rows(candidates: Sequence[WaveCandidate]) -> list[dict[str, Any]]:
    """The payload, as the model sees it: rounded, coordinate-free, index-addressed.

    A feature L4 did not produce is **left out** rather than sent as zero. The prompt says so
    explicitly, because zero metres is a claim that the surfer did not move and absence is a
    statement about what the file recorded.
    """
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        f = candidate.features
        row: dict[str, Any] = {
            "i": index,
            "dur_s": round(candidate.duration_s),
            "coverage": round(candidate.position_coverage, 2),
        }
        for key, name, digits in (
            ("measured_speed_max_ms", "top_ms", 2),
            ("measured_speed_variance", "var", 2),
            ("takeoff_accel_ms2", "accel", 2),
            ("blind_run_m", "blind_m", 0),
            ("blind_run_s", "blind_s", 0),
            ("blind_run_mean_ms", "blind_ms", 2),
            ("frozen_blind_s", "frozen_s", 0),
            ("hr_mean_bpm", "hr", 0),
            ("hr_delta_after_bpm", "hr_after", 0),
        ):
            if (value := f.get(key)) is not None:
                row[name] = round(value, digits) if digits else round(value)
        rows.append(row)
    return rows


@dataclass(frozen=True)
class ModelAdjudicator:
    """L5's model tier, pointed at a local Ollama.

    Temperature 0 with a fixed seed, so a disappointing result cannot be waved away as a bad
    sample and a good one cannot be a lucky one.
    """

    variant: str = REASONED
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    seed: int = 7
    timeout_s: float = 600.0
    prompt_path: Path | None = None

    @property
    def identity(self) -> dict[str, Any]:
        """What goes into L5's cache key: change any of it and the verdicts may change."""
        return {
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
            "variant": self.variant,
            "seed": self.seed,
        }

    def judge(self, candidates: Sequence[WaveCandidate]) -> list[Judgement]:
        """One judgement per candidate, in the order given.

        A candidate the model failed to answer for is returned as ``False`` rather than
        dropped or defaulted to a wave. Silence is not a yes, and an answer that does not
        line up with the question is a failure of the model, not of the candidate.
        """
        if not candidates:
            return []

        verdict = self._ask(candidate_rows(candidates))
        answers = {v.i: v for v in verdict.verdicts}
        if not answers:
            # Silence about every candidate is a broken contract, not a set of no votes.
            # Returning all-false here is how a prompt bug disguises itself as a finding.
            msg = f"model answered none of the {len(candidates)} candidates it was given"
            raise ModelError(msg)
        return [
            Judgement(is_wave=answer.is_wave, reason=answer.why)
            if (answer := answers.get(index)) is not None
            else Judgement(is_wave=False, reason="the model returned no answer for this one")
            for index in range(len(candidates))
        ]

    def _ask(self, rows: list[dict[str, Any]]) -> AdjudicationVerdict:
        payload = {
            "model": self.model,
            "system": load_prompt(self.variant, self.prompt_path),
            "prompt": json.dumps(rows, separators=(",", ":")),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": self.seed, "num_predict": 1500},
        }
        try:
            response = httpx.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout_s)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            msg = f"could not reach the model at {self.host}: {exc}"
            raise ModelError(msg) from exc

        try:
            return AdjudicationVerdict.model_validate_json(body["response"])
        except (ValidationError, KeyError) as exc:
            msg = (
                "model returned something that is not an AdjudicationVerdict: "
                f"{body.get('response')!r}"
            )
            raise ModelError(msg) from exc
