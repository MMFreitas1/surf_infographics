# ADR-0010: The smoothed track is a parallel model, not an overwrite

**Status:** accepted · 2026-08-30

## Context
L1 produces a smoothed position, velocity and confidence for every second of a session,
including the ~51% of seconds that carry no GPS fix. Something has to hold that output, and
the obvious place was the `Sample` it came from — `Sample.confidence` was even documented as
*"1.0 until L1 refines it"*, which reads as refine-in-place.

Refining in place is a trap. A `Sample` inside a blind window would come out carrying a
`lat`/`lon` that is structurally identical to one the watch actually recorded. Every
consumer — the frame transform, the feature extractor, the UI, an eval harness — would have
to remember, correctly and forever, which fields on which rows are measurements and which
are estimates. The one rule this project refuses to break is that a guess must never be
presentable as a measurement, and in-place refinement makes breaking it the default.

## Decision
L1 emits a **parallel track**: `list[SmoothedSample]`, one row per input sample, alongside
the untouched `Activity`. `SmoothedSample` always carries a position, because an estimate
exists even where a fix did not, and carries two fields that keep it honest:

- `observed: bool` — whether that second had a GPS fix. This is the measured/estimated line.
- `position_sigma_m: float` — the posterior standard deviation, in metres. What we do not
  know, in the units of the thing we do not know it about.

`Sample.confidence` keeps its name but not its old meaning: it is confidence in the sample
*as recorded*, and L1 never writes back to it.

Rejected alternatives:

- **Overwrite `Sample.lat`/`lon`/`speed_ms`.** Simplest, and destroys the only distinction
  the product is built on.
- **Add `smoothed_*` fields to `Sample`.** One row then carries two provenances, and the
  question "is this measured?" becomes a per-field answer instead of a per-row one.

## Consequences
- Downstream stages join the two tracks on `t`. That is a real cost, paid once per stage,
  and it is the cost of never being able to confuse the two.
- The API contract is unaffected for now: no endpoint serves a track yet, so `SmoothedSample`
  has no Zod mirror. The first endpoint that serves one owes the contract fixture a row and
  `web/` a schema — see `api/tests/test_contract_parity.py`.
- A session with no fix anywhere yields an empty track rather than an invented one.
- If a future stage genuinely needs one merged row per second, it builds that view itself
  and states which fields are estimates. It does not get to collapse these two shapes.
