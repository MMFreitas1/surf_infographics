# ADR-0017: The local model does not ship for wave adjudication

**Status:** accepted · 2026-09-21

## Context

The product has to answer "how many waves" with one number. Until this PR the pipeline
refused to: L3 proposes generously and judges nothing, L4 measures, and the reference session
arrived at the UI as 22 unscored proposals, two of them entirely inside blind windows. That is
the pipeline handing its own job to the reader.

L5 now settles it. ADR-0005 defines the ladder: a deterministic rule first, and a model only
on the ambiguous 0.15–0.85 band the rule cannot settle. ADR-0005 also governs whether that
model ships — *"a model ships only if it measurably beats the tier below it"* — and CLAUDE.md
is blunter: *"Unmeasured models do not ship."*

ADR-0016 ran this same experiment three weeks of work ago, on the session audit, and the model
lost badly: F1 0.07 against a baseline's 0.63, destroying 181 seconds of real surfing. That ADR
closed by scoping itself deliberately: it ruled the model out of *adjudication there*, not out
of the product. This is the other place, so the answer had to be measured rather than inherited.

## The measurement

`evals/test_wave_adjudication.py`, five seeded sessions with exactly known ride intervals, both
contenders reading the **identical** L4 feature rows. `qwen2.5:7b-instruct-q4_K_M`, temperature
0, fixed seed. Two prompt variants in `prompts/wave_adjudicator.v2.md`:

- **`reasoned`** — the physics stated, the model asked to apply it. The candidate.
- **`ruled`** — the decision rule handed over outright. A **control, not a candidate**.

| contender | F1 | count error | rides refused | time |
|---|---|---|---|---|
| **baseline** | **0.77** | 2.6 | 13 | ~0 s |
| `llm:reasoned` | 0.76 | **1.8** | **9** | 24.1 s |
| `llm:ruled` (control) | 0.79 | 2.4 | 12 | 18.1 s |

The run behind this table is committed at `evals/results/wave_adjudication.json`.

## Decision

**The model does not ship. L5 ships the deterministic rule alone.**

- **`reasoned` did not clear its stated bar.** The bar, set before the run, was: beat the
  baseline on F1 *and* refuse no more real rides. It missed the F1 bar, 0.76 against 0.77.
- **`ruled` cleared both bars and still cannot ship**, because it is a control. A model handed
  the rule is executing it, not adjudicating — so a good score there says the model can
  pattern-match a rule the baseline already runs perfectly in microseconds rather than
  nineteen seconds. `prompts/wave_adjudicator.v2.md` has called it a control since before it
  was first run, and `CONTROLS` in the eval now encodes that so it cannot qualify by accident.

## What is different from ADR-0016, and worth saying plainly

ADR-0016's model was not merely worse than its baseline; it was close to anti-correlated with
the truth and it destroyed real surfing. **Neither is true here.** This model sits at parity —
0.76 against 0.77 is well inside the spread of five sessions, and this ADR does not claim the
rule is better, only that the contender did not clear the bar it had to clear.

More than that, `reasoned` was **better on the metric the product actually ships**:

- **Wave count error 1.8 against the baseline's 2.6**, a 31% improvement. The count is the
  number on the screen; F1 can hold while that number drifts.
- **9 real rides refused against 13.** It recovered four rides the rule had left in the band,
  which is exactly the job the band exists to hand over.

So the honest summary is not "the model is useless here". It is "the model did not clear the
bar, and the bar is F1". A reader is entitled to notice that a different pre-declared bar —
count error — would have let it through, and this ADR would rather say so than bury it. The bar
was not changed after the numbers arrived, and it should not be changed now to fit them either.

## The reproducibility bar, and why it passed this time

ADR-0016 disqualified its contender on a third count that had nothing to do with accuracy: run
twice at temperature 0 with a fixed seed, the verdicts came back identical and the **span edges
moved**. A component whose answer shifts between identical runs cannot sit inside the
content-addressed guarantee in `architecture.md` §3.

That finding shaped this design. The model here is never shown a boundary and has nowhere to
return one: it answers yes or no about intervals L3 fixed, and L5 copies those intervals
through untouched. Run twice, `ClassifyStage.encode` produced identical bytes, and
`llm:reasoned` scored 0.7595604 on both runs. **The design earned from ADR-0016 worked.** That
is the durable result of this work, whichever model is measured next.

## A prompt bug that nearly became a finding

Recorded because the failure mode is the dangerous kind — it produced a clean, plausible,
completely wrong measurement.

`load_prompt` sends only a variant's `### System` body. The output contract lived in the
shared `## Output` section above the variants, so **the model was never told what shape to
answer in**. It returned `{"0": false, "1": true}`. `AdjudicationVerdict` then accepted that
by ignoring both unknown keys and defaulting `verdicts` to empty, every candidate came back
"the model returned no answer", and the table showed all three contenders identical to four
decimal places — which reads exactly like "the model changes nothing" and would have been
written up as such.

Two fixes, both of which are the real deliverable of that hour: each variant now states its
own output contract, and `AdjudicationVerdict` sets `extra="forbid"` with no default, so
output that does not answer the question raises `ModelError` instead of parsing to silence.

## Consequences

- **`ClassifyStage` ships with `adjudicator=None`.** The ladder is built, the band is real,
  and nothing is asked. A candidate the rule cannot settle is `UNRESOLVED` and is **not**
  counted — an unsure rule with nobody to ask is not a yes.
- **The harness stays**, as ADR-0016's did. A better model, a rewritten prompt, or a sharper
  rule can be dropped into `evals/test_wave_adjudication.py` and scored against the same
  truth. `SHIPS` is empty; the test goes red and names what changed if that stops being true.
- **The synthetic generator grew an odometer** that reproduces the measured artefact — frozen
  through a blind window, back-filled in one step on reacquisition. Opt-in, drawing no
  randomness, so every committed golden stays bit-identical. Without it the contenders would
  have been scored on a signal that never gaps, and would have met the real one in production.
- **The rule's own limits are known and recorded.** On the five seeded sessions it produces
  **zero false positives**; its 13 refusals are candidates where the true ride occupies 1–18
  seconds of a 10–50 second proposal, most of them nearly fully blind. That is an L3 boundary
  problem and a data limit, not a threshold that wants turning — and six of the 13 land in the
  band, which is precisely where a model that earns its place would help.
- **This says nothing about Phase 11's prose passes.** Writing a sentence about numbers already
  computed is a different job from deciding what the numbers are. As with ADR-0016, this rules
  the model out of *adjudication here*, not out of the product.
