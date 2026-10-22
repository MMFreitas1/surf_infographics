# ADR-0020: Hosting is deferred, not foreclosed

**Status:** accepted · 2026-10-22 · amends nothing: [ADR-0004](0004-sqlite-local-first.md)
and [ADR-0007](0007-local-diagnostics-not-saas.md) stand as written.

## Context

Asked on 2026-10-22, the same day as the licensing audit: can this be sold as a ~€5/month
subscription, hosted in Azure, data resident in the EU, with a hosted model where the local
one sits today?

**The money is not the constraint.** Priced at €5 inclusive of Portuguese VAT, roughly €3.72
survives VAT and card fees; the marginal cost of a user is €0.25–0.45/month, most of it burst
compute, because Phase 11 sends a hosted model ~1,300 billed tokens per session and no track.
Break-even against a minimal EU stack is 15–20 subscribers. Reaching €45k/year gross needs
about a thousand. That is a distribution problem and this ADR cannot help with it.

**Three recorded decisions say not yet.** ADR-0004 chose one SQLite file and no auth surface.
ADR-0007 chose local diagnostics over any SaaS. `architecture.md` §7 is the blunt one: activity
files *"stay local, are never sent to a third party"*, and *"the LLM is local for this reason as
much as for cost"*. Hosting does not bend those; it inverts them.

**Two gates sit outside this repo.** Garmin's Connect Developer Program is reported closed to
new applications as of September 2026, and it never admitted personal use. Without it every
user hand-exports FIT files from Garmin Connect, which is the onboarding, not a detail of it.
And [ADR-0013](0013-ship-proposed-numbers-without-a-labelling-gate.md) permits no accuracy
claim at all until a session is labelled the day it was surfed. Selling a number we are not
allowed to claim is worse than not selling.

The risk in waiting is not the delay. It is drift: building for months in a shape that turns
the hosted path into a rewrite, and finding out afterwards. So the deferral is recorded as a
decision, with the invariants that keep it a change.

## Decision

**Local-first remains the shipping configuration. Hosting is a later, additive layer, and
four invariants hold while we wait.**

1. **Every path comes from `Settings`.** No module learns where the data directory is by any
   other route. True today; it is what makes a storage backend a constructor argument.
2. **SQL stays inside `store/repo.py` and `store/labels.py`.** The SQLite-isms are harmless
   *because* they are quarantined. SQL reaching `main.py` is what would make Postgres a
   migration of the whole API instead of two modules.
3. **A tenant is a column that does not exist yet — and one constraint is already wrong for
   it.** `activities.source_sha256` is globally `UNIQUE`, and upload dedupe returns the
   existing activity for a known digest. Shared, that hands user B user A's session and
   refuses the legitimate case of two surfers holding the same file. The fix is
   `UNIQUE (user_id, source_sha256)` and a scoped lookup. Cheap as a migration, so it is not
   done now — but `activity_id` must not become an identifier the UI treats as global or
   shareable in the meantime, because that is what would make it dear.
4. **No screen may assume a warm stage.** Everything runs inside the request today, under §7's
   five-second warm budget. That assumption is free to hold locally and expensive to unpick in
   a UI built on it.

**What the hosted layer is allowed to be:** new modules — identity, a tenant column, a job
queue, billing. Not a refactor of L0–L6, which are pure functions and indifferent to where
they run.

**What reopens this ADR:** Garmin accepting applications again, *and* one session labelled
fresh. Neither alone suffices. The first without the second gives us users and nothing we may
honestly tell them; the second without the first gives us a claim and no way to get a file.

## What was measured, not assumed

Grepped on 2026-10-22, not recalled from how the code is meant to be:

- **Four IO seams, one composition root.** `StageCache`, `ActivityRepository`,
  `LabelRepository` and `TileCache`, all constructed at `api/src/surf/main.py:94-98`.
  `api/src/surf/report.py:204-206` builds three of them a second time — a duplication to
  collapse when next touched, not one to feed.
- **One `sqlite3.connect`**, at `store/repo.py:54`. No path literal outside `config.py` but
  `SCHEMA_PATH` and the two prompt paths.
- **The content-addressed cache is already multi-tenant-correct.** `StageCache.get/put` is
  opaque bytes under `sha256(input_hash, params, code_version)`. Two users with identical
  input legitimately share derived bytes, and naming a key requires already holding the input
  that produced it. It wants no tenant, and §3's reproducibility guarantee is what makes that
  safe rather than lucky.
- **The migration is costed per seam, in days:** cache to Blob, the two repositories to
  Postgres, tiles to Blob behind a CDN. The pipeline is zero.

## Consequences

- **The pipeline never enters this conversation.** L0–L6 are pure, so no hosting decision can
  move a number — the same property that let ADR-0019 change the basemap safely.
- **Synchronous execution is the one thing that gets dearer with time.** On scale-to-zero
  compute a cold request walking L0→L6 can outlast a request timeout. The fix is a worker and
  a `202`, which touches the web app's fetching as well as the API's, and it is one line if
  ingest warms the chain. Invariant 4 is what keeps it one line.
- **ADR-0007's diagnostics survive one replica and not two.** `data/logs/api.jsonl` and the
  bounded error buffer go per-replica. Single replica until it cannot be, then stdout plus a
  sink is the whole change. Nothing here licenses a SaaS.
- **The Esri replacement is not deferred by this ADR.** It is a licensing obligation, not a
  hosting one, and it runs on its own schedule — the longer screens are built against
  sub-metre proxied imagery, the more expectation there is to meet. Separately: every provider
  worth paying restricts caching tiles forever, which is exactly what §7's offline requirement
  and ADR-0018 depend on. **Open data is not merely the cheap licence here, it is the only one
  the architecture can accept.**
- **Open-Meteo's paid plan is a cost of selling, not of hosting.** Its free tier is
  non-commercial, so it arrives with the first paying user, not with the first server.
- **Swapping the local model for a hosted one inherits nothing.** ADR-0016 and ADR-0017 closed
  adjudication to a model until one clears the same harness, and a hosted model does not clear
  it by being larger. Phase 11's prose is a different job and may use one — pinned to a dated
  snapshot, because a retired model makes stored prose unreproducible.
- **EU residency and GDPR arrive with the second person's data, not the first server.**
  Controller duties, a DPA, a sub-processor list, export and deletion. Phase 11's "numbers, not
  raw tracks" is what keeps location history out of a provider's abuse-monitoring retention,
  and it is now load-bearing for compliance as well as for taste.
- **Local is not a holding pattern.** The two things still owed — a fresh label and Phases
  6–11 — are each strictly easier with one user, one machine, no auth and no cold starts. A
  server improves neither.
