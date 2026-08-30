# Architecture

**Status:** approved 2026-08-28 · **Tier:** 2 · Decisions here are one-way doors. See `docs/adr/` for rationale.

## 1. Thesis

Consumer surf apps run an *online* filter over a noisy GPS stream and report a confident number.
We process *offline*, with the entire session in hand, and report a number **with its uncertainty**.

That is the whole edge, and it is defensible: an offline RTS smoother has access to the future
as well as the past, which no watch-side filter can ever have.

## 2. Component map

```
                      ┌──────────────────────────────────────────┐
  FIT / GPX / TCX ───▶ │ api/  Python 3.12 · FastAPI · uv  :8000 │
                      │                                          │
                      │  ingest/   parse → canonical Activity    │
                      │  pipeline/ L1…L6, pure + content-hashed  │
                      │  detect/   Detector implementations      │
                      │  llm/      Ollama lifecycle (Phase 8)    │
                      └───────────────┬──────────────────────────┘
                                      │  REST/JSON
                      ┌───────────────▼──────────────────────────┐
                      │ web/  Next.js 14 · TS strict      :3000  │
                      │  deck.gl map · Observable Plot charts    │
                      │  labeling UI (ground truth)              │
                      └──────────────────────────────────────────┘

  storage:  SQLite (metadata, events, labels)  +  Parquet (cached stage outputs)
```

## 3. Pipeline stages

Every stage is a pure function `f(input, params) -> output`, cached on
`sha256(input_hash, params, code_version)`. Re-running after a parameter tweak is
near-instant and any published result is exactly reproducible.

A stage also owns how its output is serialised, and every stage runs through one door --
`surf.pipeline.run_stage`. A cached payload therefore stands in for running the stage: it
is self-describing, so decoding one never depends on a database row a cache-only re-run
may not have.

| Stage | Name | Output |
|---|---|---|
| L0 | ingest | `Activity` — 1 Hz `Sample[]`, `BlindWindow[]`, device/session metadata. Cached as one Parquet payload: samples as columns, session and windows as file metadata. SQLite indexes the same facts so they can be queried |
| L1 | kinematics | `SmoothedSample[]` — Kalman + RTS-smoothed position/velocity, posterior sigma and confidence per second, `observed` marking fix from estimate. A parallel track, never an overwrite (ADR-0010) |
| L2 | frame | shore bearing → cross-shore / alongshore coordinates |
| L3 | candidates | high-recall interval proposals |
| L4 | features | ~30 features per candidate |
| L5 | classify | rules → GBM → LLM adjudicates the 0.15–0.85 band only |
| L6 | metrics | session + per-wave aggregates |

## 4. Data model

```
Activity ──┬── Sample[]        1 Hz: t, lat?, lon?, speed?, hr, temp, distance, quality
           ├── BlindWindow[]   first-class gaps: t_start, t_end, cause
           └── WaveCandidate[] proposed intervals + features + score
                    │
                    └── WaveLabel[]   APPEND-ONLY ground truth, never written by the pipeline
```

`lat`, `lon` and `speed` are **optional by design**. Roughly half of a real session has no fix.
A `Sample` without a position is still a valid sample: it carries HR, time and blind-window context.

## 5. Load-bearing decisions

1. **Offline RTS smoothing** — the backward pass is our accuracy edge over any device-side filter. (ADR-0003)
2. **Confidence propagates end to end** — blind windows are objects, not absences. (ADR-0003)
3. **Labels are append-only and pipeline-immutable** — the only way evaluation stays honest. (ADR-0006)
   Likewise the smoothed track is parallel to the measured one, never written over it. (ADR-0010)
4. **Detector behind an interface** — `Detector.detect(activity) -> list[WaveCandidate]`; rule-based, GBM and LLM-adjudicated variants are judged by one harness. We ship whichever measures best. (ADR-0005)
5. **Shore-relative feature frame** — features are spot-independent, so a model trained at Sines transfers. (ADR-0003)
6. **First-party signal only** — no third-party app's derived values enter the pipeline. (ADR-0008)

## 6. Confirmed choices

| Concern | Choice | Note |
|---|---|---|
| Source of truth | **FIT** primary; GPX/TCX degraded | ADR-0002 |
| Database | **SQLite** + Parquet stage cache | ADR-0004 — local-first, zero-ops, one file to back up |
| Deploy | **localhost only**, Docker Compose for reproducibility | no cloud, no auth surface |
| Upload shape | `POST /activities` takes the **raw file bytes as the body**, not multipart | multipart would add `python-multipart` for no gain: the format is detected from content, so the filename is cosmetic. `curl --data-binary @file` |
| External | Open-Meteo Marine (keyless), MapTiler free tier | $0 stack rule |
| Error tracking | **local** — bounded buffer + `/diagnostics/*` | ADR-0007, no SaaS |
| Logging | structlog → stdout + `data/logs/api.jsonl` | ADR-0007 |
| UI visibility | Playwright `pnpm run verify` → screenshots + console errors | ADR-0007 |
| Evals | `evals/` gate on a synthetic golden | ADR-0008 |
| Tracing | none; LLM I/O logged to disk | ADR-0007 |
| LLM | Ollama, ~7B Q4_K_M, idle-TTL unload | Phase 8, ADR-0005 |

## 7. Non-functional

- **Scale:** single user, ~200 sessions/year, ~4k samples each. Trivial. Optimise for clarity, not throughput.
- **Latency:** full re-analysis of one session < 5 s warm. Interactive scrubbing must be < 100 ms (served from cache).
- **Data sensitivity:** activity files are personal location history. They stay local, are gitignored, and are never sent to a third party. The LLM is local for this reason as much as for cost.
- **Offline:** the app must fully function with no network. Weather enrichment degrades gracefully.

## 8. Known limits (see docs/data-findings.md)

GPS position is absent for ~51% of a real session because the wrist is submerged.
This is a property of the sport, not a bug we can fix in software. The product answer is
to report **detected / uncertain / blind** as three distinct states rather than to guess.
