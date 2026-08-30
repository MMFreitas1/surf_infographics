# Build plan

Cross-session source of truth. **Read this first after a `/clear`.**
Tick items as they land — an item is only ticked when it is verified, not when it is written.

---

## ▶ RESUME HERE

| | |
|---|---|
| **Tier** | 2 · approved 2026-08-28 |
| **Done** | Phase 0 — foundation, CI, diagnostics · **Phase 1** — ingest, storage, REST · **Phase 2 complete** — pipeline spine, L0 and L1 as cached stages, RTS-smoothed track |
| **Next** | Phase 3 — frame: shore bearing, cross-shore/alongshore transform, candidate generation. Start at **"Phase 3 · Frame"** below |
| **Health** | `make check` → 203 tests green (158 api · 16 web · 29 evals); 12 api tests skip without `sample_data/` |
| **Repo** | **PUBLIC** — `sample_data/` and `data/` are gitignored; never commit GPS traces |

**Orient in three commands:**
```bash
make check                 # everything CI runs
cat docs/architecture.md   # component map + one-way doors
ls docs/adr/               # why each decision was made
```

**Three rules that override convenience** (full list in `CLAUDE.md`):
1. Never present an imputed wave as measured. Detected / uncertain / blind are three states.
2. The pipeline consumes only first-party recorded signal (ADR-0008).
3. Phase 4 (labeling) lands before Phase 5 (detector). No ground truth, no quality claim.

---

## Phase checklist

- [x] **0 · Boot** — conventions, architecture, ADRs, scaffold, CI, test + eval harness, local diagnostics
- [x] **1 · Ingest** — FIT/GPX/TCX → canonical `Activity`, fidelity-tagged, golden tests, stored
- [x] **2 · Kinematics** — Kalman + RTS smoother, blind windows, propagated confidence
- [ ] **3 · Frame** — shore-bearing estimation, cross-shore/alongshore transform, candidate generation
- [ ] **4 · Labeling UI** — scrub a session and mark waves, from raw signal
- [ ] **5 · Rule detector** — transparent scorer → **first real precision/recall**
- [ ] **6 · Core infographics** — session map, sawtooth, state ribbon, wave cards
- [ ] **7 · ML detector** — gradient-boosted trees, calibration, CI regression gate
- [ ] **8 · LLM adjudicator** — Ollama + lifecycle manager, ambiguous band only
- [ ] **9 · Context** — Open-Meteo Marine: swell, tide, wind
- [ ] **10 · Full suite** — remaining infographics + replay animation

---

## Phase 0 · Boot — ✅ complete

### Boot Definition of Done
- [x] 1.1 Architecture confirmed and recorded → `docs/architecture.md` + 8 ADRs
- [x] 1.2 Scaffold: layout, uv + pnpm, `.env.example`, `.gitignore`, `tests/` with `conftest.py`
- [x] 1.3 Code standards: Ruff + Biome, mypy strict + TS strict, all enforced
- [x] 1.4 Version control: git, Conventional Commits + branch policy in `CLAUDE.md`
- [x] 1.5 Testing: harness runs, 68 tests pass, fixture pattern in place
- [x] 1.6 CI: lint → typecheck → tests → evals, blocks merge
- [x] 1.7 Deploy target chosen and **verified** — localhost + `docker compose up` on Colima
- [x] 1.8 Observability — structlog JSON to stdout + file, local error buffer (ADR-0007)
- [x] 1.9 Dependency updates — Dependabot for uv, npm, actions
- [x] 2.A `prompts/` exists, no prompts buried in code
- [x] 2.B Tracing — **decided against**, LLM I/O logs to disk instead (ADR-0007)
- [x] 2.C `evals/` harness with a golden, wired into CI as a gate
- [x] 2.D Guardrails plan noted — structured output validation, ambiguous-band-only scope (ADR-0005)
- [x] 2.E Feedback loop documented in `CLAUDE.md`

