# Data findings — forensics on the reference session

**Session:** `24151923839` · "Sines Surfing" · sport 38 (surfing) · 2026-08-28 17:23:40Z · 3789 s
**Files:** `sample_data/24151923839_ACTIVITY.fit` (194 KB) · `sample_data/activity_24151923839.gpx` (629 KB)

Everything below is measured from those two files, not assumed. Reproduce with `research/fit_probe.py`.

> Those files are **gitignored** — this repo is public and they carry precise GPS traces.
> The numbers below are reproducible on any machine holding its own copy; the eval gate
> deliberately does not need them (see ADR-0008).

## 1. The GPX export is lossy — do not build on it

| | FIT | Garmin Connect GPX |
|---|---|---|
| records | **3790** (one per second) | 1849 |
| heart rate | 3790 (100%) | 1849 |
| cumulative distance | 3790 (100%) | absent |
| speed | 1849 | absent |
| CIQ wave fields | present | absent |

The GPX drops every record that had no GPS fix, so it silently discards 51% of the session
*including the heart-rate and distance that were recorded fine*. **FIT is the only acceptable primary source.**

## 2. GPS loss is real, and it is caused by water

Position is present in **1849 / 3790** samples — **48.8%**. This is identical in FIT and GPX,
so it is genuine signal loss, not an export artifact.

The cause is legible in the data. Coverage per minute:

```
min 0–54    coverage 3–97%     in the water
min 56–63   coverage 100%      out of the water (walking, then standing still)
```

Coverage hits exactly 100% the moment the wrist leaves the water and never dips again.
**Dropout density is therefore a usable feature — it is effectively a wetness sensor.**

Gaps: 86 of ≥5 s, of which 35 are 21–45 s. A wave lasts 5–20 s, so a single gap can swallow one whole.

## 3. Speed cannot be obtained by differencing positions

Finite-differencing the GPX yields:

```
>12 m/s (world-class only)   32 segments
>20 m/s (physically impossible) 11 segments
max 109 m/s = 392 km/h
```

Naive total distance from differencing: **5750 m**. The watch's own integrated distance: **3713 m**.
The 55% excess is GPS noise being integrated as real movement.

## 4. Dead reckoning does not happen

Cumulative distance (record field 5) advances **3712.9 m over the 1848 s with a fix** and
**0.0 m over the 1941 s without one**. The watch does not fill gaps. Neither should we.

## 5. A third-party Connect IQ app is already writing wave data

18 `field_description` messages define custom fields:

- on `record`: `waveplot` (kph), `waveplot2` (sec) — per-second speed *inside a detected wave*, zero elsewhere
- on `session`: `wavenum`, `LRtxt1` (lefts), `LRtxt2` (rights), `wavetime`, `wavedist`, `wavespd`, `settings1..5`

Its reported result: **17 waves, 7 lefts, 10 rights, 6:24 total wave time, max 39 kph.**
Its algorithm, read straight off `settings1/2/5`: **speed ≥ 9 kph sustained ≥ 5 s, shore bearing 270°.**

### Why that result is not trustworthy

Reconstructing its per-second segments from `waveplot2`:

| Symptom | Evidence |
|---|---|
| Count disagrees with itself | session says `wavenum=17`; only **16** segments exist in the per-second data |
| Duration disagrees with itself | `wavetime` = 384 s; segments total **290 s** |
| Detections with no position at all | **3 of 16** have 0% GPS coverage |
| **Frozen speed** | **7 of 16** have `v_max == v_avg` to 2 dp; **5** of those run ≥5 s (up to 29 s) — a latched last-known value, not a measurement |
| Physically implausible | #12: 33 s averaging 29.9 kph at 9% GPS coverage |

(The two excluded are only 3 s long, where identical values prove nothing.) The frozen-speed group is the clearest failure: when GPS drops, the app holds the last speed,
that held value stays above the 9 kph threshold, and the timer keeps running until a fix returns.
**Long GPS blackouts manufacture long fake waves.** This is the specific defect the project exists to fix.

### And we do not use them

An earlier draft imported these 16 segments as weak bootstrap labels. That was reversed —
see **ADR-0008**. Their values are derived from the same GPS stream we already hold, so they
carry no information we cannot compute ourselves, while carrying the failure modes above.

The findings on this page remain as *motivation*: they are why the project exists. Documenting
a competitor's failure is not the same as depending on its output. Ground truth comes from
human labelling in Phase 4; until then the eval gate runs on a synthetic session with exactly
known waves (`surf.synthetic`).

## 6. Field map confirmed in this file

**record (20):** `253` timestamp · `0/1` position lat/long (semicircles, 48.8%) · `3` heart_rate (100%) ·
`5` distance (100%, cm) · `13` temperature (100%) · `73` enhanced_speed (48.8%, mm/s) ·
`136` duplicate of heart_rate · `135` unidentified (44–176, mostly 176)

**session (18):** `5` sport=38 · `7/8` elapsed/timer 3789019 ms · `9` distance 371285 cm ·
`11` calories 368 · `16/17` avg/max HR 102/139 · `57/58` avg/max temp 21/23 ·
`124/125` enhanced avg/max speed 0.98 / **20.79 m/s** ← the watch's own max speed is also implausible (74.8 kph)

**Unidentified proprietary messages** present but not yet decoded: 233 (n=3795), 160 (n=1855),
325 (n=345), 326 (n=134), 22 (n=255). Message 160's cardinality tracks the GPS fix count and is
worth decoding in Phase 1 — it may carry per-fix quality or 3D velocity.

## 7. Consequences for the build

1. Ingest targets FIT. GPX/TCX are explicitly degraded tiers and must be labelled as such in the UI.
   Developer fields are **not** read by ingest (ADR-0008).
2. `lat`/`lon`/`speed` are optional fields in the canonical model. Half of reality has none.
3. Never impute across a blind window and present the result as measured.
4. Report **detected / uncertain / blind** as three distinct states.
5. Honest headline metrics are *ranges*, not points: "9–14 waves" beats a confident, wrong "17".
