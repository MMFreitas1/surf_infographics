# ADR-0012: Labeling is blind first, and assisted labels stay out of the metric

**Status:** accepted · 2026-08-30

## Context

Phase 4 builds the UI a person marks waves in. Everything downstream is scored against what
comes out of it, so the question of *what the labeller can see while labelling* is not a UI
detail — it decides what a precision/recall number in Phase 5 will actually mean.

L3 already proposes candidate intervals, and showing them makes labelling far faster: a
session becomes a list of proposals to confirm or reject instead of an hour of scrubbing.
The cost is that human labels then inherit the detector's blind spots. Phase 3 measured
exactly which rides L3 misses — the mostly-blind ones — and a labeller whose eye is drawn
along L3's proposals will tend to miss the same ones. Score the detector against those
labels and the number reports agreement, not accuracy. That is ADR-0008's objection
(*their errors, no information*) arriving from inside the project rather than from a third
party.

## Decision

**1. The blind pass comes first, and it is gated server-side.**

A session is labelled with no candidates on screen. Completing that sweep is recorded as a
`label_passes` row — not inferred from a label count, because "nobody has opened this
session" and "somebody swept it carefully and found no rides" must not look alike. Only
once a blind pass exists may a second, assisted sweep run with L3's proposals visible.

Assisted labels are stored `source='human_assisted'`. They are real human judgement and are
kept: rejecting a bad proposal is information. They are excluded from `counts_as_truth`, so
they never enter a metric. The rule lives in `LabelRepository` and in the endpoints, not in
the front end — a rule only the UI knows is a rule the next caller breaks.

**2. The labeller sees speed, cross-shore velocity, and the track.**

Speed alone cannot separate a ride from a hard paddle-out; the sign of cross-shore velocity
can, and the plan view shows the shape. Measured seconds, estimated seconds and blind
windows render as three visibly different things in every panel (ADR-0010), and the
`±position_sigma_m` band is drawn, so "what we do not know" is on screen in metres.

**3. Charts use Observable Plot; the map uses deck.gl — as `docs/architecture.md` §2 already
named.** The MapTiler basemap degrades to a bare track when there is no key and no network,
because §7 requires the app to work fully offline.

## Consequences

- Labelling one session takes two sweeps. That is the price of an unanchored set to measure
  the anchored one against, and it is paid once per session.
- `LabelSource` gains a third member, and `counts_as_truth` now carries two jobs: keeping
  unverified imports out (ADR-0006) and keeping candidate-anchored labels out.
- Phase 5 can report two recall numbers — against blind labels, and against blind plus
  assisted. The first is the honest one; the gap between them is itself a measurement of how
  much the detector's suggestions move a human.
- Deleting an activity that carries labels now fails rather than cascading. Everything else
  in the database can be recomputed; labels cannot.

## What the real session already says about this

Both numbers below come from running the new endpoints over the reference FIT session
(`GET /activities/{id}/track` and `/candidates`), and both were surprises worth recording
before the UI is built on top of them:

- **The reference session's frame is not reliable.** Coherence is 0.365 against a 0.85
  threshold, on an effective sample of 125.7 seconds. So on the first real session anyone
  will label, the shore axis is *not* trustworthy, and the "unreliable frame" rendering path
  is the default case rather than an edge case. Phase 3's 0.51° bearing error was measured on
  the synthetic session, where rides dominate the velocity sum; a real session is mostly
  paddling and sitting.
- **L3 proposes 22 intervals on the real session, not 9.** The nine-proposal figure quoted in
  PLAN.md is the *synthetic* session's, pinned in `evals/goldens/synthetic_session_v1.json`.
  On the real session 2 proposals have zero position coverage and a further 8 are under 25%,
  which means the "which of these can I trust" problem the UI has to solve is roughly twice
  the size the plan assumed.
