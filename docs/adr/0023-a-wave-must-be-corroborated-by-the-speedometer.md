# ADR-0023: A wave must be corroborated by the device's own speedometer

**Status:** accepted · 2026-10-24 · first use of **L0.5's rejection record as evidence**,
which [ADR-0014](0014-rejection-is-demotion-not-deletion.md) produced and nothing read

## Context

On 2026-10-24 Miguel labelled the reference session's eleven settled waves — the first ground
truth this project has had. **Three of the eleven are not waves.**

| Ride | Call | In his words |
|---|---|---|
| 1, 2 | wave | "trimming, waiting for the wave to form, already standing" |
| 3, 4, 5, 6, 9, 11 | wave | a right-hand point; all rights |
| 7 | **not a wave** | "didn't happen, too far out from the peak" |
| 8 | **not a wave** | "me trying to wait for the mellow wave to form a wall, but it didnt" |
| 10 | **not a wave** | "didn't happen, too far out from the peak" |

Rides 7 and 10 are the same artefact, and it is one this repo already documented without
noticing it could manufacture a wave. A long blind stretch ends; the watch re-acquires and
**dumps the distance it accumulated while blind into a single 1-second odometer step**; the
smoother bridges the position gap with a smooth acceleration curve shaped exactly like a
ride. L3 proposes it, L5's rule reads the back-filled odometer as a window total, and a
paddle becomes a wave.

- **Ride 10:** **2 of 33 seconds carried a fix**, 167 m and 17 s apart. Everything between —
  the ramp to 11.56 m/s and back down — is interpolation, and 11.56 is against L1's
  `max_speed_ms` of 12.0, so the smoother was saturating. Odometer 216 m across the span, of
  which **201.5 m arrived in one second** (93%). That is the 201 m in ADR-0014's own docstring.
- **Ride 7:** 9 of 21 seconds seen; odometer 157 m with **140.4 m in a single second** (89%);
  and the watch recorded **0.00 m/s on every second where it logged a speed at all**, against
  the smoother's 9.50 m/s peak.

ADR-0014 got the odometer half of this right — "read as a **window total, never a rate**" —
and the window total is still wrong when the back-fill step lands *inside* the window carrying
distance earned before it.

## The cut

**Does the watch's own speedometer ever reach what the track claims?** Highest device speed
recorded during the candidate's span, over the highest smoothed speed across the same seconds:

```
waves       0.79  0.85  0.86  0.93  0.94  0.95  0.97      (ride 2 has no speed reading at all)
artefacts   0.00  0.15  0.38
```

**Every cutoff from 0.4 to 0.7 gives 3 of 3 artefacts refused and 8 of 8 waves kept.** A
plateau that wide is what a signal looks like; a threshold that works at one value is a tuned
one.

It has to be **peak against peak**. Comparing the two channels second by second closes the gap
to 0.01 and separates by luck — Doppler speed and position-derived speed legitimately disagree
moment to moment, but not about whether 9.5 m/s happened. The question is "did the watch ever
measure anything like this during this span", not "do the channels track each other".

### What does not separate them

Recorded because two of these are the obvious reach, and they fail:

| Statistic | Why it fails |
|---|---|
| **`position_coverage`** | ride 9 is a real wave at 37% seen, ride 7 an artefact at 43%, ride 2 a real wave at **0%**. No separation at all. |
| **Odometer back-fill share** | ride 1 (real) 72%, ride 8 (artefact) 59% — the real one looks worse. |
| **L0.5 rejections inside the span** | catches 7 and 10 outright (5 and 4, against **zero for all nine others**) and misses 8. Perfect corroboration, useless as the gate. |
| **Distance from the peak** | Miguel's own stated reason, and the weaker signal: artefacts start 22 / 129 / 173 m out, real waves 8–104 m. Ordered, but the gap is only 104 to 129. |

### It is not circular

`clean.py:468` and `:473` clear a rejected speed to `None`, **never to `0.0`**, and
`min_checkable_speed_ms = 8.0` means L0.5 never cross-examines a reading below 8 m/s. Ride
7's zeros are untouched device output, not the cleaner's decision read back. Doppler speed is
a channel of its own, not derived from the position fixes, so this is a genuine
cross-examination between two first-party signals and ADR-0008 holds.

