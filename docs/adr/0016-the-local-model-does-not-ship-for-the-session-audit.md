# ADR-0016: The local model does not ship for the session audit

**Status:** accepted · 2026-09-21

## Context
Phase 5's last open item was the LLM audit pass: adjudicate the not-surfing stretches L0.6's
deterministic baseline cannot settle (ADR-0015). ADR-0005 governs whether it ships — *"a model
ships only if it measurably beats the tier below it"*, and CLAUDE.md is blunter still:
*"Unmeasured models do not ship."*

So it was measured. `evals/test_llm_audit.py` scores both contenders on the **identical**
coordinate-free digest L0.6 already produces, across five seeded sessions that each walk down
to the water, surf, take a break on the sand, surf again, and walk back.

Two prompt variants, both in `prompts/session_audit.v1.md`:

- **`reasoned`** — the physics of GPS coverage stated, the model asked to apply it. This is
  the variant that has to work if a model is adding judgement.
- **`ruled`** — the decision rule handed over outright, with worked examples. A **control**,
  not a candidate: a model given the rule is executing it, not adjudicating anything.

## The measurement

`qwen2.5:7b-instruct-q4_K_M`, temperature 0, fixed seed, five sessions:

| contender | F1 | interior recall | ride seconds destroyed | time |
|---|---|---|---|---|
| **baseline** | **0.63** | 0.00 | **0** | ~0 s |
| `llm:reasoned` | 0.07 | 0.40 | 181 | 304 s |
| `llm:ruled` | 0.45 | 0.80 | 110 | 363 s |

The run behind this table is committed at `evals/results/llm_audit.json`.

## Decision

**The model does not ship. Phase 5 ships the deterministic baseline alone.**

It fails on two independent counts, and either alone is disqualifying:

1. **Neither variant beats the baseline on F1.** The one that matters — `reasoned`, the model
   working the physics out for itself — scores **0.07 against 0.63**. It does not
   underperform the baseline; it is close to anti-correlated with the truth. An earlier probe
   showed why in the model's own words: asked free-form, it flagged the *surfing* as
   out-of-water and gave its reason as "high speed, low coverage", which is precisely the
   in-water signature the prompt had just explained.

2. **Both destroy real surfing.** 181 and 110 seconds of genuine rides across five sessions,
   against the baseline's zero. This is the asymmetric cost the eval was built around: leaving
   the walk home in a session skews a duration, but cutting a ride out of one destroys the
   measurement this product exists to make, and leaves no trace that it happened.

ADR-0005 anticipated exactly this: *"If the LLM does not beat the GBM on the ambiguous band,
we do not ship it. That is an acceptable outcome, not a failure."*

### A third reason, found by running it twice

The measurement was run twice at temperature 0 with a fixed seed. F1 and interior recall came
back **identical to four decimal places** both times — and ride seconds destroyed moved, 166 →
181 and 95 → 110. The verdicts are stable; the *edges of the spans* are not.

This project content-addresses every stage output precisely so that a published number is
exactly reproducible (`docs/architecture.md` §3). A component whose answer shifts between two
identical runs cannot sit inside that guarantee, and would have to be pinned by caching its
output rather than its inputs — which is a different and much weaker promise. Even had the
accuracy been there, this alone would need answering before the stage could be built.

## Why it lost, structurally

ADR-0005 scopes the LLM to the **ambiguous band**. For this task that band is close to empty.
In-water windows sit at **0.39** coverage and out-of-water ones at **1.00**, with nothing in
between — the signal that makes GPS hard here is what makes the decision easy. There is little
left to adjudicate, and a 7B quantized model reading 64 rows of numbers is a poor instrument
for what remains.

The `ruled` control is the sharper evidence. It scores *better* than `reasoned` — 0.45 against
0.07 — which says the model is not reasoning from the physics at all; it is pattern-matching
an explicit rule, and doing so imperfectly. A model that needs the rule spelled out to be
useful adds nothing over the rule itself, which the baseline already executes perfectly in
microseconds rather than 50 seconds a session.

## What the model *did* find, recorded honestly

`ruled` reached **0.80 interior recall** where the baseline scores **0.00**. Interior breaks —
a surfer coming out for a rest mid-session — are the one thing the baseline cannot see, by
design (ADR-0015).

That is a real gap and this ADR does not dismiss it. But it was bought with 110 seconds of
destroyed rides, and a gap worth closing is not the same as a tool worth using. The obvious
next attempt is a **deterministic** interior rule — high coverage plus low speed plus a
*falling* heart rate, which is what separates resting on the sand from sitting on a board —
and it should be measured against the same harness before anyone reaches for a model again.

## Consequences

- **L0.7 is not built.** No stage, no endpoint, no Zod mirror, no contract golden. Phase 5
  closes with the deterministic cleaner (L0.5) and audit (L0.6).
- **The harness stays.** `evals/test_llm_audit.py` is the durable part of this work: a better
  model, a different prompt or a deterministic interior rule can be dropped into it and scored
  against the same truth without rebuilding anything. It writes its verdict to
  `evals/results/llm_audit.json` rather than only printing it, because an eighteen-minute
  measurement that evaporates on a failed assertion is no measurement at all.
- **The decision is encoded, not just documented.** The eval holds a `SHIPS` list, currently
  empty. If a future contender clears both bars the test goes red and names what changed,
  which is the moment to re-measure and rewrite this ADR — rather than a model quietly
  shipping because someone edited a threshold.
- **The synthetic generator grew interior-break truth** (`break_after_wave`, `break_s`),
  opt-in and drawing from its own RNG stream so every committed golden stays bit-identical.
  Nobody can mark from memory which minute they left the water — the same problem ADR-0013
  records for waves — so this truth had to be built rather than collected.
- **This says nothing about Phase 11's prose passes.** Those are a different job: writing a
  sentence about numbers already computed, not deciding what the numbers are. This ADR rules
  the model out of *adjudication here*, not out of the product.
