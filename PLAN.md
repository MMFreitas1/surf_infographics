# Build plan

Cross-session source of truth. **Read this first after a `/clear`.**
Tick items as they land — an item is only ticked when it is verified, not when it is written.

---

## ▶ RESUME HERE

| | |
|---|---|
| **Tier** | 2 · approved 2026-08-28 |
| **Done** | Phase 0 — foundation, CI, diagnostics · **1** — ingest, storage, REST · **2** — pipeline spine, RTS-smoothed track · **3** — shore frame (L2), high-recall candidates (L3) · **4** — append-only labels, six endpoints, scrub UI, labels joined to the eval harness · **5 Pass 1** — L0.5 cleaner, two channels + odometer containment, top speed 74.8 → 54.1 km/h · **5 Pass 2 baseline** — L0.6 audit, the session found inside the recording · **7 resolver** — L4 features + L5 verdict, the pipeline now commits to a wave count (ADR-0017) · **7 metrics half** — L6, every per-wave number surfaced and the session's own aggregates, with the count unmoved by L6 · **6a** — the phase's premise measured and inverted, ADR-0022 and ADR-0023 (#68) · **6b** — a wave must be corroborated by the watch's own speedometer, **count 11 → 8** against Miguel's labels (#69) · **6c** — `surf.coast`, the committed GSHHG extract and `NOTICE` · **Session screen PRs 1–3c** — masthead, method banner, hero count, satellite track with playback, the four chart cards and the wave profile grid |
| **Order** | **Phase 5 (clean) → Session screen (design Level 2) → the rest.** Agreed 2026-09-15. Level 2 first because it is the screen the design leads with, holds all the machinery, and works with the one session that exists. Level 1 compares sessions and needs five of them for a surf level — it would be an empty state today. Cleaning comes first so no screen ever renders the 74.8 km/h artefact |
| **Stack** | Next 16 · React 19 · TS 7 · vitest 5 as of PR #29. Route `params` are a Promise — `tsc` does not catch that, only running it does |
| **Next** | **Phase 6 — shore & peaks**, re-planned 2026-10-24 after measuring it. **6a, 6b and 6c are in.** The phase's premise was false twice over: ADR-0011's axis is **right to 4.2°**, and the real defect was the **count** — three of eleven waves were the smoother bridging a blind gap, now refused by the device's own speedometer (ADR-0023), so the reference session reports **8**. `surf.coast` now serves the shore angle from a committed 259 KiB GSHHG extract. Remaining: **6d** L2 re-estimated with two witnesses and L1.5 peaks beside it, **6e** left/right end to end at a ±8° straight band. **The shore line is never drawn** — only its angle is used |
| **Design built** | **PR 1 of 3 landed 2026-09-30** — `web/src/app/session/[id]`, tokens in `globals.css`, catalogues in `web/src/lib/i18n/`. Two rules to keep: **no string literal in a component** (`Messages` is a closed type, so `tsc` catches a missing key), and **"proposed" is said once**, in the method banner — a test fails if the word appears on an individual figure. The banner's copy departs from the prototype on purpose: the design said an LLM cleans the data and infers the numbers, and ADR-0016/0017 mean it does not |
| **Design** | ✅ **Landed 2026-09-15** — high-fidelity, all three levels, in `design_handover/design_handoff_surf_analytics/`. Read its `README.md` (28 KB) before building any UI. It supersedes `DESIGN_BRIEF.md`, which was the input to it |
| **Local LLM** | ✅ **Installed and verified** — Ollama + `qwen2.5:7b-instruct-q4_K_M` + LiteLLM gateway, all under `/Users/Shared/llm`. 13 tok/s measured; a 100-token pass ≈ 8 s. See "Local LLM stack" below |
| **Re-planned** | 2026-08-31 — the product is a **three-level drill-down** (Sessions → Session → Wave), specced by Miguel and merged below. The labelling gate is dropped (ADR-0013): every derived number ships marked *proposed*, and validation waits for a session labelled the day it is surfed |
| **Health** | `make check` → 755 tests green (557 api · 139 web · 59 evals); 25 api tests skip without `sample_data/`, and 6 eval cases need Ollama and skip unless `SURF_LLM_EVAL=1`. `make labels` reports on human labels and gates nothing |
| **Repo** | **PUBLIC** — `sample_data/` and `data/` are gitignored; never commit GPS traces. `web/verification/` too: those screenshots show a real track |

**Orient in four commands:**
```bash
make check                 # everything CI runs
make labels                # what the human labels say — empty until a session is labelled
cat docs/architecture.md   # component map + one-way doors
ls docs/adr/               # why each decision was made
```

> **"Reference session" means two different things in this file.** Phase 1 uses it for the
> real FIT recording in `sample_data/` (3790 samples, 48.8% coverage); Phases 2–3 use it for
> the seeded `surf.synthetic` session pinned in `evals/goldens/`. Where a number could be
> either, this plan now says which.

**Three rules that override convenience** (full list in `CLAUDE.md`):
1. Never present an imputed wave as measured. Detected / uncertain / blind are three states.
2. The pipeline consumes only first-party recorded signal (ADR-0008).
3. No ground truth, no quality claim — so make **no accuracy claim at all** until a session is
   labelled the day it is surfed (ADR-0013). Wave counts, speeds and levels ship marked
   *proposed*. "12 waves" is a reading of the data, never a measured fact, and the UI says so.

---

## Phase checklist

- [x] **0 · Boot** — conventions, architecture, ADRs, scaffold, CI, test + eval harness, local diagnostics
- [x] **1 · Ingest** — FIT/GPX/TCX → canonical `Activity`, fidelity-tagged, golden tests, stored
- [x] **2 · Kinematics** — Kalman + RTS smoother, blind windows, propagated confidence
- [x] **3 · Frame** — shore-bearing estimation, cross-shore/alongshore transform, candidate generation
- [x] **4 · Labeling UI** — scrub a session and mark waves, from raw signal
- [x] **5 · Clean signal** — ✅ Pass 1 (L0.5, cleaner) · ✅ Pass 2 baseline (L0.6, audit) · ✅ Pass 2 LLM measured and rejected (ADR-0016)
- [ ] **6 · Shore & peaks** — where you sat, where the coast runs, and therefore left vs right
- [ ] **7 · Wave metrics** — transparent scorer, then duration / speeds / manoeuvres / straightness per ride
- [ ] **8 · Marine context** — swell 1–4, wind, sea temperature, combined energy
- [ ] **9 · Session view** — the GPS graph with wave selection and playback, cards, radial, aerobic block
- [ ] **10 · Sessions tab** — progression, % change chips, surf level, correlation plots
- [ ] **11 · LLM passes** — three prose commentaries, context budget and cleanser

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

## Standing hypothesis — settle whenever a session is labelled fresh

GPS dropout is caused by wrist submersion. While *riding*, a surfer stands with the wrist clear
of the water, so GPS should **recover** during a genuine wave. If it holds, position availability
becomes a strong positive feature.

Deliberately **not** baked into `surf.synthetic` — its dropout is state-independent, so a detector
cannot score well by learning an assumption we have not confirmed. Needs human labels to settle,
and `make labels` answers it the moment one session is labelled. Not on the critical path any
more (ADR-0013): the product ships without it, marked *proposed*.

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

### Found by the loop — 2026-09-17

Both surfaced while verifying Phase 5's odometer fix, neither caused by it, and neither
folded into an unrelated PR. The first is fixed; the second is still open.

- [x] **SQLite reads are not serialised, and the label page trips it.** ✅ Fixed 2026-09-17.
      Worse than the log showed: reproduced at **17 failures in 960 concurrent reads**, in four
      flavours, and only one of them was the `InterfaceError` the buffer caught. The other
      three were *silently wrong data* — a blind window whose `cause` came back NULL, a summary
      whose counts came back NULL, and a `samples_key` read from the wrong row, which surfaces
      as "samples are missing from the stage cache": a report of data loss that had not
      happened. Both repositories now take an `RLock` on **every** access, reads included, with
      the Parquet decode deliberately left outside it. Four regression tests, each verified to
      fail against the old code.
- [x] **`make verify` flakes on a cold Next dev server.** ✅ Fixed 2026-09-30, in two goes.
      It was *not* the per-test timeout — `ui.spec.ts` has set `test.setTimeout(180_000)`
      since PR #20. Two ceilings were actually being hit, and fixing only the first left the
      flake alive: Playwright's **navigation** timeout (30 s default, unset) *and* its
      **expect** timeout (5 s default, unset). With navigation fixed, `page.goto` waits out
      the compile, returns, and hands the first assertion a page still hydrating with 5 s to
      find anything in it. Caught by the label spec failing cold then passing warm on the
      next run — the same shape as the original report, which is how a partial fix hides.
      Both are set explicitly now, with the reasoning beside them.
- [x] **maplibre's worker never loaded, on every map.** ✅ Fixed 2026-10-21, found the first
      time the UI was opened after the dependency sweep. maplibre 6.11 ships the worker as a
      module that imports a sibling chunk and locates itself from `import.meta.url`; Turbopack
      bundles the library into a hashed chunk, so the worker resolved to a
      `/_next/static/chunks/` path that was never emitted. **CI could not have caught it** —
      lint, types, unit tests and `next build` are all green with a dead worker, and the style
      is raster-only so the map still draws. Only `pnpm run verify` saw it, on all five specs
      that mount a map. `scripts/copy-maplibre-worker.mjs` copies the worker and its chunk into
      `public/` before dev, build and test, and `src/lib/maplibre-worker.ts` names that URL
      through `setWorkerUrl`. Copied from `node_modules` rather than vendored so the worker can
      never be a different version from the library.

## Deferred, with reasons

| Item | Why | Unblocks when |
|---|---|---|
| Ollama + quantized model | not needed until Phase 8 | Phase 8 |
| Playwright in CI | needs a browser download in the runner; runs locally today | Phase 9, if warranted |
| **ML detector** (gradient-boosted trees) | cannot be trained, let alone validated, without labels — and a model fitted to L3's proposals would only learn L3 | a labelled session exists |
| **LLM adjudicator** on the 0.15–0.85 band (ADR-0005) | distinct from the three prose passes in Phase 11. Adjudicating needs a calibrated score to have a band *of*, which needs labels | a labelled session exists |
| Tide | Open-Meteo Marine covers swell and wind; tide needs a second source | Phase 8, if the sea-state cards want it |
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

## Phase 3 · Frame — ✅ complete

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

### Decided before building — both approved 2026-08-30, recorded in ADR-0011

- [x] **Shore bearing: speed-weighted velocity.** `û = normalise(Σ confidence·|v|^k · v̂)`.
      Speed is only ever a *relative* weight between seconds of one session, so scaling every
      velocity leaves the bearing exactly unchanged — which is what makes it immune to the
      `measurement_noise_m` caveat below. Rejected: PCA of the position cloud (infers
      direction from where the surfer *sat*, and cannot tell shoreward from seaward);
      heading bimodality (needs many waves, and few-wave sessions are the hard case).
- [x] **Two stages, L2 and L3.** As `docs/architecture.md` §3 already had it: the frame
      caches once and is reused while candidate thresholds are swept.

### Then build

- [x] L2: estimate the bearing, rotate velocity and position into cross-shore / alongshore
      ✅ PR #17 — `pipeline/l2.py`, `tests/test_frame.py` (15), 4 chain tests in the spine,
      2 in the eval gate
- [x] L3: high-recall candidate intervals ✅ — `pipeline/l3.py`, `tests/test_candidates.py`
      (15), 4 chain tests in the spine, 3 in the eval gate. Threshold is a quantile of the
      session's **own** cross-shore speed, so no absolute m/s appears anywhere
- [x] `WaveCandidate.position_coverage` filled from `observed` — and it earns its place:
      2 of the 9 proposals on the **synthetic** session are built entirely from estimated
      seconds and report 0.0. (Phase 4 measured the real FIT session for the first time:
      **22 proposals**, 2 at zero coverage and 8 more under 25%. See ADR-0012.)
- [x] Tests: bearing to a stated 5° tolerance; candidate recall in the eval gate as **two**
      numbers, because one would have been misleading — see below

**Done when:** L0→L1→L2→L3 all run as cached stages over the reference session, the frame is
recovered on the synthetic to a pinned tolerance, candidate recall is a number in the eval
gate, and `make check` is green. — **all met.**

### What L3 measured, and the number that would have lied

| | |
|---|---|
| Recall on rides the smoother could **see** (≥50% position coverage) | **1.000** — every seed tried, every quantile tried |
| Recall over **all** rides | 0.750 on the reference session |
| Precision | 0.667, recorded and **not gated**: L5 tightens it, and a ride never proposed here cannot be recovered later |
| `quantile = 0.75` | swept over seven seeded sessions. Mean recall is flat at 0.821 from q=0.70 to q=0.75 and falls away above; below 0.75 only costs precision for recall already saturated |

The gap between those first two numbers is the whole finding. The rides L3 misses are the
ones that were **mostly blind** — on the reference session, one 33% observed and one 12%,
where the RTS pass has no position evidence and damps the track toward stillness. Their true
top speeds were 4.1 and 8.0 m/s; the smoothed track shows 0.9 and 1.2.

So "recall = 0.75" is a statement about the *fixture*, not about the rule, and reporting it
alone would have quietly attributed a data limit to the detector. The eval gate asserts both,
and `test_every_ride_the_candidates_miss_was_one_the_smoother_could_not_see` fails loudly if a
**well-observed** ride ever goes missing — which is the only version of this that is a bug.

> **This makes Phase 4 more urgent, not less.** The standing hypothesis says GPS *recovers*
> during a ride, because the wrist comes clear of the water. If it holds on real sessions,
> these blind rides are an artefact of `surf.synthetic`'s deliberately state-independent
> dropout, and the real ceiling is higher than 0.75. If it does not hold, a mostly-submerged
> ride may be genuinely undetectable from GPS alone and that is a product fact worth knowing
> early. Human labels settle it; nothing before Phase 4 can.

### What L2 measured

| | |
|---|---|
| Bearing error on the synthetic | **0.51°** against a known due-east shore, tolerance 5° |
| Exponent `k` | **4.0**, swept. At k=2 a one- or two-wave session points *seaward* (+154°, −172°); at k=4 those fall to +24° and −13°, and every session with ≥3 waves lands within 3.6° |
| Reliability | two guards, because one is not enough. `coherence ≥ 0.85` catches votes that disagree; **Kish effective sample size ≥ 5.0** catches votes that agree only because one second holds all the weight — a single 6 m/s spike in an aimless session scores 0.90 coherence off an effective sample of 1.25 |
| Verified | the two guards accept exactly the sessions inside the 5° tolerance and reject every one outside it, across a 1–12 wave sweep |

Three deliberate mutations were run against the tests: dropping the effective-sample guard,
reverting `k` to 2.0, and flipping the alongshore axis. The first two were caught
immediately; the third was **not**, because the handedness test recomputed the axes from the
bearing instead of checking the stage's output. That test was rewritten to assert against a
known heading, and now catches it. Worth remembering: a test that derives its expectation
from the code under test agrees with that code whatever it does.

> **Still carried forward.** The smoothed top-end speed on real data is sensitive to
> `measurement_noise_m`, which is currently the synthetic's 3.0 m and probably too low for
> the real watch. A candidate rule keyed on absolute peak speed would be tuned to that
> assumption rather than to surfing. Prefer shape — acceleration, duration, direction
> relative to shore — until Phase 4 labels can settle the noise level.

---

## Phase 4 · Labeling UI — ✅ complete

**Goal:** a person scrubs a real session and marks where the waves were, from raw signal.
This is the phase everything after it depends on: no ground truth, no quality claim.

### What Phase 3 hands you

```python
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FrameStage
from surf.pipeline.l3 import CandidateStage

framed = FrameStage().run(KinematicsStage().run(activity))   # FramedTrack: frame + samples
proposed = CandidateStage().run(framed)                      # CandidateSet: frame + candidates
```

| You get | Why it matters to the UI |
|---|---|
| `SessionFrame.reliable` | on a low-coherence session the cross-shore axis is not trustworthy, and the UI must not draw a confident shore line over it (ADR-0011) |
| `FramedSample.observed` | the measured/estimated line (ADR-0010). **The UI has to render this**, or a labeller marks an interpolated stretch believing they saw it |
| `FramedSample.position_sigma_m` — via the L1 track | what we do not know, in metres. This is the "render what we do not know" requirement in `CLAUDE.md` |
| `WaveCandidate.position_coverage` | On the **real** session L3 proposes 22 intervals: 2 built entirely from estimated seconds, 8 more under 25% coverage. Those are exactly the ones a human should be asked about. (The "9 proposals" in Phase 3 is the *synthetic* session — ADR-0012 records the difference) |

### Decided before building — all three approved 2026-08-30, recorded in ADR-0012

- [x] **Are L3's candidates shown to the labeller?** → **blind pass first, assisted second.**
      Candidates are not fetched until a blind pass is recorded; assisted labels are stored
      `human_assisted` and excluded from `counts_as_truth`. Enforced in the store and the
      endpoints, not in the UI. This is the sharp one. Showing them
      makes labelling far faster; it also means human labels inherit the detector's blind
      spots, and a detector then scored against them would be grading its own homework.
      That is ADR-0008's objection — *their errors, no information* — arriving from inside
      the project rather than from a third party. Options: label blind; label blind then
      reveal candidates for a second pass; or record `WaveLabel.source` and keep
      candidate-assisted labels out of the metric. **Recommend labelling blind for the first
      session at minimum**, so there is an unanchored set to measure the assisted ones
      against.
- [x] **What does the labeller actually see?** → **all three, plus the map.** Speed,
      cross-shore velocity, position uncertainty in metres, and the track. Measured solid,
      estimated dashed, blind hatched, in every panel at the same x.
- [x] **Storage and API shape.** → `labels` + `label_passes` (schema v2), six endpoints, a
      Zod mirror per shape and `labeling_contract_v1.json` checked from both sides.

### Then build

- [x] `labels` table + repo, append-only; corrections are new rows, never updates ✅ PR #19
- [x] Six endpoints: track, candidates, labels (POST/GET), label-passes (POST/GET) ✅ PR #19
- [x] Zod contract parity with a committed fixture, drift verified both ways ✅ PR #19
- [x] The scrub UI itself, with measured/estimated rendered differently ✅ PR #20
- [x] Human labels join the eval harness next to `surf.synthetic` — `truth_intervals` feeds
      the same `surf.evaluation.score`, so a real precision/recall is now possible ✅ PR #21

**Done when:** a real session can be labelled end to end, the labels survive a restart, they
are readable through the API in the canonical shape, and `make check` is green.
— **all met.** Verified in a browser against a scratch store: two blind labels saved,
candidates absent until the pass was recorded, 22 proposals revealed after, an assisted label
excluded from truth, and a correction leaving the original row in place.

### What building it turned up

| | |
|---|---|
| The real session's frame is **not reliable** | coherence 0.365 against a 0.85 threshold. The "we cannot tell where the shore is" path is the *default* on real data, not an edge case. Phase 3's 0.51° error was the synthetic, where rides dominate the velocity sum |
| L3 proposes **22** intervals on the real session | not the 9 quoted for the synthetic. 2 at zero coverage, 8 more under 25% |
| **381 separate blind windows** | blindness on real data is shredded, not blocky. Heavy hatching covered the whole chart and had to be lightened to stay readable |
| No CORS anywhere in the API | the UI could not call it at all, and the failure hid itself by blocking the error-reporting call too. Found by running it, not by reading it |
| Observable Plot deletes its container's children | `replaceChildren` wiped the React overlay — the drag surface and every band. Plot gets its own node now |
| `deck.gl` the umbrella pulls `@arcgis/core` + a Vaadin package that phones home | scoped `@deck.gl/{core,layers,react}` instead. `architecture.md` §6 |

### Still owed by a person, not by the code

- [ ] **Label the reference session.** Nobody has yet. The tooling is finished and `make
      labels` will answer the standing hypothesis the moment a session is labelled — but the
      labels themselves cannot be generated, only made. Inventing them would be exactly the
      fabricated ground truth this whole phase exists to avoid.

> **The first thing to check once labels exist.** The standing hypothesis: GPS *recovers*
> during a ride, because the wrist lifts clear of the water. `surf.synthetic` deliberately
> does not model it, and Phase 3 measured the consequence — every ride L3 misses is one that
> was mostly blind. If real labelled rides turn out to be *better* observed than the session
> around them, position availability becomes a strong positive feature and L3's ceiling rises
> on its own. Settle this before tuning anything else.
>
> **`make labels` is that check**, built in PR #21. It reports coverage inside labelled rides
> against coverage across the session, and refuses a verdict below 5 rides — three rides can
> point anywhere. It reports; it does not gate, because the answer is a property of the sport
> and the watch, not of our code.

---

## Product shape — the drill-down

Specced by Miguel 2026-08-31. Three levels, each narrowing: **Sessions → one Session → one
Wave**. Full screen-by-screen detail for design work lives in [`DESIGN_BRIEF.md`](./DESIGN_BRIEF.md);
what follows is what has to be *computed* to fill it.

| Level | Question it answers | Where the intelligence sits |
|---|---|---|
| **Sessions** | am I getting better? | % change against previous, surf level, trends, 3D correlation |
| **Session** | how was that surf? | wave count, sea state, aerobic load, distance, device confidence |
| **Wave** | how was that ride? | duration, direction, speeds, manoeuvres, straightness, HR |

Every level carries an LLM prose comment (Phase 11) and a correlation plot the user drives.
Context is kept **per level**; only Sessions may read all three.

---

## Phase 5 · Clean signal — ✅ complete

**Goal:** no impossible number reaches a chart. Correctness over speed — a five-minute local
LLM pass is acceptable if it is right.

**What the reference session actually contains**, measured 2026-08-31:

| | |
|---|---|
| Raw top speed | **74.8 km/h**. A surfer does 25–35 |
| Fixes over 40 km/h | 24 (1.30%) · over 50 km/h: 16 (0.87%) |
| `hr_bpm`, `temp_c`, `distance_m` | **100% coverage** — they survive the blind half |
| `distance_m` while blind | **frozen**: 0 m across 1,941 blind seconds. The 3.7 km total counts only the 1,848 seconds the watch saw |

### What Pass 1 measured, and the premise it corrected — ✅ landed 2026-09-17

Two things the plan above got wrong, both found by measuring before building:

1. **The position rules do not fix the top speed.** L1 already gates fixes at 12 m/s by
   inflating their variance, so rejecting them upstream moves the smoothed top speed 11.55
   → 11.56 m/s. Nothing. The map spikes and the coverage lie were real; the 74.8 km/h was
   never a position artefact.
2. **The 74.8 km/h lives in the speed field**, at +3195…3262 s, where the positions say ~1 m/s
   and HR reads 110. So Pass 1 needed a **second channel**: the recorded speed checked against
   the device's own odometer (`distance_m`, 100% coverage) or, failing that, against the fixes
   bracketing it. Two channels, and therefore two effects — a demotion moves coverage, a
   dropped speed reading does not, because coverage must tell the truth in both directions.

| Measured on the reference session | Before | After |
|---|---|---|
| Readings above 54 km/h | 12 | **3** |
| Second-highest recorded speed | 74.7 km/h | **54.1 km/h** |
| Top recorded speed | 74.8 km/h | **74.5 km/h** |
| Position coverage | 48.79% | **48.13%** |
| Worst single-second jump | 109 m/s | **≤ 18 m/s** |

43 rejections: 24 `implied_speed`, 1 `implied_acceleration`, 18 `speed_vs_odometer`.
`jump_and_return` fires **zero** times on real data and once on an injected artefact — it
ships tested but unexercised, and the ADR says so rather than implying it earns its place.

**The top speed is the honest part.** One fix survives because all three channels agree it was
fast. It is one second inside a minute of someone walking up the beach, and refusing a
*stretch* is Pass 2's job — so **Phase 5's Done-when is met when Pass 2 lands, not now.**

- [x] **Pass 1 — programmatic, deterministic, in the pipeline.** Reject a fix on physics, before
      L1 smooths it: implied speed from the previous accepted fix over a plausibility ceiling,
      acceleration over a ceiling, a jump-and-return inside one second. Rejection is a
      *demotion to blind*, never a deletion — the second becomes `observed=False` and the
      smoother estimates it like any other gap, so coverage tells the truth.
      **Plus the speed channel the measurements above forced** (ADR-0014).
      Ceilings are swept against the synthetic truth, not asserted: 18 m/s rather than L1's 12
      because L1 *softens* a fix and this stage *removes* one, and 12 demotes 3–7 genuine ride
      seconds per session.
### What Pass 2's baseline measured — ✅ landed 2026-09-17

The LLM was never going to be what fixed the top speed; a missing arithmetic check was, and
it landed in Pass 1. What Pass 2 is actually for is the **session inside the recording**. The
reference file is 63.2 minutes long and its last 7.2 are the watch on the sand — coverage 1.00
at zero speed. Session duration, distance ridden and waves per ten minutes are all wrong if
they count the walk back.

**Coverage is the signal, and the inversion is the point.** In-water windows average **0.39**;
dry ones sit at **1.00**. The hard thing about this data is what makes this easy.

| Reference session | |
|---|---|
| Recording | 63.2 min |
| Session | **55.0 min** (t+60 … t+3360) |
| Excluded | 60 s before entry · 430 s after exit, at confidence 0.7 |
| Top speed, all vs session | 54.1 km/h vs **54.1 km/h** — unchanged, and the report says so |

**Two things the first implementation got wrong**, both caught by known truth rather than by
review: "longest contiguous wet stretch" returned an 11-minute session out of 63, because a
surfer sitting up with a dry wrist reads exactly like one on the sand; and trimming on
coverage alone cut a real ride out of **three of five** seeded sessions, because a rider
standing up has the driest wrist in the file. The rule now trims inward from the ends only,
and only where a window is **dry *and* slow**. Zero rides lost across all five seeds.

**Truth had to be built.** Nobody can mark from memory which minute they walked out of the
sea — the same problem ADR-0013 records for waves. `surf.synthetic` gained an opt-in
out-of-water tail with exactly known bounds, drawing from its own RNG so every committed
golden stays valid. The baseline recovers it to within one window.

- [x] **Pass 2 baseline — deterministic, the thing the LLM has to beat.** L0.6, hanging off
      L0.5 *beside* L1 rather than beneath it, because the audit changes no sample and must
      not invalidate the track. Exclusion, never demotion: the samples keep their position and
      stay `observed` ([ADR-0015](./docs/adr/0015-not-surfing-is-excluded-not-demoted.md)).
      `GET /activities/{id}/audit`, Zod mirror, contract golden both sides, 29 tests.
- [x] **Pass 2 LLM — measured, and it does not ship.** ✅ 2026-09-21,
      [ADR-0016](./docs/adr/0016-the-local-model-does-not-ship-for-the-session-audit.md).

      | contender | F1 | interior recall | ride seconds destroyed | time |
      |---|---|---|---|---|
      | **baseline** | **0.63** | 0.00 | **0** | ~0 s |
      | `llm:reasoned` | 0.07 | 0.40 | 181 | 304 s |
      | `llm:ruled` | 0.45 | 0.80 | 110 | 363 s |

      Two independent disqualifications. Neither variant beats the baseline on F1 — the one
      that matters, the model reasoning from the physics itself, scores **0.07 against 0.63**,
      closer to anti-correlated with the truth than merely weak. And both **destroy real
      surfing**: 181 s and 110 s of genuine rides against the baseline's zero. Run twice at
      temperature 0 with a fixed seed, F1 came back identical to four decimal places while the
      destroyed seconds moved — the verdicts are stable, the span edges are not, which a
      content-addressed pipeline cannot hold to its reproducibility promise.

      ADR-0005 scopes the LLM to the *ambiguous band*, and here that band is nearly empty:
      coverage is 0.39 in the water and 1.00 out of it, with nothing between. The `ruled`
      control scoring *better* than `reasoned` is the tell — the model is pattern-matching a
      rule it was handed, not reasoning, and a rule the baseline already runs perfectly in
      microseconds rather than 50 seconds a session.

      **What it did find, recorded honestly:** `ruled` reached 0.80 interior recall where the
      baseline scores 0.00. That gap is real. The next attempt on it should be a
      *deterministic* interior rule — high coverage, low speed, and a **falling** heart rate,
      which is what separates resting on the sand from sitting on a board — measured against
      the same harness before anyone reaches for a model again.

      The harness is the durable part: `evals/test_llm_audit.py` holds a `SHIPS` list,
      currently empty, so a future contender clearing both bars turns the eval red and names
      what changed rather than shipping quietly.
- [x] Both passes are **stages** (L0.5 and L0.6), cached and content-addressed like everything
      else, so a threshold sweep is a cache key and not a re-ingest. L0.5's invalidation
      travels down to L1/L2/L3; L0.6's deliberately does not, because it changes no sample.
      Both pinned in `test_pipeline_spine.py`.
- [x] Every rejection is recorded with its reason, its effect and the two magnitudes that
      convicted it, and served from `GET /activities/{id}/cleaning`. **No coordinates** — this
      repo is public and the records reach committed goldens. Drawing it as a *device
      confidence* card is Phase 9's job; making it queryable was this one's.
- [ ] `.env`: `SURF_LLM_HOST` (local, exists) and a hosted fallback endpoint for users with no
      local model. Local is the default; hosted is opt-in and never automatic — activity files
      are personal location history.

**Done when:** top speed on the reference session is physically plausible ✅ *(74.8 → 54.1 km/h;
what remains is a real ride whose speed field over-reads ~1.6× against its own odometer — a
Phase 7 calibration question, not a cleaning one)*, the count and reason of every rejection is
queryable ✅, `make check` is green ✅, and turning the cleaner off is a one-line parameter
change that the cache key notices ✅ (`CleanStage(enabled=False)`).

**Where it landed:** `api/src/surf/pipeline/clean.py` and `audit.py` (the two stages) ·
`api/tests/test_clean.py`, `test_cleaning_api.py`, `test_audit.py`, `test_audit_api.py`
(72 tests) · `evals/goldens/{cleaning,audit}_contract_v1.json` (contracts, both sides) ·
[ADR-0014](./docs/adr/0014-rejection-is-demotion-not-deletion.md) and
[ADR-0015](./docs/adr/0015-not-surfing-is-excluded-not-demoted.md).

---

## Phase 6 · Shore & peaks

**Goal:** left or right, per wave — an axis the pipeline will stand behind, and a wave count
that only counts waves the watch corroborates.

**The premise this phase was planned on turned out to be false, and measuring first is the
only reason we know.** ADR-0011's bearing scored 0.51° on the synthetic and returned
`coherence 0.365, reliable=False` on the real session, so the plan was to replace it. It is
**right to 4.2°**. Coherence measures whether the per-second votes agree *with each other*,
not whether their sum is correct, and on a session four-fifths paddling they disagree even
when it is. The axis was never the problem.

**The count was.** Miguel labelled the session on 2026-10-24 — the first ground truth this
project has had — and **three of the eleven settled waves are not waves**. Two of them are
the same artefact: a blind stretch ends, the watch dumps its accumulated odometer distance in
one 1-second step, and the smoother bridges the position gap with a curve shaped exactly like
a ride. The evidence that refutes them was already in the file, and nothing downstream read it.

Five PRs, in order:

- [x] **6a — land the measurements** (#68). Docs only. This section, plus
      [ADR-0022](./docs/adr/0022-the-shore-axis-has-two-witnesses.md) (two witnesses for the
      axis; agreement replaces coherence as the gate) and
      [ADR-0023](./docs/adr/0023-a-wave-must-be-corroborated-by-the-speedometer.md) (a wave
      must be corroborated by the device's own speedometer).
- [x] **6b — the watch has to back the story up.** L4 measures `speed_corroboration`, L5
      refuses below **0.65**, L3 untouched and still high-recall. A span with no speed reading
      is **not judged and gains no numbers** — it is a wave that publishes neither speed nor
      direction. The cutoff's default lives in code and `SURF_WAVE_SPEED_CORROBORATION`
      overrides it, with the **resolved** value in the stage params so the cache key stays
      honest. **Count 11 → 8, measured.** All eleven of Miguel's labels reproduce: eight
      kept, three refused, the one span the watch missed abstained on. The 0.4-0.7
      plateau holds in the real stages and 0.8 starts cutting a genuine wave.
- [x] **6c — `api/src/surf/coast.py` and the committed extract.** GSHHG 2.3.7 full, clipped to
      mainland Portugal, under 1 MB, read with stdlib `json`; `NOTICE` carries its LGPL v3+
      terms. `segment_near()` resamples at fixed spacing; `fit_bearing()` is **total least
      squares**, because a north–south coast has infinite slope in OLS. Returns an angle mod
      180° and nothing else. The file's sha256 travels into L2's params. **Measured: 259 KiB,
      12,254 vertices, and it reproduces the 165.3° fit to 0.03°.** It is also far less
      window-sensitive than the OSM measuring stick — 3.0° of swing across 200–2000 m
      against OSM's 20.6° — because the coarser spacing smooths the local wiggles, so the
      declared ±1 km window is not a knife-edge.
- [ ] **6d — L2 re-estimated, and L1.5 peaks beside it.** Two chains: the **angle** from
      coastline → velocity → none, the **sign** from the walk → ride majority → none.
      `reliable` becomes agreement within 25°. L0.6's key travels in L2's **params**, as at L6
      (ADR-0015). `PeaksStage` hangs off L1 **beside** L2 — it is for sit-spots, not for the
      frame. `CODE_VERSION` bumps; the count does not move.
- [ ] **6e — left or right, end to end.** L4 measures alongshore travel and the angle off
      dead-shoreward; L6 publishes `direction` + `direction_confidence`; straight band **±8°**.
      Sit-spots on the map, direction on the wave cards. **No shore line** — there is no
      waterline we can place.
- [ ] **Enter Miguel's eleven labels through the labelling UI**, not into a fixture by hand.
      The store is append-only and pipeline-immutable (ADR-0006), and the first labels the
      project has should go in the way every later one will.

**Done when:** the reference session reports **8 waves — 7 rights, 1 blind, 0 straight, 0
lefts** — each direction with a stated confidence, the three refusals named with their ratios,
and the axis under all of it carrying two independent witnesses.

### Measured before building — 2026-10-22

Per *measure before building a numeric phase*: the stationarity premise was probed on the
reference session before any Phase 6 code exists. **It holds.** Greedy clustering of the
**observed** seconds only — a cluster extends while every member stays within 20 m of its
running centroid — then keeping clusters lasting at least 60 s:

| | |
|---|---|
| Session, after the audit | 3300 s · 1334 observed (40.4%) |
| Clusters within 20 m | 61 |
| …lasting ≥ 60 s | **11** |
| Time held still | **1366 s — 41.4% of the session** |
| Peak centroids, pairwise | **4–125 m apart** |

Three things that fall out of it, all of which are Phase 6's to decide:

1. **A duration floor is not enough.** Peak 11 lasts 170 s on **10 observed seconds**, and
   peaks 7 and 2 are nearly as thin. A stretch the watch barely saw is not evidence of
   sitting still — it is evidence of nothing. The rule needs an observed-seconds floor as
   well as a duration one, or it will site a peak on an estimate.
2. **This session has one peak area, not several.** 4–125 m between centroids is one bank,
   so the eleven clusters want merging before anything regresses a coastline through them.
   The classifier must handle both shapes: a session at one peak and a session drifting
   between three are different objects.
3. **20 m is doing work.** Cluster spread runs 11–20 m, up against the radius, so the first
   build step is a sweep over radius and duration rather than shipping the first pair that
   looked right.

### Measured before building — part 2, 2026-10-24

The 2026-10-22 probe was reproduced exactly (11 clusters, 1366 s, 41.4%) and then taken
apart. Scripts were throwaway; these are the numbers.

**The peak rule.** Three findings change it:

- **`spread_max` equals the radius at every radius.** Greedy hard-radius clustering always
  saturates, so spread is not a signal and must not be reported — publishing it would be
  publishing the parameter back. Caveat 3 of the first probe is answered: 20 m was not
  "doing work", it was being echoed.
- **A fraction floor separates better than an absolute one.** Observed fraction per cluster
  runs 0.06 … 0.75, median 0.41 against the session's own 0.40; the 170 s cluster built on 10
  observed seconds is a clear outlier at 0.06. At 20 m / 60 s / ≥ 0.25 → **8 clusters**.
- **The parameters are not load-bearing.** The observed-weighted anchor moves ≤ 24.9 m across
  48 parameter sets (median 9.4 m). One peak area at every merge distance ≥ 50 m — one bank,
  not eleven peaks, as the first probe suspected.

**The axis has two witnesses, 4.2° apart** — see
[ADR-0022](./docs/adr/0022-the-shore-axis-has-two-witnesses.md) for the full table. In short:
GSHHG agrees with OSM to **0.2°**; the **window is the dominant lever, not the source** (OSM
runs 142.0° at ±200 m to 168.7° at ±1500 m, so it is pinned at ±1000 m); Natural Earth's 4.3 m
residual is a **false confidence signal**, so residual cannot be the gate; and **no static
file can settle handedness** — GSHHG places the anchor *inside* its land polygon.

**The sign comes from the walk.** Across the 60 s before entry and the 430 s after exit,
**all 489 observed walking seconds fall on one side with no exceptions** — median +40 m and
+287 m against a session spanning −140 to +198 m. Land is the positive side, 164 m of
separation. Ride majority is the weaker fallback: 7 of 10 fast runs, +301 m net.

**Only the angle is used, and the line never draws.** Miguel's call, and it is what makes a
coarse source viable: GSHHG puts the sit spot 15 m **inland** and Natural Earth 549 m **out to
sea**, and neither error reaches the arithmetic. All five candidate angles — spanning 23.3° —
gave the same left/right call on all ten fast runs.

**The axis does not move the count.** Eleven waves at every plausible angle (52.0° through
78.7°); only a deliberately bad ±200 m fit gives 12.

### Miguel's labels, 2026-10-24 — the first ground truth

| Ride | Call | In his words |
|---|---|---|
| 1, 2 | wave | "trimming, waiting for the wave to form, already standing" |
| 3, 4, 5, 6, 9, 11 | wave | a right-hand point; all rights |
| 7 | **not a wave** | "didn't happen, too far out from the peak" |
| 8 | **not a wave** | "me trying to wait for the mellow wave to form a wall, but it didnt" |
| 10 | **not a wave** | "didn't happen, too far out from the peak" |

**The clean cut — does the watch's speedometer ever reach what the track claims?**

```
waves       0.79  0.85  0.86  0.93  0.94  0.95  0.97     (ride 2 has no speed reading at all)
artefacts   0.00  0.15  0.38
```

**Every cutoff from 0.4 to 0.7 gives 3 of 3 artefacts refused and 8 of 8 waves kept.** It must
be peak against peak; second by second the gap closes to 0.01 and separates by luck.
`position_coverage` does **not** separate them at all (a real wave at 37% and 0%, an artefact
at 43%), and neither does odometer back-fill share. Full reasoning and the two mechanisms in
[ADR-0023](./docs/adr/0023-a-wave-must-be-corroborated-by-the-speedometer.md).

**So the count is 8, every survivor is a right, and the only `LEFT` in the session was ride 7
— which never happened.** Degrees off dead-shoreward for the eight kept: ride 11 at **9.3°**,
then 21.4, 23.4, 27.6, 29.9, 32.9, 33.8, and ride 2 with no direction at all. Ride 11 is a
right, so any band of 10° or more would wrongly call it straight; with the window pinned the
angle uncertainty is 4.2°, which needs the band to clear only 2.1°. **±8°** sits between, and
straight stays rare by design — it is a beginner's shape.

### Settled 2026-10-22, confirmed by measurement 2026-10-24: a committed file

The coastline source is **GSHHG 2.3.7 full, LGPL v3+**, committed to
`api/src/surf/reference/coast/` — inside the package, because `.gitignore`'s `data/` rule
matches `api/data/` too and `api/Dockerfile` copies only `src`.
Reproducibility chose a file over a live query — §3 requires every published result to be
exactly reproducible, and a file can be hashed into the stage params where a live query
cannot: an OSM-derived bearing moves when a stranger retraces the beach, with no code change
and no version bump. **OSM via Overpass was used once as the measuring stick and never
ships** (ODbL share-alike on a derived database is the second reason).

Two things the 2026-10-22 entry got wrong, both now measured:

- **Natural Earth was the preferred source on licence grounds. It passes on this session by
  luck** — one vertex within a kilometre means its fit spans several kilometres of coast. It is
  not validated and is not the choice.
- **The extract was expected to need a coarse-line caveat on the map.** It needs none, because
  the line is never drawn. Only its angle is read.

GSHHG's LICENSE.TXT permits redistribution with notice and bundling in software sold for a
fee, so a `NOTICE` file satisfies it and nothing is foreclosed (ADR-0020). Committing
reference geography to a public repo is a deliberate exception to the instinct behind
`.gitignore`, agreed with Miguel: that rule is about activity files, and `data/`,
`sample_data/` and `web/verification/` stay ignored.

`synthetic.py` has no coastline today, so the known-answer test needs one added alongside the
method, plus a synthetic walk so the sign chain has a fixture.


---

## Phase 7 · Wave metrics — resolver landed 2026-09-21, metrics still open

**Goal:** the per-wave card, computed. L3 proposes; this phase scores and measures.

> **The resolver half is done** and shipped ahead of the Session screen, because the hero
> element had no number to render. `L4` (features) + `L5` (verdict) +
> `GET /activities/{id}/waves`. The reference session: **22 proposals → 11 waves**, 1 left
> unresolved, every verdict carrying the tier that decided it and the reason in words.
> The local model was measured against the rule and does not ship (**ADR-0017**).
>
> The finding that made it possible: **a blind window is position-blind, not dataless.**
> Heart rate and the odometer are present for 100% of blind seconds on the reference file.
> The odometer freezes through a window and back-fills in one step on reacquisition — so it
> is a window *total*, never a rate — and 59 of its 127 blind runs move ≤ 0.5 m, which
> settles them outright. Both fully-blind proposals now get decided rather than deferred.

- [x] **Transparent scorer** over L3's candidates — duration, sustained shoreward run, takeoff
      acceleration, coverage, and the odometer channels above. Reported as a *proposal
      strength*, never as a validated probability (ADR-0013), and readable: a rule a person
      can argue with. On five seeded sessions it produces **zero false positives**; its 13
      refusals are candidates where the true ride fills 1–18 s of a 10–50 s proposal
- [x] **Duration**, **top speed**, **average speed**, **distance ridden** (km/h at the edge) —
      ✅ **L6, landed 2026-10-21 (PR 3a).** Mostly a surfacing job, not a measuring one: L4 had
      already measured all four per candidate and L5 kept only the verdict fields, so they
      stopped at its door. L6 selects and names them, adds the session's own aggregates, and
      **adds nothing to L4** — which is what makes it impossible for this to move the count.
      Reference session unchanged at 22 proposals → 11 waves
- [x] **Take-off speed** — speed at the ride's start. ✅ L6, from the framed track over the
      ride's first 4 s, observed seconds only. Computed here rather than added to L4 for the
      reason above. `None` when the watch saw none of those seconds, which is common: a
      take-off is exactly where the wrist goes under. Paired with wave speed below, this is
      what says whether the paddling needs work
- [ ] **Approximate wave speed** — from swell period and direction at those coordinates
      (Phase 8) against the ride's own track. Depends on Phase 8; ships after it
- [ ] **Manoeuvres** — changes in acceleration and heading. **A change followed by no speed is a
      fall, not a manoeuvre.** At 1 Hz with half the seconds estimated this is coarse: report a
      count with a confidence, never a stroke-by-stroke breakdown
- [ ] **Path straightness ratio** — path length over start-to-end distance, the rail-to-rail
      proxy
- [ ] **Bottom turn profile** — needs research; parked as an explicit open question, not a
      checkbox to quietly drop
- [x] **Avg / max BPM per wave** — ✅ L6, carried through from L4. Recovery afterwards is
      measured there as `hr_delta_after_bpm` but not yet served: it is evidence the rule
      reasons from, and no card asks for it
- [x] Every metric carries the wave's `position_coverage`. A metric from a wave the watch did
      not see is an estimate of an estimate and has to look like one — ✅ L6 carries it on
      every row, and the flip cards badge it

**Done when:** each candidate on the reference session yields a full card, every number has a
unit and a coverage, and the ones that cannot be computed say so instead of showing zero.

### What L6 measured — ✅ landed 2026-10-21 (PR 3a)

`GET /activities/{id}/metrics`, keyed on L5 with L0.6's key in its params — the audit decides
which seconds count as session but is not in the chain (ADR-0015), so a retuned audit produces
a fresh aggregate instead of silently reusing one computed over a different span.

**The reference session, measured:** 3529 m travelled, **752 m of it riding** — of which
**494 m the watch actually saw** — 2777 m paddling back out, 2.0 waves per 10 min, and a
median 238 s between rides. Session coverage **40.4%**, which is *lower* than the recording's
48.8%: the dry walk at either end is where the fixes are best, and excluding it (ADR-0015)
takes those good seconds out of the figure. Worth remembering before quoting "48.8%" about
anything in the water.

**Riding distance ships twice, on purpose.** `ride_m` is the odometer attributed second by
second — observed seconds at their own delta, blind seconds at their run's average — and
`ride_measured_m` is the part of that the watch saw. On the reference session they are 752 m
and 494 m; on individual waves they diverge far harder (wave 7: 39.5 m attributed, **4.2 m
measured**). A single figure would have had to be either a systematic undercount or an
estimate presented as a measurement, and the pair is neither. Phase 9's own wording asked for
exactly this: *"honest that only measured seconds count"*.

**Still open in Phase 7**, and deliberately not bundled into 3a: manoeuvres, path
straightness, the bottom-turn profile (needs research) and approximate wave speed (waits on
Phase 8). None of them is on the Session screen; they belong to the N3 Onda screen.

**Known limit of the resolver, recorded rather than tuned away.** The rule's refusals are an
L3 boundary problem, not a threshold that wants turning: L3 merges bursts, so a real 15 s ride
arrives inside a 40 s proposal padded with paddling. `odometer_peak_ms` (best sustained 10 s)
was added for exactly this and recovered most of it. Six of the remaining refusals land in the
band, which is where a model that earned its place would help — ADR-0017's did not.

### What the prototype's source settled — 2026-10-21 (PR 3b-api)

Reading `design_handover/design_handoff_surf_analytics/prototype/Surf Analytics.dc.html`
rather than only the handover README corrected two premises the 3b plan had been built on.
Both changed what gets built.

**Velocidade is about surfing seconds, not session seconds.** The prototype computes the card
from `S.filter(q => q.obs && q.k === 'riding')` and captions its axis
`km/h · segundos a surfar`. L6's `speed` covered *every* observed in-session second, so the
"visibly two populations" I recorded in PR 3a was an artefact of the wrong population: the
239 seconds under 0.5 m/s are paddling and sitting, which the card was never drawing. **L6
now ships `ride_speed` alongside `speed`** — the same histogram code over the `is_wave` spans
— because the alternative was the browser filtering seconds into a statistic, which is the
one thing `SessionMetrics`' own docstring forbids. Measured on the reference session:

| | n | mean | sd |
|---|---|---|---|
| `speed` — every observed second in the water | 1334 s | 1.46 m/s · 5.2 km/h | 1.45 |
| `ride_speed` — observed seconds on a wave | **121 s** | **4.66 m/s · 16.8 km/h** | 1.98 |

A factor of 3.2 between them, so wiring the card to the wrong one would have been a visible
lie rather than a rounding. Note the sample: the whole Velocidade card rests on **121
observed riding seconds**, which the card should say.

**The riding distribution is still not a bell**, though — it rises from 5 km/h, dips around
9–10 and peaks at **23–25 km/h**, above its own mean. That is a ride's own shape: slow
take-off, fast trim, slow kick-out, so the per-second histogram carries the entries and exits
as a shoulder. A symmetric hump at 16.8 ± 7.1 would put its mode where the data has its dip.
**Settled in PR 3b: the bars ship, the bell does not.** Both were built and screenshotted
against the reference session before one was deleted. Drawn as a bell, the card puts its
tallest point at 16.8 where the data dips, and shades 0–5 km/h where not one second was
recorded; drawn as bars, the mode sits at 23–25 where the seconds actually are. The mean and
the ±1σ lines stay, over the real shape — they are true, and they now read as a summary of
the bars rather than a substitute for them. The card ships no toggle (ADR-0013: the screen
does not offer the reader a choice the pipeline already made).

**Cadência as designed cannot be built from first-party signal.** Its y-axis is
`braçadas / min` — paddle stroke rate — and the prototype fakes it:
`cadV = 34 + min(34, 900/gap) + cov*12`, a formula over wave gaps and coverage, not a
measurement. No stroke channel is recorded for surfing, so there is nothing to read.
The card keeps its name and geometry and changes its quantity to L6's `waves_per_10min` plus
the per-bucket series, with the axis caption naming what it now is. Inventing a stroke rate
from gaps is the imputation the honesty rules exist to refuse.

### What PR 3b built — the four chart cards, 2026-10-21

On screen at `/session/{id}`, between the track and the session panels, drawn from
`GET /activities/{id}/metrics` with no arithmetic in the browser beyond turning a number into
a coordinate (`web/src/lib/chart.ts`, pure and tested on its own at 122 web tests).

| Card | Draws | Departure from the handover |
|---|---|---|
| Distância | 3.5 km headline, the swim/ride split bar, and `ride_measured_m` as a sub-line under *a surfar* | the design has two readout cells and L6 ships three numbers. 752 m attributed, **494 m with a position**: the sub-line qualifies the number above it rather than competing with it |
| Cadência | waves per 10-minute block, with `waves_per_10min` as the headline | the quantity changed, the name and geometry did not. The y-axis was `braçadas / min`, which no channel records. **Counts, not a per-block rate:** the last block is usually short, and 2 waves in 5 minutes is not 4 per 10. The short block's dot is drawn hollow and named underneath |
| Velocidade | `ride_speed` as measured bars on a fixed 0–40 km/h axis, mean and ±1σ over them | the bell was built, drawn and deleted — see above. Anything past 40 km/h lands in a marked overflow bar rather than rescaling the chart or vanishing (the 74.8 km/h artefact Phase 5 convicted) |
| Retorno | the paddle back out, bars behind a line, mean in the chart and median under it | none. `returns` has one entry fewer than there are waves, so a one-wave session renders the absent state |

**Hand-rolled SVG, not Observable Plot** — recorded in `docs/architecture.md`. Plot stays in
the labelling trace panel where its scales are the question; these four are the handover's
exact geometry, and Plot `replaceChildren`s the node it owns.

**A browser check, not an eyeball:** `tests/verify/ui.spec.ts` asserts one cadence dot per
bucket, one return bar per interval, the mean line drawn at the measured mean, and the hero
count equal to `/metrics`' own — the two routes cannot first disagree on screen.

### What PR 3c built — Perfis de onda, 2026-10-21

Eleven cards, one per settled wave, under the chart band. Each carries the **ride's own GPS
track** scaled to a 60×30 thumbnail — not a speed curve, which through a blind window would
be a picture of the smoother's estimate shown as a measurement. Measured and estimated runs
are separate paths and the estimated one is dashed, as on the big map (ADR-0010).

**Coverage is the card's opacity** (`0.55 + cov × 0.45`), with the figure in the badge as
well. On the reference session that puts wave 02 at 0% almost invisible and wave 11 at 96%
crisp, which is the honest reading of the two: the watch saw one of them.

**Opening a wave isolates it on the track above**, rather than linking to the N3 Onda
screen, which waits on Phases 6 and 7. The map's selection moved up to `SessionScreen` so
there is one answer to "which wave is selected" rather than two.

**Two things from the prototype are deliberately not built**, both recorded here so they are
not quietly re-added:

- **The delete button and its lock toggle.** Removing a wave from the screen is the UI
  overriding the pipeline's answer. L5 commits to the count and says why; a correction
  belongs on the labelling screen, which is append-only and already exists.
- **The trophy on the best wave.** The prototype ranked waves with
  `top × duration × (0.4 + coverage)`, a formula invented in the browser. No stage has
  committed to a best wave, so no card claims one. If it is wanted, it is an L6 field with a
  stated rule, not a sort in a component.

---

## Licensing, audited 2026-10-22

Asked before Phase 6: is this commercially viable? **Yes, with one piece of work.** Recorded
here because it changes what gets built, not just what gets paid for.

**Clean:** every code dependency is permissive (MIT/BSD/Apache/ISC), maplibre included — it
forked from mapbox-gl-js before the licence change, which is why it is the right choice.
Fonts are DM Mono, Hanken Grotesk and Saira, all SIL OFL 1.1, self-hosted at build time. FIT
decoding is hand-rolled over a handful of interoperability constants, with no Garmin SDK
dependency. Qwen 7B is Apache-2.0 and Ollama is MIT, and neither ships (ADR-0016, ADR-0017).
The design handover is Miguel's own, made with Claude.

**The one that blocked a sale: Esri imagery — settled 2026-10-22 (ADR-0021).** Keyless is
not licensed-for-resale and ADR-0018's cache-forever design is the pattern those terms
restrict. The answer was expected to be a pyramid we render ourselves; it is not. **Imagery
is now DGT's OrtoSat 2023** — ~50 cm, 2023, **CC BY 4.0**, so caching is permitted and
ADR-0018's design stands untouched. Five sources were compared on the reference session's own
frame before choosing: the open one is also the best one, and the only one that happens to
show swell. **No pyramid PR.** Remaining: **relief is still Esri hillshade**, off by default
and unresolved, and imagery is **Portugal-only** — France (Licence Ouverte 2.0) and Spain
(CC BY 4.0) are registry entries when a session needs them.

**Cheap but real:** Open-Meteo's free tier is non-commercial — Phase 8 needs their paid plan
and a CC-BY credit. The repo is public with no LICENSE file, so it is all-rights-reserved by
default; worth making that a decision rather than an oversight.

## Selling it, asked 2026-10-22 — **hosting is deferred** (ADR-0020)

Asked the same day as the audit above: a ~€5/month subscription, hosted in Azure, data in the
EU, a hosted model where the local one sits. **The money is not the constraint** — about €3.72
of a €5 charge survives VAT and card fees, against €0.25–0.45/month of marginal cost per user,
so break-even is 15–20 subscribers and ~1,000 of them is €45k/year gross. That is a
distribution problem, and no amount of architecture helps with it.

**[ADR-0020](./docs/adr/0020-hosting-is-deferred-not-foreclosed.md) records the deferral as a
decision rather than drift**, with the four invariants that keep the hosted path a change and
not a rewrite, and the measurement behind them: four IO seams, one composition root, one
`sqlite3.connect`, and a content-addressed cache that is already multi-tenant-correct.

**Two gates reopen it, and neither alone is enough.** Garmin's Connect Developer Program is
reported closed to new applications (September 2026), so today every user hand-exports FIT
files — that is the onboarding, not a detail of it. And ADR-0013 permits no accuracy claim
until a session is labelled the day it was surfed. Users with nothing we may honestly tell
them, or a claim with no way to get a file, are each half a product.

**One thing is wrong for tenancy today and is cheap to fix later:** `activities.source_sha256`
is globally `UNIQUE` and upload dedupe returns the existing activity for a known digest.
Shared, that hands one user another's session. `UNIQUE (user_id, source_sha256)` when the day
comes — but until then `activity_id` must not become an identifier the UI treats as global.

---

## Phase 8 · Marine context

**Goal:** the sea state that produced the session.

- [ ] Open-Meteo Marine at the session's coordinates and time: **swell components 1..4 where
      the provider has them** — height, period, direction, plus energy in kJ/m derived from
      height and period. Free tier is likely to give total wave + wind wave + primary swell;
      the plan must survive returning **fewer than four**, showing what exists rather than
      padding
- [ ] Wind speed and direction · **sea surface temperature** (the device's 21–23 °C is case
      temperature, not water) · time of day · combined swell energy
- [ ] Cached to disk per session on first fetch. Historic marine data does not change, and the
      app must work offline afterwards
- [ ] Degrades visibly: no network and no cache means the sea-state cards say unavailable, and
      nothing downstream invents a swell
- [ ] Feeds Phase 7's wave speed and cross-checks Phase 6's shore direction

**Done when:** the reference session carries its sea state, a second fetch is served from cache,
and pulling the network out degrades to a stated absence.

---

## Phase 9 · Session view

**Goal:** the screen Miguel asked for on day one. See [`DESIGN_BRIEF.md`](./DESIGN_BRIEF.md).

- [ ] **GPS graph, wave-selectable.** Selecting a wave hides the others and highlights it.
      **Play at 250 ms per step**, metrics ticking as it goes, interpolated between seconds
- [ ] **Radial overlay** on the map: swell 1 and swell 2 cones plus wind cone, labelled with
      wave height and km/h, opposed colours, colour strength carrying period. Legend bottom-right
- [ ] **Sea-state cards**, swell 1 → 4, **card size proportional to wave height**
- [ ] **Wave count**, spotlighted — the biggest element on the dashboard
- [ ] **Waves per 10 min**, with rate
- [ ] **Distance**, split swimming vs riding — and honest that only measured seconds count
- [ ] **Aerobic block** — avg BPM, max BPM, zones, effort vs reward, fatigue from HR against
      recovery time and paddling speed
- [ ] **Device confidence** — coverage, blind windows, and what Phase 5 rejected
- [ ] Infographics kept from the earlier list: **1** session map, **3** wave cards, **4** summary
      tiles, **5** state ribbon, **8** wave-shape small multiples, **9** speed distribution,
      **10** ride/rest rhythm. **2 (sawtooth) dropped** — the GPS graph already carries it
- [ ] **Correlation plot**, two metrics of the user's choosing, scatter

**Done when:** a session opens, plays back, and every number on it is traceable to a stage.

---

## Phase 10 · Sessions tab

**Goal:** am I getting better?

- [ ] Session list in the Garmin idiom, below the infographics
- [ ] **% change against the previous session in the top-right of every metric, card and
      infographic** — the tab's whole purpose
- [ ] **Surf level** — Beginner / Intermediate / Intermediate-high / Advanced / Athlete.
      First assessed after **5 sessions**, revisited every **10**. The rubric is written down
      and inspectable; a level is a claim about a person and must never be a black box
- [ ] Trends over time per metric
- [ ] **3D correlation plot** — user picks two metrics against time, manipulable
- [ ] Reuses Phase 9's correlation component

**Done when:** five sessions produce a level with its reasoning visible, and every card shows
its change against the last.

---

## Phase 11 · LLM passes

**Goal:** three short prose commentaries, on a budget that stays honest and cheap.

| Pass | Level | Says |
|---|---|---|
| Progression | Sessions | whether improvement is real, and in what |
| Session quality | Session | how that surf went, to the athlete |
| Technique | Wave | what the straightness ratio and manoeuvres imply |

- [ ] **100 output tokens each. Deterministic (temperature 0). Prose, no lists.** Reasoning
      capped at ~1,000 tokens end-to-end, output excluded
- [ ] **Context per level.** Sessions may read all three; Session and Wave see only their own.
      Enforced in code, not in the prompt
- [ ] **Core points as JSON**, scoped to the current surf level. It **empties on level-up**, and
      the next level opens with a short summary of the one before
- [ ] **Cleanser at 20k context**: reduce context and JSON back to core points, so the model
      stays sharp and does not forget. Roughly a refresh every ~20 sessions
- [ ] Prompts in `prompts/`, versioned, with goldens (CLAUDE.md). A prompt change re-runs evals
- [ ] `.env`: local endpoint first, hosted fallback for users without one. Never automatic —
      sending a session means sending location history
- [ ] The model gets **numbers, not raw tracks**, at every level

**Done when:** each level renders its comment offline against a local model, the same input
gives the same words, and the context budget is provably bounded by a test.


---

## Design handover — v1.0, 2026-09-15

Built in Claude Design over two weeks against `DESIGN_BRIEF.md`, then exported.
**Location:** `design_handover/design_handoff_surf_analytics/`

| | |
|---|---|
| `README.md` | 28 KB. The spec. Read it first |
| `prototype/Surf Analytics.dc.html` | working prototype — a **reference, not production code**. Open over http |
| `prototype/_ds/mf-concepts-design-system-*/` | the design system: `_ds_bundle.js`, `styles.css`, and `tokens/{base,colors,elevation,fonts,spacing,typography}.css` |
| `prototype/assets/` | logo lockup + mark |

**What it decided that the brief did not:**

- ~~**The UI is in Portuguese (pt-PT).**~~ **Overridden 2026-09-15: the UI follows the
  system language**, and so does the LLM's prose. The design's Portuguese (*Sessões · Sessão ·
  Onda*) becomes the `pt-PT` catalogue rather than the only one. See "Language" below.
- **The measured/estimated/blind language changed, for the better.** Solid stroke = measured;
  dashed translucent (`#3E6B7C`) = estimated; **absence plus a dedicated "blind rail"** = no
  data. It explicitly replaces the hatch — which this project had already had to lighten
  twice because a real session has 128 separate blind windows. Never a hatch, never a fake
  value.
- **Coverage is expressed typographically** — a number from low-coverage data renders lighter
  and more transparent, plus a small coverage arc. That answers the open question in
  `DESIGN_BRIEF.md` §10.2 ("how does 12% coverage look different from 100%, at card size?").
- **Basemap is OpenStreetMap tiles**, not MapTiler, with a warm-grid fallback that is a
  *designed state*, not an error. **Amended 2026-09-15: satellite imagery, not street tiles** —
  see "Basemap" below. `architecture.md` §6 names MapTiler and needs revisiting either way.
- **It names `llama-3.1-8b-instruct` as the local model.** We installed
  `qwen2.5:7b-instruct-q4_K_M`. Same size class; pick one deliberately in Phase 11 rather
  than letting the mismatch decide.
- The prototype's data is synthetic but shaped to `docs/data-findings.md` — 48.8% coverage,
  ~127 blind windows, ~3790 samples. Replace with real records; the shapes should line up.

**How to use it:** recreate the designs in `web/` using this codebase's patterns. Do not copy
the prototype's HTML into production.

---

## Local LLM stack — installed 2026-09-15

Everything lives under `/Users/Shared/llm` so it is reachable by every user on the machine,
and so no model is ever cached twice. `/Users/Shared/llm/README.md` documents it fully.

| layer | what | where |
|---|---|---|
| Engine | Ollama 0.34.0 | `/opt/homebrew/bin/ollama`, serves `:11434` |
| Model | `qwen2.5:7b-instruct-q4_K_M` (4.4 GB) | `/Users/Shared/llm/models` |
| Gateway | LiteLLM 1.101.0, OpenAI-compatible | `/Users/Shared/llm/venv`, serves `:4000` |
| HF cache | moved out of `~/.cache` | `/Users/Shared/llm/huggingface` |

**Measured on this machine** (M1 MacBook Air, 16 GB): **13 tok/s**, ~4.5 GB resident. A
100-token prose pass ≈ 8 s, so all three Phase 11 commentaries ≈ 25 s. Comfortably inside
the five-minute budget, with room for Phase 5's audit pass.

**Three env vars make it work** — in `~/.bash_profile` and `~/.zprofile` already; `/etc/zshenv`
and `/etc/profile` for all users needs sudo:

```bash
export OLLAMA_MODELS=/Users/Shared/llm/models
export HF_HOME=/Users/Shared/llm/huggingface
export TORCH_HOME=/Users/Shared/llm/torch
```

**Two traps.** Neither service starts at boot — they were launched from a shell. And a
launchd-started daemon (`brew services start ollama`) reads **no** shell profile, so it would
fall back to `~/.ollama/models` and appear to have lost the model; the fix is
`EnvironmentVariables` in the plist.

**Tone finding, relevant to Phase 11.** The first test generation opened with *"You had a
great session"* — unprompted praise about numbers it cannot verify. In a product where every
figure is marked *proposed* (ADR-0013), that tone is a defect. The prompts will have to work
against it.

---

## Open questions — carried, unanswered

Both came out of inspecting the reference FIT on 2026-08-31 and need a decision before the
phases that depend on them:

- [ ] **Decode the Connect IQ developer fields for comparison only?** The file carries another
      app's derived values — `wavenum`, `LRtxt1` (# of Lefts), `LRtxt2` (# of Rights),
      `wavespd`, `wavedist`, plus per-record `waveplot` (kph) and `Height` (m). ADR-0008 keeps
      them out of the pipeline and that stands. The open question is whether to decode them
      **for display-only disagreement** — "the app says 14 waves, we propose 22" — which is
      information about our detector rather than input to it. Blocks nothing; decide before Phase 9.
- [ ] **Height for manoeuvre detection.** The records carry **no altitude at all** (no field 2
      or 78). The only height signal in the file is that app's derived `Height`. Phase 7's
      manoeuvre definition says "changes in acceleration and/or height" — so either accept a
      third-party derived signal for that half, or drop height and work from acceleration
      alone. Blocks Phase 7.


---

## Decisions taken on the handover — 2026-09-15

### Language — follows the system, never hard-coded

The design ships Portuguese. **The product does not.** UI strings and the LLM's prose both
follow the user's system locale; `pt-PT` becomes the first catalogue, not the only one.

- [ ] Message catalogues keyed by locale; `pt-PT` transcribed from the design, `en` alongside it
- [ ] Locale resolved from the browser (`navigator.language`) with an explicit override, since
      a local-first app has no account to carry a preference
- [ ] **The LLM answers in the resolved locale too.** The prompt states the target language;
      the model is asked for prose in that language, not for English later translated
- [ ] No string literal in a component. A hard-coded label is the bug this decision exists to
      prevent, and it is cheapest to enforce from the first screen rather than retrofit
- [ ] Numbers and dates go through `Intl` — km/h, decimal commas and date order are all
      locale-dependent, and Portuguese formats differ from English

### Basemap — satellite, cached once

Satellite imagery, not street tiles: a surf session is coastline, sandbanks and a peak, none
of which a street map renders. Miguel's observation shapes the implementation — **the tiles
are static and load once per session**, so smooth-pan performance is not a requirement and
caching is trivially correct.

- [ ] **Esri World Imagery** as the source: keyless, free, satellite, and it satisfies the $0
      stack rule. Attribution is required and goes in the map's corner
- [ ] **Cache tiles to disk on first fetch**, keyed by z/x/y, exactly as the marine data will
      be. A session's tiles are fetched once and the app is fully offline afterwards —
      which is what `architecture.md` §7 requires
- [ ] The designed warm-grid fallback stays, for a session whose tiles were never fetched
- [ ] A session covers a few hundred metres of coast, so the tile count per session is small.
      Bound it anyway, and never fetch tiles for a viewport the user has not opened

### Accepted from the design as-is

- **Measured / estimated / blind**: solid · dashed translucent (`#3E6B7C`) · absence plus a
  dedicated blind rail. Replaces the hatch.
- **Coverage expressed typographically**: low-coverage numbers render lighter and more
  transparent, plus a coverage arc.


---

## Where PR #29 left the web stack — 2026-09-15

Next 16 · React 19 · TypeScript 7 · vitest 5, migrated deliberately while `web/` was seven
files, because Phase 9 writes three levels of hi-fi UI on top of it.

- **Route params are a Promise.** `await params` in every page. Next does not constrain a
  page's props type, so `tsc --noEmit` passes on the old synchronous form and it fails only
  in the browser. `pnpm run verify` is what catches this class of thing; the type checker is not.
- `vitest.config.mts`, not `.ts` — Vite 5's native config loader rejects ESM-in-CJS.
- `web/AGENTS.md` and `web/CLAUDE.md` are **generated by `next dev`** and re-created on every
  run. They are committed on purpose; deleting them just makes them come back as a dirty tree.
- deck.gl 9 and Observable Plot both verified working under React 19 in a real browser.

**Two PRs remain open and cannot be merged from here:** #3 (pnpm/action-setup v4→v6) and #5
(actions/setup-node v4→v7). Both edit `.github/workflows/ci.yml`, and the GitHub token lacks
`workflow` scope — `gh auth refresh -s workflow` fixes it permanently. Both are reviewed and
safe; they are also the riskiest of the CI bumps, spanning several majors, so if CI goes red
after merging, look there first. Neither affects local development.
