"use client";

/**
 * The N2 panels this PR can fill honestly, and the designed absence for the ones it cannot.
 *
 * Three of the Session screen's panels have no data source until Phases 6, 8 and 11. They
 * render `Unavailable`, which is a **designed state and not an error** — the handover is
 * explicit that absence is part of the language, and a placeholder pretending to be a swell
 * card would be the one thing the whole design exists to prevent.
 */
import { integer, minutes, percent } from "@/lib/format";
import { useLocale, useT } from "@/lib/i18n";
import type { Messages } from "@/lib/i18n/catalog";
import type { AuditReport, CleanReport, SessionVerdict } from "@/lib/schema";

/**
 * The count, at 104px. The biggest element on the dashboard, and the reason PR 0 existed.
 *
 * It renders `wave_count` flat, with no per-number hedging: the pipeline committed to this
 * and the method banner carries the caveat for the whole session. What it *does* show is
 * how the number was reached — how many proposals it came from, and how many the rule could
 * not settle — because a count you cannot take apart is a count you cannot check.
 */
export function HeroCount({ verdict }: { verdict: SessionVerdict }) {
  const t = useT();
  const { locale } = useLocale();
  return (
    <section className="hero">
      <p className="hero-value">{integer(locale, verdict.wave_count)}</p>
      <div className="hero-meta">
        <p className="hero-label">{t("hero.waves")}</p>
        <p className="hero-sub">{t("hero.ofProposals", { proposed: verdict.proposed_count })}</p>
        {verdict.unresolved_count > 0 ? (
          <p className="hero-sub hero-unresolved">
            {t("hero.unresolved", { count: verdict.unresolved_count })}
          </p>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Heart rate: the only channel with no gaps.
 *
 * The badge is not decoration. Every other number on this screen is qualified by coverage,
 * and this one genuinely is not — heart rate is present for 100% of seconds on the reference
 * session, blind windows included. Saying so is what makes the qualifications elsewhere
 * mean something.
 */
export function AerobicPanel({
  meanBpm,
  maxBpm,
  durationS,
}: {
  meanBpm: number | null;
  maxBpm: number | null;
  durationS: number;
}) {
  const t = useT();
  const { locale } = useLocale();
  if (meanBpm === null || maxBpm === null) {
    return <Unavailable title="aerobic.title" message="quality.unavailable" />;
  }
  return (
    <section className="panel panel-ink">
      <header className="panel-head">
        <p className="panel-eyebrow panel-eyebrow-ink">{t("aerobic.title")}</p>
        <span className="badge">{t("aerobic.coverageBadge")}</span>
      </header>
      <div className="stat-row">
        <Stat value={integer(locale, meanBpm)} label={t("aerobic.meanBpm")} onInk />
        <Stat value={integer(locale, maxBpm)} label={t("aerobic.maxBpm")} onInk />
        <Stat
          value={minutes(locale, durationS)}
          unit={t("unit.minutes")}
          label={t("aerobic.duration")}
          onInk
        />
      </div>
      <p className="panel-note">{t("aerobic.note")}</p>
    </section>
  );
}

/**
 * What the watch actually saw, and what was refused on the way here.
 *
 * Coverage, blind windows, L0.5's rejections and L0.6's exclusion, in one place. This is the
 * panel that makes the rest of the screen legible: a session the watch saw half of is a
 * different object from one it saw throughout, and the reader is entitled to know which one
 * they are looking at before they read anything else.
 */
export function DeviceConfidence({
  cleaning,
  audit,
  blindWindows,
}: {
  cleaning: CleanReport;
  audit: AuditReport;
  blindWindows: number;
}) {
  const t = useT();
  const { locale } = useLocale();
  const seen = cleaning.coverage_after;
  return (
    <section className="panel">
      <p className="panel-eyebrow">{t("confidence.title")}</p>
      <div className="coverage-bar" role="img" aria-label={t("confidence.watchSaw")}>
        <span className="coverage-seen" style={{ width: `${seen * 100}%` }} />
      </div>
      <div className="coverage-key">
        <span>
          <strong>{percent(locale, seen)}</strong> {t("confidence.watchSaw")}
        </span>
        <span className="muted">
          <strong>{percent(locale, 1 - seen)}</strong> {t("confidence.blind")}
        </span>
      </div>
      <ul className="fact-list">
        <li>{t("confidence.blindWindows", { count: integer(locale, blindWindows) })}</li>
        <li>{t("confidence.rejected", { count: integer(locale, cleaning.rejections.length) })}</li>
        {audit.decided ? (
          <li>
            {t("confidence.excluded", { minutes: minutes(locale, audit.excluded_s) })} ·{" "}
            {t("confidence.sessionSpan")}
          </li>
        ) : null}
      </ul>
    </section>
  );
}

/**
 * A panel whose data source does not exist yet. A designed state, never an error.
 *
 * `title` is optional because a band holding one panel is already named by its section
 * header, and repeating it there reads as a mistake rather than as structure.
 */
export function Unavailable({
  title,
  message,
}: {
  title?: keyof Messages;
  message: keyof Messages;
}) {
  const t = useT();
  return (
    <section className="panel panel-absent">
      {title ? <p className="panel-eyebrow">{t(title)}</p> : null}
      <p className="absent-message">{t(message)}</p>
    </section>
  );
}

function Stat({
  value,
  unit,
  label,
  onInk,
}: {
  value: string;
  unit?: string;
  label: string;
  onInk?: boolean;
}) {
  return (
    <div className={onInk ? "stat stat-ink" : "stat"}>
      <p className="stat-value">
        {value}
        {unit ? <span className="stat-unit">{unit}</span> : null}
      </p>
      <p className="stat-label">{label}</p>
    </div>
  );
}
