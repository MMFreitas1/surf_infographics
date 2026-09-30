import type { Messages } from "./catalog";

/**
 * English, alongside `pt-PT` rather than above it.
 *
 * The design was drawn in Portuguese and this is the translation, not the source — where the
 * two disagree about tone, the Portuguese is the one that was designed.
 */
export const en: Messages = {
  "app.eyebrow": "MF CONCEPTS · TECHNOLOGY",
  "app.title": "Surf Analytics",
  "app.provenance": "Local-first · FIT · {spot}",
  "app.footer": "Session at {spot} · {samples} samples at 1 Hz",
  "app.provenanceNoSpot": "Local-first · FIT",
  "app.footerNoSpot": "{samples} samples at 1 Hz · break not yet identified",

  "tab.sessions": "Sessions",
  "tab.session": "Session",
  "tab.wave": "Wave",

  "method.eyebrow": "How these numbers are made",
  "method.body":
    "The numbers come from what your watch recorded, read carefully. Cleaning, finding the " +
    "session inside the recording and counting the waves are all deterministic — no model " +
    "decides a number. Every wave carries the reason it was counted. None of it has yet been " +
    "checked against a session labelled the day it was surfed, so these are proposals, not " +
    "validated measurements. Your data stays on this machine, not on a server.",
  "method.dismiss": "Understood",

  "hero.waves": "Waves",
  "hero.proposed": "proposed · no labelled session",
  "hero.ofProposals": "of {proposed} proposals",
  "hero.unresolved": "{count} undecided",

  "section.session": "The session",
  "section.conditions": "Sea state",
  "section.confidence": "What the watch saw",

  "aerobic.title": "Aerobic",
  "aerobic.coverageBadge": "100% COVERAGE",
  "aerobic.note":
    "Heart rate is the one signal with no gaps: it keeps recording with the wrist under water.",
  "aerobic.meanBpm": "mean bpm",
  "aerobic.maxBpm": "max bpm",
  "aerobic.duration": "duration",

  "confidence.title": "Device confidence",
  "confidence.watchSaw": "The watch saw",
  "confidence.blind": "blind — no position",
  "confidence.blindWindows": "{count} blind windows",
  "confidence.rejected": "{count} readings refused",
  "confidence.sessionSpan": "session found inside the recording",
  "confidence.excluded": "{minutes} min excluded — not surfing",

  "seaState.title": "Sea state",
  "seaState.unavailable": "unavailable — marine API not wired up yet",
  "quality.title": "Session quality",
  "quality.unavailable": "unavailable — no model has earned this job",

  "unit.minutes": "min",
  "unit.seconds": "s",
  "unit.bpm": "bpm",
  "state.loading": "loading…",
  "state.error": "Could not load the session.",
  "state.noSession": "Session not found.",
};
