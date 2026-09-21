"""Does a local model beat the deterministic baseline at finding what is not surfing?

ADR-0005 is the rule this file enforces: a model ships only if it measurably beats the tier
below it, and unmeasured models do not ship. The tier below it here is L0.6's baseline, which
trims the ends of a recording on a coverage threshold and answers in microseconds.

**Both contenders read the identical digest** -- the coordinate-free `SessionWindow` rows
L0.6 already produces -- so this compares two readers of one piece of evidence, not two
pipelines that might differ somewhere nobody looked.

Three numbers decide it, and the third is the one that matters most:

* **F1 on out-of-water spans**, IoU-matched through `surf.evaluation`, the same path a wave
  detection is scored by. Directly comparable to every other number this project reports.
* **Interior-interruption recall**, where the baseline scores zero by construction -- it only
  trims ends (ADR-0015). This is the whole case for a model existing here.
* **True ride seconds destroyed.** A false interruption cuts real surfing out of a session
  and leaves no trace. An F1 win bought with ride seconds is not a win, and this is the
  asymmetry that made the first cut of the baseline wrong in PR #33.

The baseline half runs offline, always, in CI. The model half needs Ollama and is skipped
unless `SURF_LLM_EVAL=1` -- CI has no model and never will (ADR-0007).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from surf.evaluation import Interval, score
from surf.llm.audit import PROMPT_VERSION, REASONED, RULED, AuditRun, ModelError, ask
from surf.models import SessionWindow
from surf.pipeline.audit import AuditStage
from surf.pipeline.clean import CleanStage
from surf.synthetic import SyntheticParams, SyntheticSession, make_synthetic_session

SEEDS = (7, 11, 23, 42, 101)
"""Five sessions, so a verdict rests on more than one lucky draw."""

MIN_IOU = 0.3
"""Same threshold the wave detector is scored at, for the same reason: a span that overlaps
the truth by a third has found the right stretch, even if it disagrees about the edges."""

SHIPS: list[str] = []
"""Which model variants have earned their place, per ADR-0016. Currently none.

A list rather than a bare assertion, so this file states the *decision* instead of merely
failing. A contender is unshippable here for two separate reasons -- it loses on F1 and it
destroys real surfing -- and either alone is disqualifying (ADR-0005). When a better model
clears both bars, this test goes red and names what changed, which is the right moment to
re-measure and rewrite the ADR rather than quietly ship.
"""

LIVE = os.environ.get("SURF_LLM_EVAL") == "1"
needs_model = pytest.mark.skipif(not LIVE, reason="needs Ollama; set SURF_LLM_EVAL=1")


@dataclass(frozen=True)
class Contender:
    """One reader of the digest, and what it found."""

    name: str
    spans: list[Interval]
    elapsed_s: float


@dataclass(frozen=True)
class Case:
    """One session, its digest, and the truth both contenders are scored against."""

    session: SyntheticSession
    windows: list[SessionWindow]
    origin: float

    @property
    def truth(self) -> list[Interval]:
        return list(self.session.out_of_water)

    @property
    def interior(self) -> list[Interval]:
        return self.session.interior_breaks

    @property
    def rides(self) -> list[Interval]:
        return list(self.session.truth)


def build_case(seed: int) -> Case:
    """A session that walks down, surfs, takes a break on the sand, surfs, and walks back.

    Every kind of out-of-water stretch in one recording, so one session exercises the case
    the baseline handles and the case it deliberately does not.
    """
    session = make_synthetic_session(
        SyntheticParams(seed=seed, break_after_wave=4, break_s=240, walk_out_s=120, idle_s=180)
    )
    cleaned = CleanStage().run(session.activity).activity
    stage = AuditStage()
    return Case(
        session=session,
        windows=stage.digest(cleaned.samples),
        origin=cleaned.samples[0].t,
    )


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return [build_case(seed) for seed in SEEDS]


def baseline_of(case: Case) -> Contender:
    """What L0.6 excludes, as intervals."""
    cleaned = CleanStage().run(case.session.activity).activity
    report = AuditStage().run(cleaned)
    return Contender(
        name="baseline",
        spans=[Interval(w.t_start, w.t_end) for w in report.not_surfing],
        elapsed_s=0.0,
    )


def model_of(case: Case, variant: str) -> Contender:
    """What the model says, or a skip when it cannot be reached."""
    try:
        run: AuditRun = ask(case.windows, origin=case.origin, variant=variant)
    except ModelError as exc:  # pragma: no cover - only on a live run
        pytest.skip(f"model unavailable: {exc}")
    return Contender(
        name=f"llm:{variant}", spans=run.verdict.intervals(case.origin), elapsed_s=run.elapsed_s
    )


def ride_seconds_destroyed(spans: list[Interval], rides: list[Interval]) -> float:
    """Seconds of genuine surfing that fall inside a proposed out-of-water span.

    The asymmetric cost. Leaving the walk home in a session skews a duration; cutting a ride
    out of one destroys the measurement the product exists to make, silently.
    """
    total = 0.0
    for ride in rides:
        for span in spans:
            overlap = min(ride.t_end, span.t_end) - max(ride.t_start, span.t_start)
            if overlap > 0:
                total += overlap
    return total


def recall_of(spans: list[Interval], truths: list[Interval]) -> float:
    """Fraction of the truths some span overlaps at all.

    Deliberately looser than the IoU match: for an interior break, finding it at all is the
    question, and the baseline's score here is zero however generously it is read.
    """
    if not truths:
        return 1.0
    found = sum(
        1
        for truth in truths
        if any(min(truth.t_end, s.t_end) - max(truth.t_start, s.t_start) > 0 for s in spans)
    )
    return found / len(truths)


def report(case_list: list[Case], contenders: list[list[Contender]]) -> dict[str, dict]:
    """Aggregate one contender's numbers across every session."""
    summary: dict[str, dict] = {}
    for column in zip(*contenders, strict=True):
        name = column[0].name
        f1s, interior, destroyed, elapsed = [], [], 0.0, 0.0
        for case, contender in zip(case_list, column, strict=True):
            f1s.append(score(contender.spans, case.truth, min_iou=MIN_IOU).f1)
            interior.append(recall_of(contender.spans, case.interior))
            destroyed += ride_seconds_destroyed(contender.spans, case.rides)
            elapsed += contender.elapsed_s
        summary[name] = {
            "f1": sum(f1s) / len(f1s),
            "interior_recall": sum(interior) / len(interior),
            "ride_seconds_destroyed": destroyed,
            "elapsed_s": elapsed,
        }
    return summary


