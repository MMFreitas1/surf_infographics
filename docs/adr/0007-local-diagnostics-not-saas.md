# ADR-0007: Local diagnostics instead of SaaS error tracking

**Status:** accepted · 2026-08-29 · supersedes the Sentry and Phoenix rows of ADR/architecture as first recorded

## Context
The Tier 2 house style specifies Sentry for error tracking and Phoenix for LLM tracing.
Both are aggregation services built for fleets of machines and multiple developers.

This app is single-user and localhost-only. There is no fleet to aggregate, no on-call
rotation, and no second developer. What is actually needed is narrower and more useful:
whoever is debugging — including an assisting agent — must be able to *read the errors*
and *see the UI*, without a cloud account or a browser devtools session.

## Decision
No SaaS error tracking and no LLM tracing service. Instead:

- **structlog routed through stdlib logging**, so every event reaches both stdout and an
  append-only `data/logs/api.jsonl`.
- **A bounded in-memory `ErrorBuffer`** with every unhandled exception captured by a
  FastAPI exception handler.
- **`GET /diagnostics/errors`**, `DELETE /diagnostics/errors`, `GET /diagnostics/logs` —
  errors and logs readable over HTTP.
- **`POST /diagnostics/client-error`** plus a browser `ErrorReporter`, so front-end
  failures land in the same buffer as server failures instead of dying in a console.
- **Playwright (`pnpm run verify`)** writing screenshots and a JSON of every console
  error, page exception and failed request to `web/verification/`.

For Phase 8, LLM prompt/response pairs are logged to disk rather than to a tracing service.

## Consequences
- Full visibility with no cloud account and no cost, consistent with the $0 stack rule.
- No cross-session error aggregation or alerting. Acceptable: there is one user, who is
  present when the error happens.
- This is a deliberate, signed-off deviation from the locked house style — recorded here
  rather than silently applied.