### Built
- [x] `CLAUDE.md` from canonical template + project honesty rules
- [x] `docs/architecture.md`, `docs/data-findings.md` (reproducible forensics), ADR 0001–0008
- [x] Canonical Pydantic model — `lat`/`lon`/`speed` optional by design
- [x] `surf.evaluation` — interval IoU matching, precision/recall/F1
- [x] `surf.synthetic` — seeded session with exactly known waves (52.5% coverage, 8 rides)
- [x] `surf.pipeline` — content-addressed stage cache
- [x] `surf.llm.lifecycle` — load on demand, unload on idle TTL or command, injected clock + backend
- [x] `surf.diagnostics` — bounded error buffer, `/diagnostics/*` endpoints
- [x] Zod contracts mirroring the Python model + `certaintyOf()`
- [x] Playwright UI verification → screenshots + console/page/network errors
- [x] CI, Dependabot, PR template, pre-commit, Docker Compose, Makefile

### Course corrections made during Phase 0
- [x] Sentry + Phoenix removed → local diagnostics (ADR-0007)
- [x] Connect IQ bootstrap labels removed → synthetic golden (ADR-0008)
- [x] Docker Desktop install failed silently (sudo) → Colima; compose verified

### Bugs caught by running things, not by reading green output
- [x] LLM idle-TTL restarted on work *start*, not *finish* — caught by its own test
- [x] Browser errors mislabeled `RuntimeError`, real stack discarded — caught by live curl
- [x] Missing `.dockerignore` broke the web image behind a false `exit 0` — caught by verifying

### Open before moving on
- [x] **Commit Phase 0** — merged as PR #1 (`3b26065`)

---

## Phase 1 · Ingest — ✅ complete

**Goal:** a canonical `Activity` from any of the three formats, with fidelity tracked.

**Parsers** ✅ PR #10

- [x] Port `research/fit_probe.py` → `api/src/surf/ingest/fit.py` as production code
      (full field profile, both endiannesses, compressed timestamps with rollover, CRC-16)
- [x] **Skip developer fields** — by declared size, never decoded (ADR-0009)
- [x] `ingest/gpx.py` and `ingest/tcx.py`, both tagged degraded fidelity
- [x] Blind-window derivation: `NO_FIX` runs *and* `MISSING_RECORD` gaps, one bounds convention
- [x] Golden tests pinning the reference session:
      3790 records · 1849 positions · 48.8% coverage · sport `surfing` · 3712.85 m ·
      **3790 s span** — not the 3789.019 s the watch reports: one record is genuinely
      missing 16 s in (`docs/data-findings.md` §4)
- [x] Decode message 160 → it is `gps_metadata`, with **no timestamp** and six more rows than
      there are fixes, so it cannot be aligned to the timeline. Written up in
      `docs/data-findings.md` §6 and **not ingested**. Revisit only if a timestamped variant appears.

**Store** ✅ PR #11

- [x] SQLite `activities` + `blind_windows` tables — `store/schema.sql`, `store/repo.py`
- [x] Samples → Parquet through the existing `StageCache` (L0), keyed from the activities row
- [x] `POST /activities` + `GET /activities/{id}` + `GET /activities` in the canonical shape
      (raw bytes as the body, not multipart — see `docs/architecture.md` §6)
- [x] Idempotent ingest: identical bytes return the stored activity with 200, not a second row
- [x] Zod contract parity — one committed fixture read by both sides; **drift detection verified
      in both directions**, not just asserted

**Done when:** the reference FIT round-trips into an `Activity` whose numbers match the
golden exactly, it survives a restart, and `make check` is green.

---

## Standing hypothesis — settle in Phase 5

GPS dropout is caused by wrist submersion. While *riding*, a surfer stands with the wrist clear
of the water, so GPS should **recover** during a genuine wave. If it holds, position availability
becomes a strong positive feature.

Deliberately **not** baked into `surf.synthetic` — its dropout is state-independent, so a detector
cannot score well by learning an assumption we have not confirmed. Needs human labels to settle.

## Evaluation

Gate runs today on `surf.synthetic`: a seeded session with exactly known wave intervals, no
personal data, no third-party values. Human labels from Phase 4 join the same harness.

## Diagnostics loop

| Need | Command |
|---|---|
| Recent API errors | `make errors` (or `GET /diagnostics/errors`) |
| Structured log tail | `make logs` (or `GET /diagnostics/logs`) |
| Look at the UI | `make verify` → `web/verification/*.png` + `*.json` |
| Containerised stack | `docker compose up -d` → api :8000, web :3000 |