## Decision

**L4 measures it; L5 refuses on it; L3 is untouched.**

- **L4** gains `speed_corroboration` — the span's highest device speed over its highest
  smoothed speed, computed on the **cleaned** samples, and **absent rather than zero** when the
  span carries no speed reading. It also carries `rejected_fixes_in_span`, read from L0.5's
  `CleanReport`, as reported evidence that does not gate.
- **L5's deterministic rule refuses below the cutoff**, with its reason in words a person can
  disagree with: *"the watch never measured above 1.8 m/s here; the track claims 11.6"*.
- **L3 stays high-recall and must keep proposing these.** Its own docstring is the reason: a
  candidate never proposed cannot be recovered later.

### A span with no speed reading is not judged, and does not acquire numbers

Ride 2 is three seconds with zero fixes and zero speed readings. The rule has nothing to
divide, so it abstains — and abstaining must not mean "kept, with numbers". It is a wave that
publishes **no speed and no direction**: `blind`, already one of the three states the product
reports (`architecture.md` §8). Miguel confirmed it is real; it is still not measured.

### The cutoff is 0.65, in code, overridable from the environment

- **The default lives in code**, as a field on the stage, because that is what lets the repo
  reproduce its own published numbers.
- `SURF_WAVE_SPEED_CORROBORATION` in `Settings` overrides it. **This is the first stage
  parameter to come from the environment**, and the reason every other one is a field is the
  content hash — so the **resolved** value goes into `StageMeta.params`. A verdict can then
  never be served under a cutoff it was not computed with. Two `.env` files give two cache
  keys and two counts, which is correct rather than a bug.
- The resolved value ships in the verdict response, so a screenshot is traceable to the knob
  that produced it.
- **0.65 is stricter than the data needs, deliberately.** The worst artefact is 0.38, so 0.65
  catches nothing extra on this session and narrows the margin against refusing a *genuine*
  wave from 0.29 to 0.14. Miguel chose it to be strict about a future fuzzier case, on the
  reasoning that a wave wrongly refused is recoverable through a label and the UI lets him
  reject one that survives.

### The local model is not called for this

ADR-0017 kept the model for the ambiguous 0.15–0.85 band and Miguel's instinct was that this
failure mode needed it. A plateau this wide says otherwise, and a deterministic rule is
strictly better here: it caches, so the count is reproducible (`architecture.md` §3); it
explains itself in one line; and it was never going to be beaten by a model reading the same
two numbers. **The model stays in the code for what it was measured on**, and these three
candidates leave the ambiguous band rather than entering it.

## Consequences

- **Cleaning and detection now speak, and that is new.** L0.5 produced a rejection report that
  was served and never read by another stage. A candidate dense with rejections is a candidate
  built on refused data, and that is a fact about the candidate.
- **Demoting a bad fix makes the artefact worse, not better.** It is still the right thing to
  do (ADR-0014), but a blinder span gives the smoother more room to invent, so the demotion
  has to travel forward as evidence rather than only as a hole in the coverage.
- **The count drops from 11 to 8 on the reference session**, and every surviving wave is a
  right. ADR-0022's axis does not move the count; this does.
- **It also removes the only `LEFT`.** Ride 7 was it, which is why Phase 6's straight band
  could be narrowed to ±8° — a right point produces rights, and Miguel does not ride straight.
- **Eleven labels from one session justify a rule, not a hit rate.**
  [ADR-0013](0013-ship-proposed-numbers-without-a-labelling-gate.md) binds: nothing here is an
  accuracy claim and everything still ships marked *proposed*. The plateau is what makes the
  rule safe to ship on one session's labels; the cutoff is revisited when a second is labelled.
- **Every rejection Miguel makes in the UI compounds.** Labels are append-only and
  pipeline-immutable (ADR-0006), so disagreeing with this rule builds the set the next sweep
  is measured against. The eval set grows out of the product being wrong in front of him.
- **A device with no speed channel cannot be judged by this rule at all.** GPX without
  extensions is that case (ADR-0002 already calls GPX degraded). The rule abstains per
  candidate, so such a session keeps its waves and loses its speed claims, rather than
  losing its waves.
