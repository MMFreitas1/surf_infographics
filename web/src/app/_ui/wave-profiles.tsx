"use client";

/**
 * Perfis de onda: one small card per settled wave, with the ride's own track on it.
 *
 * The profile is the **GPS trace of the ride, not a speed curve**, as the handover
 * specifies. That is also the more honest of the two: a ride's shape is something the watch
 * recorded, where a speed curve drawn through a blind window would be a picture of the
 * smoother's estimate presented as a measurement. The estimated stretches are dashed here
 * for the same reason they are dashed on the big map (ADR-0010).
 *
 * **Coverage is the card's opacity.** A wave the watch barely saw is barely there. The
 * badge says the figure as well, because a design that only whispers is not a design that
 * tells you anything.
 *
 * Two things from the prototype are deliberately not here:
 *
 * - **The delete button.** Removing a wave from the screen would be the UI overriding the
 *   pipeline's answer. L5 commits to the count and says why; a correction belongs on the
 *   labelling screen, which is append-only and already exists.
 * - **The trophy on the best wave.** The prototype ranked waves with
 *   `top * duration * (0.4 + coverage)`, a formula invented in the browser. No stage has
 *   committed to a best wave, so no card claims one.
 */
import { MINI, miniTrack } from "@/lib/chart";
import { integer, kmh, percent } from "@/lib/format";
import { useLocale, useT } from "@/lib/i18n";
import type { SmoothedSample, WaveMetrics } from "@/lib/schema";

/**
 * Which way the ride went, where the pipeline will stand behind it.
 *
 * **An unknown direction renders as nothing at all**, not as a dash or a shrug. There are
 * two ways a wave has no direction and both are honest: the watch saw under two seconds of
 * it, or the session's frame never established which way the sea is (ADR-0022). Drawing a
 * placeholder would make a designed silence look like a missing value.
 *
 * The confidence is **not** printed as a number. It is not a calibrated probability and must
 * never be rendered as one (ADR-0013), so it only ever modulates how firmly the chip is
 * drawn — a marginal left looks marginal. Ride 11 of the reference session is the case that
 * matters: a right at 9.1° off dead-shoreward, which is a real call and a thin one.
 */
function Direction({ wave }: { wave: WaveMetrics }) {
  const t = useT();
  if (wave.direction === "unknown") return null;

  const confidence = wave.direction_confidence ?? 0;
  return (
    <span
      className={`profile-direction profile-direction-${wave.direction}`}
      style={{ opacity: 0.45 + confidence * 0.55 }}
      title={t("direction.label")}
    >
      {t(`direction.${wave.direction}`)}
    </span>
  );
}

/** The four bars of the coverage glyph light up at these fractions. */
const STEPS = [0, 0.25, 0.5, 0.75];

export function WaveProfiles({
  waves,
  samples,
  selectedStart,
  onOpen,
}: {
  waves: WaveMetrics[];
  samples: SmoothedSample[];
  /** `t_start` of the wave isolated on the map above, so the grid can show which. */
  selectedStart: number | null;
  onOpen: (wave: WaveMetrics) => void;
}) {
  const t = useT();

  if (waves.length === 0) {
    return (
      <section className="chart-card chart-card-absent">
        <p className="panel-eyebrow">{t("profiles.title")}</p>
        <p className="absent-message">{t("profiles.unavailable")}</p>
      </section>
    );
  }

  return (
    <section className="chart-card">
      <p className="panel-eyebrow">{t("profiles.title")}</p>
      <div className="profile-grid">
        {waves.map((wave) => (
          <Profile
            key={wave.t_start}
            wave={wave}
            samples={samples}
            selected={wave.t_start === selectedStart}
            onOpen={onOpen}
          />
        ))}
      </div>
    </section>
  );
}

function Profile({
  wave,
  samples,
  selected,
  onOpen,
}: {
  wave: WaveMetrics;
  samples: SmoothedSample[];
  selected: boolean;
  onOpen: (wave: WaveMetrics) => void;
}) {
  const t = useT();
  const { locale } = useLocale();

  const { paths, start } = miniTrack(
    samples.filter((s) => s.t >= wave.t_start && s.t < wave.t_end),
  );
  const cover = wave.position_coverage;

  return (
    <div className="profile-slot">
      <button
        type="button"
        className={selected ? "flip-card flip-card-selected" : "flip-card"}
        onClick={() => onOpen(wave)}
        aria-label={`${t("profiles.open")} ${wave.index}`}
      >
        <span className="flip-front" style={{ opacity: 0.55 + cover * 0.45 }}>
          <span className="profile-head">
            <span className="profile-no">{String(wave.index).padStart(2, "0")}</span>
            <span className={`profile-badge ${badgeOf(cover)}`}>
              <Signal cover={cover} label={t("profiles.signal")} />
              {percent(locale, cover)}
            </span>
          </span>

          <Direction wave={wave} />

          <svg className="profile-track" viewBox={`0 0 ${MINI.width} ${MINI.height}`} aria-hidden>
            {paths.map((path) => (
              <path
                key={path.d}
                className={path.series === "measured" ? "profile-measured" : "profile-estimated"}
                d={path.d}
              />
            ))}
            {start ? <circle className="profile-start" cx={start.x} cy={start.y} r={2} /> : null}
          </svg>

          <span className="profile-foot">
            <span className="profile-figure">
              <span className="profile-value">
                {wave.avg_speed_ms === null ? "—" : kmh(locale, wave.avg_speed_ms, 0)}
              </span>
              <span className="profile-unit">{t("unit.kmh")}</span>
            </span>
            <span className="profile-figure profile-figure-end">
              <span className="profile-value">{integer(locale, wave.duration_s)}</span>
              <span className="profile-unit">{t("unit.secondsLong")}</span>
            </span>
          </span>
        </span>

        <span className="flip-back">
          <svg width="13" height="13" viewBox="0 0 12 12" fill="none" aria-hidden>
            <path
              d="M2 6h8M6.5 2.5 10 6l-3.5 3.5"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="profile-back-label">{t("profiles.open")}</span>
        </span>
      </button>
    </div>
  );
}

/** Four bars, lit by how much of the ride the watch actually had a position for. */
function Signal({ cover, label }: { cover: number; label: string }) {
  return (
    <svg className="profile-signal" width="11" height="11" viewBox="0 0 12 12" role="img">
      <title>{label}</title>
      {STEPS.map((step, i) => (
        <path
          key={step}
          d={`M${1.5 + i * 3} ${8.5 - i * 2.05}v${1.6 + i * 2.05}`}
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          opacity={cover > step || (step === 0 && cover > 0) ? 1 : 0.28}
        />
      ))}
    </svg>
  );
}

/** Three bands, so the badge reads at a glance before the number is read at all. */
function badgeOf(cover: number): string {
  if (cover >= 0.6) return "profile-badge-high";
  if (cover >= 0.25) return "profile-badge-mid";
  return "profile-badge-low";
}
