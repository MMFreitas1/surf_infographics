# Build plan

Cross-session source of truth. **Read this first after a `/clear`.**
Tick items as they land — an item is only ticked when it is verified, not when it is written.

---

## ▶ RESUME HERE

| | |
|---|---|
| **Tier** | 2 · approved 2026-08-28 |
| **Done** | Phase 0 — foundation, CI, diagnostics · **1** — ingest, storage, REST · **2** — pipeline spine, RTS-smoothed track · **3** — shore frame (L2), high-recall candidates (L3) · **4** — append-only labels, six endpoints, scrub UI, labels joined to the eval harness · **5 Pass 1** — L0.5 cleaner, two channels + odometer containment, top speed 74.8 → 54.1 km/h · **5 Pass 2 baseline** — L0.6 audit, the session found inside the recording |
| **Order** | **Phase 5 (clean) → Session screen (design Level 2) → the rest.** Agreed 2026-09-15. Level 2 first because it is the screen the design leads with, holds all the machinery, and works with the one session that exists. Level 1 compares sessions and needs five of them for a surf level — it would be an empty state today. Cleaning comes first so no screen ever renders the 74.8 km/h artefact |
| **Stack** | Next 16 · React 19 · TS 7 · vitest 5 as of PR #29. Route `params` are a Promise — `tsc` does not catch that, only running it does |
| **Next** | **The LLM audit** (the last piece of Phase 5), then the Session screen. The deterministic baseline it has to beat now exists, and so does the truth to score both on: a synthetic session with a known out-of-water tail. It ships only if it wins (ADR-0005). Two defects found by the diagnostics loop are queued ahead of it if you want them first — see "Found by the loop". Start at **"Phase 5 · Clean signal"** |
| **Design** | ✅ **Landed 2026-09-15** — high-fidelity, all three levels, in `design_handover/design_handoff_surf_analytics/`. Read its `README.md` (28 KB) before building any UI. It supersedes `DESIGN_BRIEF.md`, which was the input to it |
| **Local LLM** | ✅ **Installed and verified** — Ollama + `qwen2.5:7b-instruct-q4_K_M` + LiteLLM gateway, all under `/Users/Shared/llm`. 13 tok/s measured; a 100-token pass ≈ 8 s. See "Local LLM stack" below |
| **Re-planned** | 2026-08-31 — the product is a **three-level drill-down** (Sessions → Session → Wave), specced by Miguel and merged below. The labelling gate is dropped (ADR-0013): every derived number ships marked *proposed*, and validation waits for a session labelled the day it is surfed |
| **Health** | `make check` → 449 tests green (343 api · 58 web · 48 evals); 17 api tests skip without `sample_data/`. `make labels` reports on human labels and gates nothing |
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
- [ ] **5 · Clean signal** — ✅ Pass 1 (L0.5, cleaner) · ✅ Pass 2 baseline (L0.6, audit) · ⬜ Pass 2 LLM (must beat the baseline)
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

### Found by the loop, not yet fixed — 2026-09-17

Both surfaced while verifying Phase 5's odometer fix. Neither is caused by it; both are
recorded here so they survive a `/clear`, and neither was folded into an unrelated PR.

- [ ] **SQLite reads are not serialised, and the label page trips it.** `store/repo.py` opens
      one connection with `check_same_thread=False` and shares it across FastAPI's threadpool,
      but only `save` and `delete` take `self._lock` — `get`, `samples_key`, `summaries`,
      `id_for_digest` and `_blind_windows` all execute unlocked. Opening `/label/{id}` fires
      four requests at once and raised `sqlite3.InterfaceError: bad parameter or other API
      misuse` from `repo.get`, which the browser then reported as `ApiUnreachable`. Structural
      and present since PR #19. **User-facing: a session page can fail to load its labels.**
- [ ] **`make verify` flakes on a cold Next dev server.** The scrub spec takes **25.1 s**
      against a 30 s default timeout when the route has not been compiled yet, and 4.0 s once
      it has. It failed once, then passed on every rerun. Either raise the per-test timeout in
      `playwright.config.ts` or warm the route before asserting — a verification harness that
      cries wolf is worse than none.

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