`make verify` reuses whatever already serves :3000, so it works against dev server or container.
Browser errors POST to `/diagnostics/client-error`, so UI and API failures share one buffer.

## Deferred, with reasons

| Item | Why | Unblocks when |
|---|---|---|
| Ollama + quantized model | not needed until Phase 8 | Phase 8 |
| Playwright in CI | needs a browser download in the runner; runs locally today | Phase 6, if warranted |
| Docker Desktop | install needs a sudo password it cannot prompt for; Colima provides the daemon and compose is verified | only if the GUI is wanted |

## Decided against

| Item | Why |
|---|---|
| Sentry | single-user localhost app; local buffer + JSONL log is more useful and free (ADR-0007) |
| Phoenix / LLM tracing | same; Phase 8 logs prompt/response pairs to disk (ADR-0007) |
| Connect IQ bootstrap labels | derived from the same GPS we hold — their errors, no information (ADR-0008) |

---

## Phase 2 · Kinematics — ✅ complete

**Goal:** a smoothed position/velocity track with per-sample confidence, honest across blind windows.

### What Phase 1 hands you

```python
from pathlib import Path
from surf.ingest import parse_file
activity = parse_file(Path("sample_data/24151923839_ACTIVITY.fit"))   # or POST it to the API
```

`Sample.confidence` already exists on the model and defaults to `1.0` — **L1 is what refines it.**
Measured properties of that input, which the smoother has to respect rather than average away:

| Property | Value on the reference session | Why it matters to L1 |
|---|---|---|
| cadence | 1 Hz (derived as the *mode* of the steps, not the median) | the process model's dt |
| position coverage | 48.8% — 1849 of 3790 samples | half the updates are missing, not noisy |
| blind time | 1942.0 s over 128 windows, longest **107 s** | a 107 s unobserved stretch cannot yield a confident track |
| `speed_ms` | present **only where positioned**; absent from GPX entirely | not an independent measurement to lean on when blind |
| `distance_m` | 100% present in FIT, and **does not advance while blind** (`docs/data-findings.md` §4) | the watch adds no dead reckoning — a real constraint, not a gap to fill |
| differencing positions | yields up to 109 m/s, 11 segments over 20 m/s (§3) | raw finite differences are unusable as a velocity measurement |

Blind windows arrive as `BlindWindow` objects with a cause (`no_fix` vs `missing_record`), not as
absences to be discovered. Do not re-derive them.

### Do these two first — groundwork, not smoothing

Phase 2 is the first phase that must implement `Stage`, and that abstraction has never run.

- [x] **Pipeline spine.** ✅ PR #14 — `surf.pipeline.run_stage` is the one door every stage
      goes through (key → hit, or run and store), and `surf.ingest.stage.IngestStage` is L0
      behind it. `tests/test_pipeline_spine.py` runs a built FIT *and* the reference session
      through it and asserts miss → hit, an identical payload round-trip, and a changed param
      landing in a different entry. The hit is proved by handing the second call bytes that
      are not an activity: if the runner re-parsed, it would raise. Add L1 to that file
      rather than giving it a spine argument of its own.
- [x] **Move stage identity out of storage.** ✅ PR #14 — `SAMPLES_STAGE` and
      `INGEST_CODE_VERSION` are gone from `store/repo.py`, along with the Parquet codec.
      Name, code version, params and serialisation now live on the stage; `repo.save` is
      handed the key its payload landed under and only indexes it.

**Two things that changed and are worth knowing before writing L1:**

1. **A stage owns its serialisation, and its payload is self-describing.** `Stage` gained
   `encode`/`decode`, and the L0 payload carries the session — id, sport, fidelity, device,
   blind windows — in the Parquet file metadata alongside the sample columns. A cache hit
   must return exactly what a run returns, so decoding cannot depend on a SQLite row a
   cache-only re-run may not have. L1's payload has to hold to the same rule.
2. **L0 has a real param: `gap_tolerance`.** It was a module constant in `ingest/blind.py`,
   so changing it would have silently reused windows drawn under the old rule. It is now
   threaded through the parsers and lives in L0's cache key. L1's noise parameters belong
   in its key for the same reason.

