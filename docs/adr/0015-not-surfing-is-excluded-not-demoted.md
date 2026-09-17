# ADR-0015: A stretch that is not surfing is excluded from the session, not demoted

**Status:** accepted · 2026-09-17

## Context
A recording starts when the watch does and stops when the surfer remembers to stop it. The
reference session is 63.2 minutes long and its **last 7.2 minutes** are coverage 1.00 at
roughly zero speed: the watch is on the sand with the recording still running. The first
minute is the walk down.

Phase 7 and Phase 9 cannot ignore that. Session duration, distance ridden and waves per ten
minutes are all wrong if they count the walk up the beach, and 490 seconds of a 3790-second
recording is 13% of it.

ADR-0014 already built machinery for refusing data, so the obvious move was to reuse it and
demote those seconds to blind. That would have been a lie in the opposite direction from the
one ADR-0014 exists to prevent.

## Decision

### Exclusion, never demotion
A not-surfing stretch is recorded as a `NotSurfingWindow` on a parallel `AuditReport`. The
samples underneath are **untouched**: they keep `lat`, `lon`, `speed_ms`, and `observed=True`.
`GET /activities/{id}` still serves every one of them and the smoothed track still covers the
whole recording.

Demoting them was rejected because the watch *could* see — better than usual, in fact, since a
dry wrist is what makes those windows detectable at all. Reporting blindness we did not have
is the same class of error as reporting a measurement we did not take, and it would have cost
about a fifth of the reference session's coverage.

Trimming the samples themselves was also rejected: the excluded stretch has to stay
reviewable, because somebody must be able to check the verdict.

`Activity` is unchanged, so this adds no schema one-way door. The report is a parallel object,
the same shape of decision as ADR-0010's parallel track.

### Coverage is the signal, and the inversion is the point
What makes this project hard — a wrist underwater about half the time — is what makes this
easy. In-water windows on the reference session average **0.39** coverage; dry ones sit at
**1.00**. The threshold is a line drawn across an empty gap rather than a tuned value.

Coverage alone is not sufficient, and the first implementation proved it by cutting a real
ride out of three of five seeded synthetic sessions. A rider standing up has the wrist clear
of the water, so the final ride of a session can be the best-covered window in the file. A
window is therefore only trimmable when it is **dry *and* slow** — a surfer rides at 4–10 m/s
and walks at about 1.3.

### Only the ends are trimmed, by the baseline
The rule walks inward from each end and stops at the first window that does not look like dry
land. "Longest contiguous wet stretch" was tried first and is wrong: a session has interior
dry spells, because a surfer sitting up with the wrist clear reads exactly like one standing
on the sand. On the reference recording that rule returned an **11-minute** session out of 63.

Interior stretches are what the audit pass is for, and it has to beat this baseline on
measured truth before it gets to make that call (ADR-0005). `NotSurfingReason.INTERRUPTION`
and `AuditSource.LLM` exist in the contract now so the boundary is fixed before anything
crosses it.

### L0.6 sits beside L1, not above it
Every other stage chains in a single file. This one hangs off L0.5 **in parallel** with the
smoother, because the audit changes no sample. Chaining L1 beneath it would mean retuning a
coverage threshold silently invalidated a smoothed track that cannot possibly have changed,
along with every screen built on it. Pinned by
`test_retuning_the_audit_leaves_the_smoothed_track_alone`.

### The digest carries no location
`SessionWindow` is rates, fractions and counts — no coordinate, no bearing. This is what lets
Pass 2's hosted-model fallback be genuinely opt-in: there is no location in the payload to
send anywhere, so the guarantee is structural rather than a policy someone has to remember.
Asserted on both sides of the contract.

## Consequences

- **The reference session's span is 55.0 minutes of a 63.2-minute recording**, with 60 s
  excluded before entry and 430 s after exit, at a stated confidence of 0.7 rather than 1.0.
- **The top speed does not move.** ADR-0014's amendment had already removed the artefact, and
  what remains is inside the surfing span. `top_speed_ms_all` and `top_speed_ms_surfing` ship
  side by side precisely so that is visible rather than assumed — on this session they are
  equal, and the report says so.
- **Truth for this had to be built, not collected.** Nobody can mark from memory which minute
  they walked out of the sea, which is the same problem ADR-0013 records for waves. The
  synthetic generator grew an opt-in out-of-water tail with exactly known bounds; across five
  seeds the baseline recovers it to within a window and trims **zero** genuine rides.
- **The generator's additions are opt-in and draw from their own RNG**, because every
  committed golden and most of the test suite is built on its default output.
- A boundary cannot be sharper than a window, and a leftover shorter than one window is not
  reported as an exit — that is the ragged end of the digest, not a walk up the beach.
- Nothing consumes the span yet. Phase 7 is where it starts mattering, and the report carries
  `surfing_t_start`/`surfing_t_end` so that every metric reads one answer rather than deriving
  its own.
