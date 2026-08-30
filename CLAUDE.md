# Project Conventions
<!-- Generated at project boot. Read every session. Keep current. -->

## Project summary
- What this is: A local-first surf analytics app that turns Garmin FIT/GPX/TCX activities into measurable wave detection and session infographics.
- Tier: 2
- Stack: Python 3.12 (FastAPI, uv) + TypeScript (Next.js 14, deck.gl, pnpm), SQLite + Parquet stage cache

## Architecture (one-way doors — DO NOT change without explicit sign-off)
- Two processes on localhost: `api/` (Python pipeline + REST, :8000) and `web/` (Next.js UI, :3000). Full component map in [docs/architecture.md](./docs/architecture.md).
- Data model: `Activity` → `Sample[]` (1 Hz) + `BlindWindow[]` → `WaveCandidate[]` → `WaveLabel[]`. Labels are append-only and are NEVER written by the pipeline. · External services: Open-Meteo Marine (swell/tide/wind), MapTiler (basemap), Ollama (local LLM, Phase 8).
- Changing architecture, schema, core deps, or auth requires plan mode + my approval.

## Workflow
- Start non-trivial work in PLAN MODE. Propose, wait for approval, then build.
- Feature branches. Conventional Commits. Small, focused PRs with clear "what & why".
- When a required input is missing, ASK — never assume and proceed.
- One phase at a time. [PLAN.md](./PLAN.md) is the cross-compaction source of truth; update it as phases land.

## Code standards
- Layout: `api/src/surf/{ingest,pipeline,detect,llm}` · `web/src/{app,lib}` · Lint/format: Ruff (Python) + Biome (TS) · Types: mypy (strict) + TypeScript (strict) — enforced.
- Conform to repo config; do not disable rules to pass. Match existing patterns.

## Testing — NOT OPTIONAL
- Every new function/endpoint gets tests in the SAME PR.
- Shared setup via fixtures in `api/tests/conftest.py`. All tests run offline; mock external calls.
- Numeric claims need a test with a known-answer fixture, not an eyeball check.

## Secrets & config
- Secrets from environment variables only. See `.env.example`.
- **This repo is PUBLIC.** `data/` and `sample_data/` are gitignored because activity files
  carry precise GPS traces with timestamps. Never commit an activity, and never paste
  coordinates into a doc, commit message or issue.
- Tests that need a reference session must `pytest.skip` when it is absent — CI never has it.

## CI/CD
- CI runs lint → type check → tests → evals on every PR; blocks merge on failure. Do not merge red.

<!-- TIER 2+ -->
## Observability — local only, no SaaS (ADR-0007)
- Structured JSON logging via structlog, to stdout AND `data/logs/api.jsonl`.
- Unhandled errors land in a bounded buffer, readable at `GET /diagnostics/errors`. Browser errors POST to `/diagnostics/client-error` so UI and API failures sit together.
- `cd web && pnpm run verify` drives Playwright: screenshots plus every console error, page exception and failed request, written to `web/verification/`. Use it to actually look at the UI.

<!-- IF the project uses an LLM / agents -->
## AI / LLM engineering
- Prompts in `prompts/`, versioned in git. A prompt/model change REQUIRES updating goldens + running evals.
- Evals: the CI gate in `evals/` is a hard pass/fail. No tracing service — LLM prompt/response pairs are logged to disk (ADR-0007).
- The LLM adjudicates ONLY the ambiguous confidence band (0.15–0.85). It ships only if it beats the deterministic baseline on held-out labels. Unmeasured models do not ship.
- Loop: prompt/version → trace locally → curate failures into eval dataset → re-run evals → ship.

## Honesty rules (project-specific, non-negotiable)
- GPS position is missing for ~51% of a typical session. Never impute a wave through a blind window and present it as measured.
- Every derived number carries a confidence. The UI renders what we do not know.
- "Detected", "uncertain" and "blind" are three different states and must stay distinguishable end to end.
- The pipeline consumes ONLY first-party recorded signal. No third-party app's derived values, ever (ADR-0008) — they add that app's errors and no information.

## Re-boot discipline (every session)
- Read this file and docs/architecture.md first.
- If a request contradicts a recorded decision, flag it and ask before acting.
