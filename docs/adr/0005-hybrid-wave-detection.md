# ADR-0005: Hybrid wave detection; the LLM adjudicates only the ambiguous band

**Status:** accepted · 2026-08-28

## Context
The goal is reliable detection. The incumbent Connect IQ app uses a single rule — speed ≥ 9 kph
for ≥ 5 s — and fails in a specific, reproducible way: when GPS drops it holds the last speed,
the held value stays above threshold, and the timer runs on. Seven of its sixteen detections on
the reference session have `v_max == v_avg` to two decimals, which is a latched value rather
than a measurement.

A reasoning LLM as the primary detector would be non-deterministic, which is the opposite of
what "reliable" requires, and slower and less accurate than a purpose-built model on windowed features.

## Decision
Three tiers behind one `Detector` interface:

1. **Rule-based scorer** — transparent, tunable, ships first, fully explainable.
2. **Gradient-boosted trees** on ~30 features, trained on human labels, producing a *calibrated* probability.
3. **Local quantized LLM** (Ollama, ~7B Q4_K_M) adjudicating **only** candidates scoring 0.15–0.85.

All three are judged by one evaluation harness against held-out human labels. **A model ships
only if it measurably beats the tier below it.** The LLM runs locally, loads on demand and
unloads after an idle TTL or on explicit command.

## Consequences
- Tier 1 gives value immediately; tiers 2 and 3 are upgrades, not prerequisites.
- Requires human ground truth, hence the labeling UI landing before the detector (see PLAN.md).
- If the LLM does not beat the GBM on the ambiguous band, we do not ship it. That is an
  acceptable outcome, not a failure.
