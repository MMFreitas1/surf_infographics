"""Does a local model beat the deterministic rule at deciding what is a wave?

ADR-0005 is the rule this file enforces: a model ships only if it measurably beats the tier
below it, and unmeasured models do not ship. The tier below it here is L5's deterministic
rule, which settles a candidate from named thresholds in microseconds and says why in words.

ADR-0016 ran this experiment once already, on the session audit, and the model lost badly --
0.07 against the baseline's 0.63, while destroying 181 seconds of real surfing. That ADR
closed by scoping itself: it ruled the model out of *adjudication there*, not out of the
product. This is the other place, measured the same way, so the answer is evidence rather
than inheritance.

**Both contenders read the identical features** -- L4's coordinate-free rows -- so this
compares two readers of one piece of evidence, not two pipelines that might differ somewhere
nobody looked. And the model is only ever shown the ambiguous band, because that is the
scope ADR-0005 gives it; handing it the confident candidates too would measure something the
product would never run.

Four numbers decide it:

* **F1 on ride intervals**, IoU-matched through `surf.evaluation` -- the same path every
  other detection number in this project takes.
* **Wave count error**, because the count *is* the product. A detector can hold its F1 while
  the number on the screen drifts.
* **Real rides refused.** The asymmetric cost, as ride-seconds-destroyed was for the audit:
  a missed wave is a wave that never happened as far as the user can tell, and nothing
  downstream can recover it.
* **Reproducibility.** Run twice, byte for byte. ADR-0016 found the verdicts stable and the
  span edges not; this design removes edges from the model's reach, and this is the test
  that proves it worked rather than assuming it did.

The baseline half runs offline, always, in CI. The model half needs Ollama and is skipped
unless `SURF_LLM_EVAL=1` -- CI has no model and never will (ADR-0007).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from surf.evaluation import Interval, score
from surf.llm.adjudicate import PROMPT_VERSION, REASONED, RULED, ModelAdjudicator, ModelError
from surf.pipeline.clean import CleanStage
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FrameStage
from surf.pipeline.l3 import CandidateStage
from surf.pipeline.l4 import FeatureInput, FeatureSet, FeatureStage
from surf.pipeline.l5 import ClassifyStage
from surf.synthetic import SyntheticParams, SyntheticSession, make_synthetic_session

SEEDS = (7, 11, 23, 42, 101)
"""Five sessions, so a verdict rests on more than one lucky draw."""

MIN_IOU = 0.3
"""Same threshold every other detection number here uses: a span overlapping the truth by a
third has found the right ride, even if it disagrees about the edges."""

SHIPS: list[str] = []
"""Which model variants have earned their place, per ADR-0017. Currently none.

A list rather than a bare assertion, so this file states the *decision* instead of merely
failing. When a contender clears every bar this test goes red and names what changed, which
is the moment to re-measure and rewrite the ADR -- rather than a model quietly shipping
because somebody edited a threshold.
"""

LIVE = os.environ.get("SURF_LLM_EVAL") == "1"
needs_model = pytest.mark.skipif(not LIVE, reason="needs Ollama; set SURF_LLM_EVAL=1")


@dataclass(frozen=True)
class Contender:
    """One reader of the features, and what it decided."""

    name: str
    waves: list[Interval]
    count: int
    elapsed_s: float


@dataclass(frozen=True)
class Case:
    """One session, its L4 features, and the ride truth both contenders are scored against."""

    session: SyntheticSession
    features: FeatureSet

    @property
    def truth(self) -> list[Interval]:
        return list(self.session.truth)


def build_case(seed: int) -> Case:
    """A session taken all the way to L4, the last point before anyone judges anything.

    The odometer is switched on deliberately. It is the channel that survives a blind window
    and the whole reason L4 can say anything about a candidate the smoother had to estimate;
    a case built without it would measure the contenders on a signal the real file has and
    the fixture does not.
    """
    session = make_synthetic_session(SyntheticParams(seed=seed, odometer=True))
    cleaned = CleanStage().run(session.activity).activity
    framed = FrameStage().run(KinematicsStage().run(cleaned))
    candidates = CandidateStage().run(framed)
    features = FeatureStage().run(
        FeatureInput(candidates=candidates, framed=framed.samples, samples=cleaned.samples)
    )
    return Case(session=session, features=features)


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return [build_case(seed) for seed in SEEDS]


def run_stage(case: Case, name: str, stage: ClassifyStage) -> Contender:
    """Score one contender on one session."""
    started = time.monotonic()
    verdict = stage.run(case.features)
    return Contender(
        name=name,
        waves=[Interval(v.t_start, v.t_end) for v in verdict.verdicts if v.is_wave],
        count=verdict.wave_count,
        elapsed_s=time.monotonic() - started,
    )


def baseline_of(case: Case) -> Contender:
    """The deterministic rule alone, forced to settle everything it is given."""
    return run_stage(case, "baseline", ClassifyStage())


def model_of(case: Case, variant: str) -> Contender:
    """The rule, with the model asked about the band it could not settle."""
    return run_stage(
        case, f"llm:{variant}", ClassifyStage(adjudicator=ModelAdjudicator(variant=variant))
    )


def rides_refused(waves: list[Interval], truths: list[Interval]) -> int:
    """Real rides no accepted verdict overlaps.

    The asymmetric cost. A wave the pipeline refuses is one the user never hears about, and
    unlike a stray false positive there is nothing downstream that can recover it.
    """
    return sum(
        1
        for truth in truths
        if not any(min(truth.t_end, w.t_end) - max(truth.t_start, w.t_start) > 0 for w in waves)
    )


def report(case_list: list[Case], contenders: list[list[Contender]]) -> dict[str, dict]:
    """Aggregate one contender's numbers across every session."""
    summary: dict[str, dict] = {}
    for column in zip(*contenders, strict=True):
        name = column[0].name
        f1s, count_errors, refused, elapsed = [], [], 0, 0.0
        for case, contender in zip(case_list, column, strict=True):
            f1s.append(score(contender.waves, case.truth, min_iou=MIN_IOU).f1)
            count_errors.append(abs(contender.count - len(case.truth)))
            refused += rides_refused(contender.waves, case.truth)
            elapsed += contender.elapsed_s
        summary[name] = {
            "f1": sum(f1s) / len(f1s),
            "count_error": sum(count_errors) / len(count_errors),
            "rides_refused": refused,
            "elapsed_s": elapsed,
        }
    return summary


