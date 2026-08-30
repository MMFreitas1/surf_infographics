# Build plan

Cross-session source of truth. **Read this first after a `/clear`.**
Tick items as they land — an item is only ticked when it is verified, not when it is written.

---

## ▶ RESUME HERE

| | |
|---|---|
| **Tier** | 2 · approved 2026-08-28 |
| **Done** | Phase 0 — foundation, CI, diagnostics, eval harness · Phase 1 parsers (PR #2) |
| **Next** | Phase 1 store — SQLite + `POST/GET /activities` + Zod parity (PR #3) |
| **Health** | `make check` → 121 tests green (88 api · 9 web · 24 evals); 10 api tests skip without `sample_data/` |
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
- [ ] **1 · Ingest** — FIT/GPX/TCX → canonical `Activity`, fidelity-tagged, golden tests
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

## Phase 1 · Ingest — next

**Goal:** a canonical `Activity` from any of the three formats, with fidelity tracked.

**PR #2 — parsers** ✅

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

**PR #3 — store** ← next

- [ ] SQLite `activities` + `blind_windows` tables — `store/schema.sql`, `store/repo.py`
- [ ] Samples → Parquet through the existing `StageCache` (L0), keyed from the activities row
- [ ] `POST /activities` + `GET /activities/{id}` + `GET /activities` in the canonical shape
- [ ] Idempotent ingest: re-posting identical bytes returns the existing activity
- [ ] Zod contract parity test — Python model and TS schema must not drift

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
| SQLite persistence | ~~nothing to persist until ingest exists~~ | **unblocked — lands in PR #3** |

## Decided against

| Item | Why |
|---|---|
| Sentry | single-user localhost app; local buffer + JSONL log is more useful and free (ADR-0007) |
| Phoenix / LLM tracing | same; Phase 8 logs prompt/response pairs to disk (ADR-0007) |
| Connect IQ bootstrap labels | derived from the same GPS we hold — their errors, no information (ADR-0008) |
