# ADR-0009: Developer fields are skipped by declared size, never decoded

**Status:** accepted · 2026-08-30

## Context
ADR-0008 decided the pipeline consumes no third-party derived data. That is a policy; this
is the mechanism that makes it true in code rather than by intention.

A FIT definition message can declare a block of *developer fields* after its normal fields.
Resolving what those fields mean requires decoding `field_description` messages (global
message 206) in a first pass, then re-reading the file with the resulting names — which is
what the `research/fit_probe.py` spike does, and how it recovered `waveplot`, `wavenum` and
the Connect IQ app's thresholds.

The obvious risk with a decoder that *can* name those fields is that someone later reads one
"just for a moment", and the boundary ADR-0008 draws quietly stops holding.

## Decision
`api/src/surf/ingest/fit.py` steps over the developer-field block using the **byte size each
field declares in the definition message**, and never interprets it.

Every definition message already states the width of every developer field, so the parser
does not need `field_description` to stay byte-aligned. Measured on the reference session,
walking the file this way consumes exactly to the declared data end — 194186 of 194186 bytes,
with only the 2 CRC bytes trailing — across 33 definition messages, 3 of which declare
developer blocks totalling 22 field slots.

The decoder therefore has **no code path that can produce a developer value at all**. Message
206 is not in the set of messages it reads.

## Consequences
- The parser is simpler than the spike: one pass, no name resolution, no `devbt` table.
- ADR-0008 is enforced structurally. Reading a Connect IQ field would require adding a
  capability the decoder does not have, which is a visible change in a review.
- A regression test asserts that no developer value reaches the canonical `Activity`
  (`test_developer_fields_are_skipped_without_shifting_alignment`, and the reference check
  `test_no_connect_iq_developer_field_reaches_the_activity`).
- If a specific question ever needs those fields, `research/fit_probe.py` still answers it.
  That is research, not a runtime dependency.