RESULTS_PATH = Path(__file__).parent / "results" / "wave_adjudication.json"
"""Where the verdict is written, so it survives a failing assertion.

The numbers *are* the deliverable here, and a measurement that evaporates when an assertion
fails is no measurement at all -- the lesson `llm_audit.json` is kept for.
"""


def qualifies(row: dict, baseline: dict) -> bool:
    """Whether a contender has earned its place, per ADR-0005.

    Two bars, and both are required. Beating the baseline on F1 is the stated rule; refusing
    no more real rides than the baseline is the one the F1 alone would let you miss, because
    a contender can trade recall for precision and still look like it improved.
    """
    return row["f1"] > baseline["f1"] and row["rides_refused"] <= baseline["rides_refused"]


CONTROLS = frozenset({f"llm:{RULED}"})
"""Contenders that are diagnostic instruments and cannot ship, however they score.

`ruled` is handed the decision rule outright, so a good score from it means the model can
pattern-match a rule the baseline already executes perfectly, in microseconds instead of
nineteen seconds. Shipping it would be shipping a slower, remoter copy of the incumbent.

Declared here rather than decided after the numbers arrived: `prompts/wave_adjudicator.v2.md`
has called this variant "a control, not a candidate" since before it was first run, and
ADR-0016 says the same of its own. It is also the conservative direction -- excluding it can
only stop something shipping, never start it.
"""


def qualifying(summary: dict[str, dict]) -> list[str]:
    """Every contender that clears both bars. The baseline is the incumbent, not a rival."""
    baseline = summary["baseline"]
    return [
        name
        for name, row in summary.items()
        if name != "baseline" and name not in CONTROLS and qualifies(row, baseline)
    ]


def table_of(summary: dict[str, dict]) -> str:
    """The comparison as a block of text a person can read."""
    lines = [f"{'contender':<16} {'F1':>6} {'count err':>10} {'refused':>8} {'seconds':>8}"]
    for name, row in summary.items():
        lines.append(
            f"{name:<16} {row['f1']:>6.2f} {row['count_error']:>10.1f} "
            f"{row['rides_refused']:>8} {row['elapsed_s']:>7.1f}s"
        )
    return "\n".join(lines)


def show(summary: dict[str, dict]) -> None:
    """Print the table. Printing is not recording -- see :func:`record`."""
    print("\n" + table_of(summary))


def record(summary: dict[str, dict]) -> None:
    """Write the verdict down. Refuses a partial measurement, for the reason ADR-0016 gives."""
    if "baseline" not in summary or len(summary) < 2:
        msg = f"refusing to record a partial measurement: {sorted(summary)}"
        raise ValueError(msg)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "seeds": list(SEEDS),
                "min_iou": MIN_IOU,
                "table": table_of(summary),
                "summary": summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# -- the rule, measured offline ----------------------------------------------------------


