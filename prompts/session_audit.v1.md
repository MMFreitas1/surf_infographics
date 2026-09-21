# Session audit — v1

**Version:** 1 · **Model:** local quantized instruct model via Ollama
**Scope:** deciding which minutes of a recording were spent out of the water.
**Contract:** output MUST validate against `AuditVerdict` (Pydantic). Invalid output is a failure, not a retry-until-it-parses.

> Changing this file REQUIRES re-running `evals/test_llm_audit.py` and updating the numbers
> in ADR-0016 (CLAUDE.md). The whole point of that eval is that the prompt is what decides
> the answer here — see the two variants below, which differ *only* in how much of the rule
> they state, and disagree completely.

---

## Input

A JSON array, one object per minute of the recording. **No coordinates, ever** — every field
is a rate, a fraction or a count (ADR-0015). This is what makes a hosted model safe to offer:
there is no location in the payload to leak.

```json
[{"i": 0, "coverage": 1.0, "speed_max": 1.36, "speed_mean": 0.31, "hr": 105}]
```

## Output

```json
{"out_of_water": [{"from_min": 0, "to_min": 1, "why": "perfect sky view, no movement"}]}
```

An empty list is a valid and often correct answer: most sessions are surfing end to end.

---

## Variant A — `reasoned`

States the physics and asks the model to apply it. This is the variant that has to work if
the model is adding judgement rather than executing arithmetic.

### System

You analyse a surf session recorded by a GPS watch, one row per minute.

GPS coverage is the key signal, and it is **inverted** from intuition:

- **In the water:** the wrist is submerged most of the time, so coverage is **low** (0.2–0.7).
- **Out of the water** (walking, resting on sand, driving home): nothing blocks the sky, so
  coverage is **high** (0.9–1.0) while speed stays low.

A surfer paddling or riding shows bursts of speed. A surfer sitting on the board waiting for
a set shows low speed but still **low** coverage, and often a high heart rate from paddling.

Heart rate distinguishes the two kinds of stillness: someone resting on the sand is
recovering, so their heart rate falls; someone sitting on a board between waves has just
paddled, so theirs stays up.

Identify which rows were recorded **out** of the water. Return JSON only:

```json
{"out_of_water": [{"from_min": <number>, "to_min": <number>, "why": "<at most 8 words>"}]}
```

Return an empty list if the whole session was in the water.

---

## Variant B — `ruled`

States the decision rule outright, with worked examples. Included **as a control, not as a
candidate**: a model given the rule is no longer adjudicating anything, it is executing a
rule the deterministic baseline already runs perfectly in microseconds. Its purpose is to
measure the gap between "the model can follow an explicit rule" and "the model can work out
the rule from the physics" — which is the gap that decides whether it ships.

### System

Classify each minute of a surf-watch recording as IN or OUT of the water.

The GPS coverage signal is inverted from intuition. Learn it from these examples:

```
coverage=0.38 speed_max=7.9 hr=108  -> IN    (low coverage = wrist underwater; bursts = riding)
coverage=0.20 speed_max=0.0 hr=103  -> IN    (low coverage = wrist underwater; waiting for a set)
coverage=0.62 speed_max=5.2 hr=106  -> IN    (still mostly submerged)
coverage=1.00 speed_max=0.0 hr=100  -> OUT   (perfect sky view, no movement = on the sand)
coverage=1.00 speed_max=1.4 hr=105  -> OUT   (perfect sky view, walking pace)
coverage=0.97 speed_max=1.7 hr=130  -> IN    (dry wrist but HR still high = sitting up on the board)
```

**RULE:** OUT requires `coverage >= 0.9` AND `speed_max < 3.0`. Everything else is IN.

Return JSON only, in the same shape as variant A:

```json
{"out_of_water": [{"from_min": <number>, "to_min": <number>, "why": "<at most 8 words>"}]}
```
