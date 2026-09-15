repo: MMFreitas1/surf_infographics
branch: main

## Last sync
date: 2026-08-31T14:52:00Z

### Updated in this project
- Read the honesty rules, data findings and existing labelling UI to ground the design pass.
- Built the three-level drill-down (Sessions · Session · Wave) as one working prototype.
- Proposed a new measured / estimated / blind language: solid · dashed-translucent · absence + a dedicated blind rail (replaces the hatch that had to be lightened twice).
- Coverage rendered as typographic weight + a coverage arc, so a 12%-coverage number reads weaker than a 100% one at card size.

## Screen map
| Project screen | Built from |
|---|---|
| Sessions (Level 1) | `docs/data-findings.md`, `web/src/lib/schema.ts` (ActivitySummary), `uploads/DESIGN_BRIEF.md` §4 |
| Session (Level 2) | `web/src/app/label/[id]/session-view.tsx`, `track-map.tsx`, `web/src/app/globals.css`, `docs/data-findings.md` §2–4 |
| Wave (Level 3) | `web/src/lib/schema.ts` (WaveCandidate, RideDirection, certaintyOf), `uploads/DESIGN_BRIEF.md` §6 |
| measured/estimated/blind language | `web/src/app/globals.css` (`--measured`/`--estimated`/`--unknown`, `.band-blind`), ADR-0010 |