## Phase 5 · Clean signal — Pass 1 ✅ · Pass 2 baseline ✅ · LLM next

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
- [ ] **Pass 2 LLM — audit over what the baseline cannot settle.** Local model, deterministic,
      offline. It sees the **same digest the baseline reads** — windowed speed/coverage/HR,
      already built and **coordinate-free by construction**, which is what makes the hosted
      fallback safe to offer rather than merely policed. Its job is the residue: an interior
      stretch that is not surfing at all (driving home, the watch on a table).
      `NotSurfingReason.INTERRUPTION` and `AuditSource.LLM` are already in the contract, so
      the boundary is fixed before anything crosses it. **It ships only if it beats the
      baseline on the synthetic truth above** (ADR-0005) — and not shipping is a result.
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

**Goal:** left or right, per wave — and a shore axis that works on a session that is mostly
sitting still.

ADR-0011's velocity-coherence bearing scored 0.51° on the synthetic and **failed on the real
session** (coherence 0.365, refused). The reason is structural: it weights fast seconds, and a
real session is mostly slow ones. Miguel's method inverts that and uses the sitting as signal.

- [ ] **Peaks from stationarity.** Where the track stays inside a ~20 m radius for over a
      minute, that is a peak. Centroid them.
- [ ] **Coastline by regression.** ~20 points along the shore within ~1 km either way of the
      peak, least-squares line. Source: a coastline geometry provider (OSM/Overpass or the
      basemap vendor), cached to disk on first fetch so the app stays offline afterwards.
- [ ] **Classifier.** Perpendicular to the coast through the peak centroid. Ride heading above
      it is a left, below is a right, for an east-facing shore — with the handedness derived
      from which side the sea is on, not hard-coded.
- [ ] **Fallback, offline or coastline unavailable:** principal axis of the peak cloud plus the
      seaward direction from where rides *end*. Marked lower confidence; never silently
      substituted.
- [ ] **A new ADR** records this as the primary method and demotes ADR-0011's bearing to a fallback,
      with the 0.365 measurement as the reason.
- [ ] Tests: a synthetic coastline at a known angle recovers a known left/right split; a session
      with no stationary period degrades to the fallback rather than guessing.

**Done when:** every candidate on the reference session carries left/right/straight with a
stated confidence, and the shore line can be drawn on the session map without a caveat.

---

## Phase 7 · Wave metrics

**Goal:** the per-wave card, computed. L3 proposes; this phase scores and measures.

- [ ] **Transparent scorer** over L3's candidates — duration, sustained shoreward run, takeoff
      acceleration, coverage. Reported as a *proposal strength*, never as a validated
      probability (ADR-0013), and it must stay readable: a rule a person can argue with.
- [ ] **Duration**, **top speed**, **average speed**, **distance ridden** (km/h at the edge)
- [ ] **Take-off speed** — speed at the ride's start. Paired with wave speed below, this is what
      says whether the paddling needs work
- [ ] **Approximate wave speed** — from swell period and direction at those coordinates
      (Phase 8) against the ride's own track. Depends on Phase 8; ships after it
- [ ] **Manoeuvres** — changes in acceleration and heading. **A change followed by no speed is a
      fall, not a manoeuvre.** At 1 Hz with half the seconds estimated this is coarse: report a
      count with a confidence, never a stroke-by-stroke breakdown
- [ ] **Path straightness ratio** — path length over start-to-end distance, the rail-to-rail
      proxy
- [ ] **Bottom turn profile** — needs research; parked as an explicit open question, not a
      checkbox to quietly drop
- [ ] **Avg / max BPM per wave**, and recovery afterwards
- [ ] Every metric carries the wave's `position_coverage`. A metric from a wave the watch did
      not see is an estimate of an estimate and has to look like one

**Done when:** each candidate on the reference session yields a full card, every number has a
unit and a coverage, and the ones that cannot be computed say so instead of showing zero.

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