RESULTS_PATH = Path(__file__).parent / "results" / "llm_audit.json"
"""Where the verdict is written.

Written to disk rather than only printed, because the numbers *are* the deliverable here and
a measurement that evaporates when an assertion fails is no measurement at all. A run costs
eighteen minutes of local inference; it should have to happen once.
"""


def qualifies(row: dict, baseline: dict) -> bool:
    """Whether a contender has earned its place, per ADR-0005.

    Two bars, and a contender must clear both. Beating the baseline on F1 is the stated
    rule; destroying no real surfing is the one the numbers alone would let you miss, since
    a contender can buy recall with ride seconds and still look like it improved.
    """
    return row["f1"] > baseline["f1"] and row["ride_seconds_destroyed"] == 0.0


def qualifying(summary: dict[str, dict]) -> list[str]:
    """Every contender that clears both bars. The baseline is the incumbent, not a rival."""
    baseline = summary["baseline"]
    return [n for n, row in summary.items() if n != "baseline" and qualifies(row, baseline)]


def table_of(summary: dict[str, dict]) -> str:
    """The comparison as a block of text a person can read."""
    lines = [f"{'contender':<16} {'F1':>6} {'interior':>9} {'rides lost':>11} {'seconds':>8}"]
    for name, row in summary.items():
        lines.append(
            f"{name:<16} {row['f1']:>6.2f} {row['interior_recall']:>9.2f} "
            f"{row['ride_seconds_destroyed']:>10.0f}s {row['elapsed_s']:>7.1f}s"
        )
    return "\n".join(lines)


def show(summary: dict[str, dict]) -> None:
    """Print the table. Printing is not recording -- see :func:`record`."""
    print("\n" + table_of(summary))


def record(summary: dict[str, dict]) -> None:
    """Write the verdict down, so it survives a failing assertion.

    Separate from :func:`show` on purpose, and only ever called by the full measurement.
    Wiring the write into the printer meant an offline run that displayed the baseline alone
    overwrote a three-contender record with a one-row one -- destroying eighteen minutes of
    measurement to print a table nobody had asked to keep.
    """
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


# -- the baseline, measured offline ---------------------------------------------------


def test_the_baseline_finds_the_boundaries(cases):
    """What the incumbent is worth, so the bar is a number rather than an impression."""
    summary = report(cases, [[baseline_of(case)] for case in cases])
    show(summary)
    assert summary["baseline"]["f1"] > 0.5


def test_the_baseline_never_destroys_a_ride(cases):
    """The property PR #33 was rebuilt around, held here as a standing guarantee."""
    for case in cases:
        assert ride_seconds_destroyed(baseline_of(case).spans, case.rides) == 0.0


def test_the_baseline_cannot_see_an_interior_break(cases):
    """Not a defect -- a deliberate limit (ADR-0015), and the entire opening for a model.

    Pinned so that if the baseline ever *does* learn to find these, this eval's premise is
    revisited rather than silently outdated.
    """
    for case in cases:
        assert case.interior, "the fixture must contain an interior break or this proves nothing"
        assert recall_of(baseline_of(case).spans, case.interior) == 0.0


