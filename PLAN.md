# Build plan

Cross-session source of truth. **Read this first after a `/clear`.**
Tick items as they land — an item is only ticked when it is verified, not when it is written.

---

## ▶ RESUME HERE

| | |
|---|---|
| **Tier** | 2 · approved 2026-08-28 |
| **Done** | Phase 0 — foundation, CI, diagnostics · **Phase 1 complete** — ingest, storage, REST |
| **Next** | Phase 2 — kinematics: Kalman + RTS smoother, blind windows, propagated confidence |
| **Health** | `make check` → 163 tests green (123 api · 16 web · 24 evals); 10 api tests skip without `sample_data/` |
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
- [ ] **2 · Kinematics** — Kalman + RTS smoother, blind windows, propagated confidence
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

## Phase 2 · Kinematics — next

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

- [ ] Kalman filter + RTS backward smoother over the 1 Hz samples (ADR-0003)
- [ ] Confidence per sample, driven by fix availability and innovation — not a constant
- [ ] Blind windows stay blind: the smoother may interpolate *through* one, but the result is
      tagged so nothing downstream can present it as measured
- [ ] Wire as an L1 stage behind the `Stage` protocol, cached by `StageCache`
- [ ] Tests: a synthetic track with known kinematics recovers to a stated tolerance; a
      positionless stretch produces low confidence, never silent certainty

**Done when:** L1 runs over the reference session, confidence drops inside every blind window,
and `make check` is green.
