"""Asking a local model which minutes of a recording were spent out of the water.

Deliberately *not* a pipeline stage. ADR-0005 says a model ships only if it measurably beats
the tier below it, and the tier below it here is L0.6's deterministic baseline, which already
answers this question in microseconds. So this module exists to be **measured**
(`evals/test_llm_audit.py`), and the stage gets built only if the measurement says to.

What it sends is the same coordinate-free :class:`~surf.models.SessionWindow` digest the
baseline reads -- rates, fractions and counts, no position anywhere (ADR-0015). That is what
would make a hosted fallback safe to offer rather than merely policed, and it means both
contenders are scored on identical evidence rather than on two views that might differ in
some way nobody noticed.

The prompts live in ``prompts/session_audit.v1.md`` and are read from it at call time rather
than duplicated here. A prompt is a versioned artefact in this project (CLAUDE.md); copying
one into code is how the file on disk and the string actually sent drift apart.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from surf.evaluation import Interval
from surf.models import SessionWindow

PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / "session_audit.v1.md"
PROMPT_VERSION = "session_audit.v1"
"""Identifies the prompt in a result. A model's answer is only interpretable next to it."""

REASONED = "reasoned"
"""Variant A: the physics stated, the model asked to apply it."""
RULED = "ruled"
"""Variant B: the decision rule stated outright. A control, not a candidate -- a model
handed the rule is executing it, not adjudicating anything."""


class PromptError(RuntimeError):
    """The prompt file is not in the shape this module expects."""


class ModelError(RuntimeError):
    """The model did not return something this module will act on."""


class OutOfWaterSpan(BaseModel):
    """One stretch the model says was recorded on dry land."""

    from_min: float = Field(ge=0.0)
    to_min: float = Field(ge=0.0)
    why: str = ""


class AuditVerdict(BaseModel):
    """What the model returned, once. Invalid output is a failure, not a retry.

    Retrying until something parses would turn a model that cannot do the task into one
    that appears to, which is precisely the reading the eval exists to prevent.
    """

    out_of_water: list[OutOfWaterSpan] = Field(default_factory=list)

    def intervals(self, origin: float) -> list[Interval]:
        """The spans as absolute-time intervals, ready for :mod:`surf.evaluation`.

        Reversed and zero-length spans are dropped rather than repaired. A model that
        cannot order two numbers is telling us something, and quietly sorting them would
        hide it from the measurement.
        """
        out: list[Interval] = []
        for span in self.out_of_water:
            start = origin + span.from_min * 60.0
            end = origin + span.to_min * 60.0
            if end > start:
                out.append(Interval(start, end))
        return out


@dataclass(frozen=True)
class AuditRun:
    """One call to the model: what it said, and what it cost."""

    verdict: AuditVerdict
    variant: str
    prompt_version: str
    model: str
    elapsed_s: float
    prompt_tokens: int
    output_tokens: int


def load_prompt(variant: str, path: Path | None = None) -> str:
    """The system prompt for one variant, read from the versioned file.

    Parsed out of the markdown by heading rather than kept in a Python string, so the file
    a reviewer reads is the file the model is sent.
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


def digest_rows(windows: Sequence[SessionWindow], origin: float) -> list[dict[str, Any]]:
    """The digest as the model sees it: minutes, rounded, and free of any location.

    Minutes rather than unix seconds because a 10-digit timestamp costs tokens and invites
    arithmetic errors, and because the answer is only ever wanted to the nearest window.
    """
    rows: list[dict[str, Any]] = []
    for index, window in enumerate(windows):
        rows.append(
            {
                "i": index,
                "min": round((window.t_start - origin) / 60.0, 1),
                "coverage": round(window.coverage, 2),
                "speed_mean": round(window.speed_mean_ms or 0.0, 2),
                "speed_max": round(window.speed_max_ms or 0.0, 2),
                "hr": round(window.hr_mean_bpm or 0.0),
            }
        )
    return rows


def ask(
    windows: Sequence[SessionWindow],
    *,
    origin: float,
    variant: str = REASONED,
    model: str = "qwen2.5:7b-instruct-q4_K_M",
    host: str = "http://127.0.0.1:11434",
    seed: int = 7,
    timeout_s: float = 600.0,
    prompt_path: Path | None = None,
) -> AuditRun:
    """Ask the model which minutes were out of the water.

    Temperature 0 and a fixed seed, so a disappointing result cannot be waved away as a bad
    sample and a good one cannot be a lucky one.
    """
    payload = {
        "model": model,
        "system": load_prompt(variant, prompt_path),
        "prompt": json.dumps(digest_rows(windows, origin), separators=(",", ":")),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "seed": seed, "num_predict": 1500},
    }
    try:
        response = httpx.post(f"{host}/api/generate", json=payload, timeout=timeout_s)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:
        msg = f"could not reach the model at {host}: {exc}"
        raise ModelError(msg) from exc

    try:
        verdict = AuditVerdict.model_validate_json(body["response"])
    except (ValidationError, KeyError) as exc:
        msg = f"model returned something that is not an AuditVerdict: {body.get('response')!r}"
        raise ModelError(msg) from exc

    return AuditRun(
        verdict=verdict,
        variant=variant,
        prompt_version=PROMPT_VERSION,
        model=model,
        elapsed_s=body.get("total_duration", 0) / 1e9,
        prompt_tokens=int(body.get("prompt_eval_count", 0)),
        output_tokens=int(body.get("eval_count", 0)),
    )