# -- the model, measured live ---------------------------------------------------------


@pytest.fixture(scope="module")
def measurement(cases) -> dict[str, dict]:
    """Every contender, measured once, and written to disk.

    Module-scoped because a run costs eighteen minutes of local inference: asking the model
    the same question twice to satisfy two assertions would double that for nothing.
    """
    if not LIVE:
        pytest.skip("needs Ollama; set SURF_LLM_EVAL=1")
    rows = [[baseline_of(case), model_of(case, REASONED), model_of(case, RULED)] for case in cases]
    summary = report(cases, rows)
    show(summary)
    record(summary)
    return summary


@needs_model
@pytest.mark.llm
def test_the_model_returns_something_usable(cases):
    """Before asking whether it is right: is it even well-formed, once, without retries."""
    run = ask(cases[0].windows, origin=cases[0].origin, variant=REASONED)
    assert run.prompt_version == PROMPT_VERSION
    assert run.output_tokens > 0


@needs_model
@pytest.mark.llm
def test_the_model_is_measured_against_the_baseline(measurement):
    """The verdict. Printed, written to disk, and asserted only where ADR-0005 requires it.

    The assertion is deliberately narrow: this test does not fail because the model loses --
    losing is a legitimate outcome and the numbers are the deliverable. It fails if the model
    *destroys real surfing*, because shipping that would be a defect whatever its F1 said.
    """
    summary = measurement
    baseline = summary["baseline"]
    qualified = qualifying(summary)
    for name, row in summary.items():
        if name == "baseline":
            continue
        print(f"\n{name}: {'QUALIFIES' if name in qualified else 'does not qualify'}")
        print(
            f"   F1 {row['f1']:.2f} vs {baseline['f1']:.2f} · "
            f"interior recall {row['interior_recall']:.2f} vs "
            f"{baseline['interior_recall']:.2f} · "
            f"ride seconds destroyed {row['ride_seconds_destroyed']:.0f} vs "
            f"{baseline['ride_seconds_destroyed']:.0f}"
        )

    assert baseline["ride_seconds_destroyed"] == 0.0, (
        "the shipping contender destroyed real surfing"
    )
    assert qualified == SHIPS, (
        f"the shipping decision recorded in ADR-0016 no longer matches the measurement: "
        f"{qualified or 'nothing'} qualifies, ADR-0016 says {SHIPS or 'nothing'} does. "
        f"Re-measure, update the ADR, and only then change this list."
    )


# -- the recorded verdict, checked offline ---------------------------------------------


def test_the_recorded_measurement_still_says_what_adr_0016_says():
    """The decision rule, exercised in CI without a model.

    A measurement costs eighteen minutes of local inference, so the rule that turns numbers
    into a shipping decision would otherwise only ever run on a machine with a GPU and an
    hour to spare. The numbers from the run behind ADR-0016 are committed next to this file;
    this holds the rule to them every time CI runs.

    Editing the results file to change the verdict will not work: it has to disagree with
    `SHIPS`, and `SHIPS` is what the ADR documents.
    """
    if not RESULTS_PATH.is_file():
        pytest.skip("no recorded measurement yet")
    recorded = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    summary = recorded["summary"]

    assert summary["baseline"]["ride_seconds_destroyed"] == 0.0
    assert qualifying(summary) == SHIPS, (
        f"the recorded measurement says {qualifying(summary) or 'nothing'} qualifies, "
        f"but ADR-0016 records {SHIPS or 'nothing'}"
    )


def test_the_rule_would_notice_a_contender_that_earned_its_place():
    """Guards the guard. A rule that cannot say yes is not checking anything.

    Both halves matter and both are pinned: beating F1 alone is not enough if it cost ride
    seconds, and destroying nothing is not enough if it did not beat the baseline.
    """
    baseline = {"f1": 0.63, "ride_seconds_destroyed": 0.0}

    assert qualifies({"f1": 0.80, "ride_seconds_destroyed": 0.0}, baseline) is True
    assert qualifies({"f1": 0.80, "ride_seconds_destroyed": 1.0}, baseline) is False
    assert qualifies({"f1": 0.45, "ride_seconds_destroyed": 0.0}, baseline) is False


def test_a_partial_measurement_is_never_recorded():
    """The bug this guard exists for: a baseline-only run overwrote the real record.

    Eighteen minutes of measurement, replaced by a one-row table, because displaying a
    summary and preserving one were the same call.
    """
    with pytest.raises(ValueError, match="partial measurement"):
        record(
            {
                "baseline": {
                    "f1": 0.6,
                    "interior_recall": 0.0,
                    "ride_seconds_destroyed": 0.0,
                    "elapsed_s": 0.0,
                }
            }
        )