def test_the_rule_finds_the_rides(cases):
    """The incumbent has to be worth beating, or the comparison means nothing."""
    summary = report(cases, [[baseline_of(case)] for case in cases])
    show(summary)

    assert summary["baseline"]["f1"] > 0.5


def test_the_rule_commits_to_a_count_on_every_session(cases):
    """The product's requirement, not the detector's: one integer, always."""
    for case in cases:
        verdict = ClassifyStage().run(case.features)
        assert isinstance(verdict.wave_count, int)
        assert verdict.proposed_count == len(case.features.candidates)


def test_the_rule_leaves_nothing_unresolved_it_could_have_settled(cases):
    """Whatever the band costs, it must be a minority of the session, or the rule is not one."""
    for case in cases:
        verdict = ClassifyStage().run(case.features)
        if verdict.proposed_count:
            assert verdict.unresolved_count <= verdict.proposed_count / 2


def test_the_rule_is_reproducible(cases):
    """The bar ADR-0016 earned, applied to the tier that does not need a model to fail it."""
    stage = ClassifyStage()
    for case in cases:
        assert stage.encode(stage.run(case.features)) == stage.encode(stage.run(case.features))


def test_an_unresolved_candidate_is_never_counted_as_a_wave(cases):
    """An unsure rule with nobody to ask is not a yes."""
    for case in cases:
        for verdict in ClassifyStage().run(case.features).verdicts:
            if verdict.decided_by.value == "unresolved":
                assert verdict.is_wave is False


# -- the model, measured only when one is available --------------------------------------


@pytest.fixture(scope="module")
def measurement(cases) -> dict[str, dict]:
    """Every contender on every session. Eighteen minutes of local inference; run it once."""
    if not LIVE:
        pytest.skip("needs Ollama; set SURF_LLM_EVAL=1")
    try:
        rows = [
            [baseline_of(case), model_of(case, REASONED), model_of(case, RULED)] for case in cases
        ]
    except ModelError as exc:
        pytest.skip(f"model unavailable: {exc}")
    summary = report(cases, rows)
    show(summary)
    record(summary)
    return summary


@needs_model
def test_the_model_returns_something_usable(cases):
    """Before comparing anything: does it answer the question that was asked?"""
    case = cases[0]
    band = [
        candidate
        for candidate, verdict in zip(
            case.features.candidates, ClassifyStage().run(case.features).verdicts, strict=True
        )
        if verdict.decided_by.value == "unresolved"
    ]
    if not band:
        pytest.skip("this session left nothing in the band")

    judgements = ModelAdjudicator().judge(band)
    assert len(judgements) == len(band), "one judgement per candidate, in order"


@needs_model
def test_the_model_never_moves_a_boundary(cases):
    """The design ADR-0016 forced. If this ever fails, the stage is not content-addressable."""
    case = cases[0]
    plain = ClassifyStage().run(case.features)
    judged = ClassifyStage(adjudicator=ModelAdjudicator()).run(case.features)

    assert [(v.t_start, v.t_end) for v in plain.verdicts] == [
        (v.t_start, v.t_end) for v in judged.verdicts
    ]


@needs_model
def test_the_model_is_reproducible(cases):
    """ADR-0016 found verdicts stable and span edges not. Verdicts are all this returns."""
    stage = ClassifyStage(adjudicator=ModelAdjudicator())
    case = cases[0]

    assert stage.encode(stage.run(case.features)) == stage.encode(stage.run(case.features)), (
        "identical runs disagreed, so this stage cannot be content-addressed (architecture.md §3)"
    )


@needs_model
def test_the_model_is_measured_against_the_rule(measurement):
    """The decision, encoded. ADR-0017 records whatever this says.

    A contender must beat the rule on F1 *and* refuse no more real rides, because shipping
    something that loses waves would be a defect whatever its F1 said.
    """
    baseline = measurement["baseline"]
    for name, row in measurement.items():
        if name == "baseline":
            continue
        print(
            f"\n{name}: F1 {row['f1']:.2f} vs {baseline['f1']:.2f} · "
            f"count error {row['count_error']:.1f} vs {baseline['count_error']:.1f} · "
            f"rides refused {row['rides_refused']} vs {baseline['rides_refused']}"
        )

    qualified = qualifying(measurement)
    assert qualified == SHIPS, (
        f"the shipping decision has changed: {qualified or 'nothing'} qualifies, "
        f"ADR-0017 says {SHIPS or 'nothing'} does. Re-measure and rewrite the ADR."
    )
