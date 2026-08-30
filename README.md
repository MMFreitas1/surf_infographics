# surf_infographics

Local-first surf analytics. Turns Garmin activity files into measurable wave detection and
session infographics — and is honest about what it cannot see.

## Why

Consumer surf apps run an online filter over a noisy GPS stream and report a confident number.
Measured on the reference session, the Connect IQ app already on the watch reports **17 waves**,
of which **3 were detected with no GPS position at all** and **5 rest on a frozen speed reading**
held while the GPS was dead. Its whole algorithm is `speed ≥ 9 kph for ≥ 5 s`.

We process offline with the entire session in hand, and report every number with its uncertainty.
Full forensics in [docs/data-findings.md](docs/data-findings.md).

We do **not** consume that app's numbers. They are derived from the same GPS stream we already
hold, so they would contribute its errors and no information ([ADR-0008](docs/adr/0008-no-third-party-derived-data.md)).

## Quick start

```bash
make setup     # uv sync + pnpm install
make api       # API on http://127.0.0.1:8000
make web       # UI  on http://127.0.0.1:3000
make check     # everything CI runs: lint, types, tests, evals
make verify    # drive the UI with Playwright -> screenshots + console errors
make errors    # recent errors from the running API
make logs      # tail the structured log
```

Or containerised (verified working on Colima):

```bash
docker compose up -d     # api :8000 + web :3000
docker compose down
```

## Layout

```
api/        Python 3.12 · FastAPI · uv        pipeline + REST
web/        Next.js 14 · TypeScript · pnpm    map, charts, labeling UI
prompts/    versioned LLM prompts             (Phase 8)
evals/      goldens + detection eval gate
research/   throwaway spikes, not production
docs/       architecture.md · data-findings.md · adr/
sample_data/ reference session (FIT + GPX) — gitignored, local only
```

## Docs

| Document | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Conventions. Read first, every session. |
| [PLAN.md](PLAN.md) | Phase plan and current status. |
| [docs/architecture.md](docs/architecture.md) | Component map and load-bearing decisions. |
| [docs/data-findings.md](docs/data-findings.md) | What is actually in the files, measured. |
| [docs/adr/](docs/adr/) | Why each one-way door was chosen. |

## Status

**Phase 0 complete** — foundation, CI, test and eval harness. Ingest lands in Phase 1.
