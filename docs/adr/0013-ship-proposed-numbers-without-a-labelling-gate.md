# ADR-0013: Ship proposed numbers; stop gating the product on labels

**Status:** accepted · 2026-08-31 · supersedes the Phase 4-before-Phase 5 rule

## Context

ADR-0012 and PLAN.md made human labels a hard gate: no phase past labelling could claim a
quality number, so nothing past labelling got built. Phase 4 delivered the tooling — an
append-only store, six endpoints, a scrub UI, and `truth_intervals` joining labels to the
metric. Then it hit the assumption nobody had checked.

**A person cannot label a session they surfed days ago.** They do not remember which waves
happened. The UI was built so the labeller reads the *signal* rather than their memory — but
push on that and the justification thins: someone identifying rides by eyeing a speed chart
is applying a rule by eye, and the detector is applying a rule in code. Scoring one against
the other measures **agreement, not accuracy**. Calling that output "ground truth", as
ADR-0006 and PLAN.md did, oversells it.

Meanwhile the actual request — infographics, with the noise cleaned out automatically — sat
four phases behind the gate. Five phases of work had produced no picture of a surf session.

## Decision

**The labelling gate is dropped.** Phases 5–11 build the product: clean signal, shore
direction, wave metrics, sea state, and the three-level drill-down UI.

**Every derived number ships marked *proposed*.** Wave counts, speeds, manoeuvre counts and
surf levels are readings of the data, and the UI says so. No accuracy, precision or recall
figure is published anywhere until a session is labelled the day it was surfed.

**The labelling tool stays exactly as built.** It costs nothing to keep, and it is the only
route to a validated number. `make labels` answers the standing hypothesis the moment one
fresh session is labelled.

**What this does *not* relax:** detected / uncertain / blind stay three distinguishable
states; no imputed value is ever presented as measured; every number keeps its coverage and
its confidence. Those rules get *more* important without labels, not less — they are now the
only thing standing between a proposal and a claim.

## Consequences

- The ML detector and the LLM band-adjudicator (ADR-0005) are deferred, not cancelled. Both
  need labels: a model fitted to L3's proposals would only ever learn L3, and adjudicating an
  ambiguous band requires a calibrated score to have a band of.
- "12 waves" on a dashboard is a proposal. If it later proves wrong, the UI must have said so
  first — that is the whole bargain being struck here.
- The honest wording for the product is "what your watch recorded, read carefully", never
  "measured wave detection".
- Reversing this needs only one labelled fresh session, which is why the tooling stays.

## What made this visible

Miguel, on being handed the labelling UI: *"I don't even know what I'm looking at... Why do
I need to label if I don't remember which waves had passed? It has been a couple of days
already."* The plan had been questioned three times about *how* to label and never once about
whether it was possible.
