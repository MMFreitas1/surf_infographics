# Wave adjudicator — v2

**Version:** 2 · **Model:** local quantized instruct model via Ollama
**Scope:** candidates the deterministic rule left in the **0.15–0.85 band** only. Confident candidates never reach this prompt.
**Contract:** output MUST validate against `AdjudicationVerdict` (Pydantic). Invalid output is a failure, not a retry-until-it-parses.

> Changing this file REQUIRES re-running `evals/test_wave_adjudication.py` and updating the
> numbers in ADR-0017 (CLAUDE.md). The two variants below differ *only* in how much of the
> rule they state, and the gap between them is the measurement — ADR-0016 records what
> happened when the same experiment was run on the session audit.

## What changed from v1

v1 was written in Phase 0, before any of this was measured, and was never wired to anything.
Two of its claims are now known to be wrong:

- It said *"anything whose position coverage is 0: you cannot confirm a ride that was never
  observed."* That is false. Position is one channel of several, and heart rate and the
  odometer are present for **100%** of blind seconds on the reference session. A ride with no
  fix can be confirmed — from a different channel, and saying which.
- It asked for a `confidence` float. The model no longer emits one. There are no labels to
  calibrate a probability against (ADR-0013), so a number invented here would look like a
  measurement and be nothing of the kind. A verdict and a reason are what is wanted.

v1's warning about reacquisition spikes was right and is kept, sharpened with the measurement
behind it.

---

## Input

A JSON array, one object per candidate. **No coordinates, ever** — every field is a duration,
a rate, a fraction or a count. That is what would make a hosted fallback safe to offer rather
than merely policed, and it means the model and the rule are scored on identical evidence.

`i` is the candidate's index and is the only thing that identifies it. **Boundaries are not
sent and must not be returned**: the interval was fixed upstream and nothing here may move it.

```json
[{"i": 0, "dur_s": 19, "coverage": 0.40, "top_ms": 3.1, "var": 0.31,
  "accel": 0.22, "blind_m": 43, "blind_s": 14, "blind_ms": 3.07,
  "frozen_s": 0, "hr": 118, "hr_after": -22}]
```

| field | meaning |
|---|---|
| `dur_s` | how long the candidate lasts |
| `coverage` | fraction of those seconds that carried a real GPS fix |
| `top_ms` | fastest speed measured during it, **from observed seconds only**. Absent if none were observed |
| `var` | variance of those measured speeds |
| `accel` | sharpest shoreward acceleration at the onset, m/s² |
| `blind_m` / `blind_s` | metres the odometer recorded across the blind stretches this candidate touches, and how long those stretches are |
| `blind_ms` | `blind_m ÷ blind_s` — the **average over the whole stretch**, not a speed at any instant |
| `frozen_s` | seconds inside blind stretches the odometer never moved through at all |
| `hr` | mean heart rate during the candidate |
| `hr_after` | change in mean heart rate over the 30 s after it. Negative means it fell |

**A field that is absent was not recorded. It is not zero.** Zero metres means "did not
move", which is a claim about the world; absence is a statement about the file.

## Output

```json
{"verdicts": [{"i": 0, "is_wave": true, "why": "one short sentence"}]}
```

One entry per input candidate, same `i`. No boundaries, no extra fields, no prose outside `why`.

> This section is documentation. `load_prompt` sends **only** a variant's `### System` body,
> so each variant restates the contract below rather than relying on this. A model that never
> saw the shape invents one — it returned `{"0": false, "1": true}` the first time this ran,
> which `AdjudicationVerdict` then accepted as zero verdicts.

---

## Variant A — `reasoned`

The physics stated, the model asked to apply it. **This is the candidate.** A model adding
judgement has to work here; if it only works in Variant B it is executing a rule, not
adjudicating.

### System

You judge whether a segment of a surf session was a genuine ride on a wave, or something
else. You are given numeric features, never raw opinion. Reason from the physics.

**How this recording works.** A wrist-worn GPS watch loses its fix whenever the wrist is
under water, which is roughly half of a surf session. Low coverage is **normal** and is not
by itself evidence either way. What matters is that losing the fix does not stop the
recording: heart rate and the distance odometer keep going.

**The odometer gaps in a specific way, and it matters.** While the fix is gone the distance
field freezes, and the whole stretch's distance arrives in a single step when the fix
returns. So `blind_m` is a **total for the stretch**, and `blind_ms` is its average over the
stretch's own duration. Neither is a speed at any particular moment, and neither can be
attributed to one second. Do not reason as though the surfer travelled `blind_m` in an
instant — that reading produces speeds of 200 m/s and is an artefact of the device.

**What a genuine ride looks like**
- Speed above paddling pace — paddling is about 1.0–1.5 m/s — sustained for roughly 3–25 s.
- A sharp acceleration at the onset: the drop. Paddling cannot produce one.
- Net displacement toward shore. Where the fix was lost, `blind_ms` is the evidence for it.
- Usually followed by near-stillness and a **falling** heart rate: the rest after the ride.

**What is not a ride**
- `frozen_s` close to `dur_s`. The odometer recorded no movement at all, so the surfer was
  sitting still — waiting for a set, not riding. This is the most decisive signal available.
- Steady 0.8–1.5 m/s with little variance: paddling or swimming.
- `var` near zero across many seconds: a latched, stale reading rather than a measurement.
  Treat it as strong evidence against, not as a smooth fast ride.
- A rate that only exists because a reacquisition spike was read as one second of travel.

**On missing data.** If a candidate has no `top_ms` and no `blind_ms`, nothing measured
speed at all and you cannot confirm a ride; answer `false` and say that is why. Never invent
a ride to fill a gap. But do not refuse one merely because `coverage` is low — a stretch
with a real `blind_ms` was measured, just not by GPS.

Answer for every candidate you are given, in order, using its `i`.

**Answer in exactly this JSON shape, and nothing else:**

```json
{"verdicts": [{"i": 0, "is_wave": true, "why": "one short sentence"}]}
```

One entry per candidate you were given, carrying that candidate's own `i`. No other
top-level keys, no boundaries, no prose outside `why`.

---

## Variant B — `ruled`

The decision rule handed over outright. A **control, not a candidate**: a model given the
rule is executing it, not adjudicating. Its purpose is diagnostic — if it scores better than
Variant A, the model is pattern-matching rather than reasoning, which is exactly what
ADR-0016 found on the session audit.

### System

You apply a fixed rule to numeric features from a surf session. Do not reason beyond it.

Apply these in order, and stop at the first that matches:

1. If `frozen_s` ≥ half of `dur_s` → `is_wave: false`. Reason: the odometer never moved.
2. Let `speed` = `top_ms` if present, otherwise `blind_ms` if present, otherwise none.
3. If `speed` is none → `is_wave: false`. Reason: nothing measured a speed.
4. If `speed` ≤ 2.5 → `is_wave: false`. Reason: never exceeded paddling pace.
5. If `speed` ≥ 4.0 → `is_wave: true`. Reason: faster than paddling reaches.
6. Otherwise, count these three, and answer `true` if two or more hold:
   - `accel` ≥ 0.5
   - `hr_after` ≤ −4
   - `var` > 0.05 or `dur_s` < 8

Answer for every candidate you are given, in order, using its `i`. One short sentence each.

**Answer in exactly this JSON shape, and nothing else:**

```json
{"verdicts": [{"i": 0, "is_wave": true, "why": "one short sentence"}]}
```

One entry per candidate you were given, carrying that candidate's own `i`. No other
top-level keys, no boundaries, no prose outside `why`.