### Then the kinematics — ✅ complete, PR #16

The spine is built, so L1 has somewhere to plug in. Two things block the smoother itself,
and they are in this order on purpose.

#### 1. Decide L1's output shape — plan mode, needs my approval

A data-model decision, so it does not get made in passing (`models.py` is a one-way door;
`CLAUDE.md` requires plan mode + sign-off). The question: where does a smoothed position
live?

| Option | What it means | Verdict |
|---|---|---|
| Overwrite `Sample.lat/lon/speed_ms` in place | simplest, reuses the L0 payload shape | **Reject.** A sample inside a blind window would carry a position indistinguishable from a measured one — exactly the failure rule 1 exists to prevent |
| **A parallel track**: new `SmoothedSample` (`t`, `lat`, `lon`, `speed_ms`, `confidence`, `observed: bool`), L1 returns `list[SmoothedSample]` | raw stays untouched; "was there a fix here" is explicit per sample; downstream joins on `t` | **Recommended** |
| Add `smoothed_*` fields to `Sample` | one row carries two provenances | Reject — mixes measured and estimated in the shape itself |

Note the tension to resolve while deciding: `Sample.confidence` is documented as *"1.0 until
L1 refines it"*, which reads as refine-in-place. Under the recommendation, the raw track's
confidence stays 1.0 and the refined number lives on `SmoothedSample` — so that docstring
needs correcting either way.

#### 2. The synthetic fixture cannot yet score a smoother

`make_synthetic_session` builds a true velocity profile, integrates it, then adds 3 m
Gaussian noise and dropout — and **throws the clean track away**. `SyntheticSession` exposes
only `activity` and `truth` (ride intervals). There is nothing to measure a recovered track
against, so "recovers to a stated tolerance" is not currently writable.

- [x] Carry the noiseless per-second `(x, y, vx, vy)` out on `SyntheticSession` alongside
      `truth`. ✅ PR #15 — `TrueState` per second on `SyntheticSession.true_track`, drawing
      no random numbers, golden unmoved. It also closed a hole: coverage, blind windows and
      truth intervals all fall out of the RNG *sequence*, so a changed speed profile moved
      nothing the gate checked. The track's aggregates are pinned in the golden now, and a
      mutation confirms they catch it.

#### 3. Then the smoother

- [x] Kalman filter + RTS backward smoother in `api/src/surf/pipeline/l1.py`, with
      `surf/geo.py` giving it a local metric frame to work in
- [x] Measurement model honesty: position updates only where a fix exists; `distance_m` is
      never used as dead reckoning
- [x] Confidence per second from the posterior covariance — `1/(1+(sigma/sigma_ref)^2)`,
      one knee, no cliffs. Fix availability enters through sigma rather than as a second term
- [x] `observed=False` marks every estimated second (ADR-0010)
- [x] Wired as an L1 `Stage` keyed on the L0 payload key, so a track cannot outlive the
      samples behind it. `repo.samples_key()` exposes that key for a stored activity
- [x] Tests: `tests/test_kinematics.py` (14), `tests/test_geo.py` (6), three chain tests in
      `tests/test_pipeline_spine.py`

**Measured, not asserted** — against `SyntheticSession.true_track`:

| | |
|---|---|
| RMS error where a fix existed | **1.84 m**, against the 3.0 m noise it was given — the smoother earns its place |
| RMS error inside blind seconds | 8.5 m, and it *must* be worse: an estimate is not a measurement |
| Confidence, observed vs blind | 0.98 vs 0.60 mean; 0.08 at the worst second |
| `process_noise = 0.25` | swept, not guessed: it minimises both position and speed error. Tuned on generated motion, so revisit against human labels in Phase 4 |

The sharpest test is `test_uncertainty_peaks_in_the_middle_of_a_gap`. Over the longest
70 s blind run, sigma runs 2.5 m at each edge and 24.4 m dead centre. A forward-only filter
peaks at a gap's *end*; only a backward pass peaks in its middle. If that test ever fails
with the maximum at the last index, the RTS pass has stopped running whatever else is green.

