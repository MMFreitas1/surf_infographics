/**
 * The message catalogue's shape, and the rule that makes it worth having.
 *
 * **No component may hold a string literal.** The design ships Portuguese; the product
 * follows the user's system locale (PLAN.md, 2026-09-15), so `pt-PT` is the first catalogue
 * rather than the only one. A hard-coded label is the exact bug this decision exists to
 * prevent, and it is cheapest to enforce from the first screen rather than retrofit.
 *
 * `Messages` being a closed type is what enforces it: adding a key to one catalogue without
 * adding it to the other fails `tsc`, so no locale can silently fall back to English.
 */
export interface Messages {
  /** Masthead and chrome. */
  "app.eyebrow": string;
  "app.title": string;
  "app.provenance": string;
  "app.footer": string;
  /** Used until Phase 6 names the break from the coastline lookup. The device id is not a
   *  place, and "Session at garmin:3291" reads like one. */
  "app.provenanceNoSpot": string;
  "app.footerNoSpot": string;

  /** The three levels of the drill-down. */
  "tab.sessions": string;
  "tab.session": string;
  "tab.wave": string;

  /** The method banner: where "proposed" is stated, once per session. */
  "method.eyebrow": string;
  "method.body": string;
  "method.dismiss": string;

  /** N2 hero. */
  "hero.waves": string;
  "hero.proposed": string;
  "hero.ofProposals": string;
  "hero.unresolved": string;

  /** The track map, its playback and its legend. */
  "map.title": string;
  "map.attribution": string;
  "playback.play": string;
  "playback.pause": string;
  "playback.scrub": string;
  "playback.step": string;
  "legend.measured": string;
  "legend.estimated": string;
  "legend.wave": string;
  "legend.blind": string;
  "legend.excluded": string;
  "selection.isolated": string;
  "selection.showAll": string;
  "selection.coverage": string;
  "selection.decidedBy.rule": string;
  "selection.decidedBy.model": string;
  "selection.decidedBy.unresolved": string;

  /** Section headers. */
  "section.track": string;
  "section.session": string;
  "section.conditions": string;
  "section.confidence": string;

  /** Aerobic panel — the one gap-free signal. */
  "aerobic.title": string;
  "aerobic.coverageBadge": string;
  "aerobic.note": string;
  "aerobic.meanBpm": string;
  "aerobic.maxBpm": string;
  "aerobic.duration": string;

  /** Device confidence. */
  "confidence.title": string;
  "confidence.watchSaw": string;
  "confidence.blind": string;
  "confidence.blindWindows": string;
  "confidence.rejected": string;
  "confidence.sessionSpan": string;
  "confidence.excluded": string;

  /** Panels whose data source does not exist yet. A designed state, not an error. */
  "seaState.title": string;
  "seaState.unavailable": string;
  "quality.title": string;
  "quality.unavailable": string;

  /** Shared. */
  "unit.minutes": string;
  "unit.seconds": string;
  "unit.bpm": string;
  "state.loading": string;
  "state.error": string;
  "state.noSession": string;
}

export type LocaleTag = "pt-PT" | "en";

/** Every locale the product ships. `pt-PT` first: it is the one the design was drawn in. */
export const LOCALES: readonly LocaleTag[] = ["pt-PT", "en"] as const;

export const DEFAULT_LOCALE: LocaleTag = "en";