> **A caveat Phase 3 and 5 need.** On the *real* session the smoothed top speed reaches
> 11.55 m/s, just under ADR-0003's 12 m/s prior — but it is sensitive to an assumed
> parameter, not just to the data: at `measurement_noise_m` 3.0 / 5.0 / 8.0 the maximum is
> 11.55 / 10.41 / 8.50 m/s. The 3.0 m default is the synthetic's noise, and the real watch is
> probably noisier. **Do not build a feature that leans on absolute top-end speed** until
> Phase 4 labels can settle it. This is exactly why the parameter sits in the cache key.

> **A seam that is not yet closable.** No test spans ingest and `surf.evaluation`. That is
> not a Phase 2 gap: `evaluation` compares interval lists and has nothing to say about an
> `Activity` until a detector consumes one. It first becomes testable in **Phase 5**, and
> should be closed there rather than faked earlier.

---

## Phase 3 · Frame — next

**Goal:** a shore-relative frame per session, so a feature means the same thing at Sines as
anywhere else (ADR-0003), and a first pass at candidate intervals.

### What Phase 2 hands you

```python
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline import run_stage, stage_key

track = KinematicsStage().run(activity)          # list[SmoothedSample], one row per sample
```

| You get | Shape | Why it matters to L2 |
|---|---|---|
| `SmoothedSample.vx_ms` / `vy_ms` | m/s **east / north** | the rotation input. Do not difference positions again — the velocity is already estimated, and differencing throws away the smoothing |
| `SmoothedSample.observed` | bool | the measured/estimated line (ADR-0010). It has to survive into `WaveCandidate` |
| `SmoothedSample.confidence` | 0–1 | propagate it. A candidate built from estimated seconds is not as good as one built from fixes |
| `SmoothedSample.position_sigma_m` | metres | what we do not know, in metres. The UI will want this in Phase 6 |
| `surf.geo.LocalFrame` | `to_metres` / `to_degrees` | already exists; L2 should rotate within it rather than inventing a second projection |

### The chain pattern, which L2 must follow

L1 keys its output on **L0's key**, not on the activity id, so a track can never outlive the
samples behind it — `test_changing_an_l0_param_invalidates_l1_too` pins that. L2 keys on
L1's key for the same reason. `repo.samples_key(activity_id)` gets you the head of the chain
for a stored session.

Spine assertions go in `tests/test_pipeline_spine.py` next to L0's and L1's. That file is
deliberately one place.

### Decide before building

- [ ] **How is shore bearing estimated?** Candidates: principal axis of the position cloud;
      the mean direction of high-speed runs (rides go shoreward); the asymmetry between
      paddle-out and ride headings. The synthetic fixture has a **known** answer — shore is
      east, rides travel +x, paddle-outs −x — so whichever method you pick can be scored
      rather than eyeballed. Pick one, state the error you accept, pin it.
- [ ] **Is L2 one stage or two?** `docs/architecture.md` §3 lists L2 frame and L3 candidates
      separately. Keeping them separate means the frame can be cached and reused while
      candidate thresholds are swept, which is the whole point of the stage cache. Recommend
      two stages, but say so explicitly rather than drifting into one.

### Then build

- [ ] L2: estimate the bearing, rotate velocity and position into cross-shore / alongshore
- [ ] L3: high-recall candidate intervals — recall matters far more than precision here, the
      scorer in L5 is what tightens it
- [ ] `WaveCandidate.position_coverage` already exists on the model: fill it from `observed`
- [ ] Tests: bearing recovered on the synthetic to a stated tolerance; candidates achieve a
      stated recall against `SyntheticSession.truth` via `surf.evaluation.score`

**Done when:** L0→L1→L2→L3 all run as cached stages over the reference session, the frame is
recovered on the synthetic to a pinned tolerance, candidate recall is a number in the eval
gate, and `make check` is green.

> **Carry this warning forward.** The smoothed top-end speed on real data is sensitive to
> `measurement_noise_m`, which is currently the synthetic's 3.0 m and probably too low for
> the real watch. A candidate rule keyed on absolute peak speed would be tuned to that
> assumption rather than to surfing. Prefer shape — acceleration, duration, direction
> relative to shore — until Phase 4 labels can settle the noise level.
