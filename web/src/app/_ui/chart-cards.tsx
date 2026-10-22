"use client";

/**
 * The Session screen's four chart cards: Distância, Cadência, Velocidade, Retorno.
 *
 * Every figure here is read from `GET /activities/{id}/metrics` and none is derived. The
 * browser's only arithmetic is turning a number into a coordinate, which is what
 * `@/lib/chart` is for and why it is tested on its own.
 *
 * Two of the four depart from the handover on purpose, and the departures are the honest
 * part:
 *
 * - **Cadência** was drawn as `braçadas / min`, a paddle stroke rate. The watch records no
 *   stroke channel for surfing and the prototype faked the series from wave gaps. The card
 *   keeps its name and its geometry and plots what is actually counted: waves per block.
 * - **Velocidade** is about the seconds spent on a wave, not every second in the water.
 *   L6 distributes both; this card takes `ride_speed`, and says how many seconds that is.
 *
 * A figure the recording cannot support renders the card's absent state. Never a zero: 0.0
 * km is a measurement, and "this file has no odometer" is not.
 */
import {
  areaPath,
  type Bar,
  gridLines,
  headroom,
  histogram,
  linePath,
  SERIES,
  seriesBars,
  seriesPoints,
  speedX,
} from "@/lib/chart";
import { decimal, distance, integer, kmh, minutes } from "@/lib/format";
import { useLocale, useT } from "@/lib/i18n";
import type { Messages } from "@/lib/i18n/catalog";
import type { SessionMetrics } from "@/lib/schema";

/**
 * Total, split between the paddle out and the ride in — and, under the ride, the part of it
 * the watch actually had a position for.
 *
 * The design has two readout cells and L6 ships three numbers. The third sits under the one
 * it qualifies rather than beside it, because `ride_m` and `ride_measured_m` are not two
 * comparable quantities: one is what the odometer attributed to the rides, the other is how
 * much of that the watch saw. They differ by exactly what was not measured.
 */
export function DistanceCard({ metrics }: { metrics: SessionMetrics }) {
  const t = useT();
  const { locale } = useLocale();

  if (metrics.distance_m === null) {
    return <ChartCard title="distance.title" absent="distance.unavailable" />;
  }

  const swim = metrics.swim_m ?? 0;
  const ride = metrics.ride_m ?? 0;
  const span = Math.max(1, swim + ride);
  const total = distance(locale, metrics.distance_m);
  const measured =
    metrics.ride_measured_m === null ? null : distance(locale, metrics.ride_measured_m);

  return (
    <ChartCard title="distance.title">
      <p className="chart-value">
        {total.value}
        <span className="chart-unit">{t(total.unit)}</span>
      </p>
      <div className="split-bar" role="img" aria-label={t("distance.title")}>
        <span className="split-swim" style={{ width: `${(swim / span) * 100}%` }} />
        <span className="split-ride" style={{ width: `${(ride / span) * 100}%` }} />
      </div>
      <div className="split-readout">
        <Readout swatch="split-swim" label={t("distance.swim")} metres={swim} />
        <Readout swatch="split-ride" label={t("distance.ride")} metres={ride}>
          {measured === null
            ? null
            : t("distance.measured", { value: measured.value, unit: t(measured.unit) })}
        </Readout>
      </div>
    </ChartCard>
  );
}

/**
 * How the waves fell across the session, ten minutes at a time.
 *
 * Counts, not a rate per block: the last block is usually short, and dividing two waves by
 * five minutes to claim four per ten is an extrapolation from a sample of five minutes. The
 * short block is drawn hollow and named underneath instead, and the headline rate is L6's,
 * measured over the whole session.
 */
export function CadenceCard({ metrics }: { metrics: SessionMetrics }) {
  const t = useT();
  const { locale } = useLocale();

  if (metrics.cadence.length === 0) {
    return <ChartCard title="cadence.title" absent="cadence.unavailable" />;
  }

  const blocks = metrics.cadence;
  const values = blocks.map((block) => block.waves);
  const top = headroom(values, 1.14);
  const points = seriesPoints(values, top);
  const partial = blocks.findIndex((b) => b.t_end - b.t_start < metrics.bucket_s);

  return (
    <ChartCard title="cadence.title">
      <svg className="chart-svg" viewBox="0 0 400 168" role="img" aria-label={t("cadence.axis")}>
        <title>{t("cadence.axis")}</title>
        {gridLines().map((y) => (
          <line key={y} className="chart-grid" x1={SERIES.left} y1={y} x2={SERIES.right} y2={y} />
        ))}
        <path className="cadence-area" d={areaPath(points)} />
        <path className="cadence-line" d={linePath(points)} />
        {points.map((point, i) => (
          <circle
            key={blocks[i]?.t_start}
            className={i === partial ? "chart-dot chart-dot-partial" : "chart-dot"}
            cx={point.x}
            cy={point.y}
            r={3}
          />
        ))}
        <line
          className="chart-baseline"
          x1={SERIES.left}
          y1={SERIES.baseline}
          x2={SERIES.right}
          y2={SERIES.baseline}
        />
        <text className="chart-axis" x={SERIES.left} y={12}>
          {t("cadence.axis")}
        </text>
        <text className="chart-lead chart-lead-blue" x={SERIES.right} y={12} textAnchor="end">
          {t("cadence.rate", { value: decimal(locale, metrics.waves_per_10min) })}
        </text>
        <text className="chart-tick" x={SERIES.left} y={148}>
          {t("cadence.firstBlock")}
        </text>
        <text className="chart-tick" x={SERIES.right} y={148} textAnchor="end">
          {t("cadence.lastBlock", { count: blocks.length })}
        </text>
      </svg>
      {partial >= 0 ? (
        <p className="chart-note">
          {t("cadence.partialBlock", {
            minutes: minutes(
              locale,
              (blocks[partial]?.t_end ?? 0) - (blocks[partial]?.t_start ?? 0),
            ),
          })}
        </p>
      ) : null}
    </ChartCard>
  );
}

/**
 * The speed of the seconds spent riding, on a fixed 0–40 km/h axis.
 *
 * `ride_speed`, never `speed`: a session is mostly paddling, so the same chart over every
 * observed second describes the paddling and calls it surfing.
 *
 * **The bars are measured; the curve the handover drew was not.** The design specified a
 * normal curve from the mean and the standard deviation, which assumes the riding seconds
 * are one symmetric population. They are not: on the reference session they peak at 23–25
 * km/h, well above their own 16.8 mean, because a ride is a slow take-off, a fast middle
 * and a slow kick-out. Drawn as a bell, the card puts its tallest point where the data has
 * a dip and shades 0–5 km/h where not one second was recorded. The mean and ±1σ stay, as
 * the design's furniture over the real shape — they are true, and they are now visibly a
 * summary of the bars rather than a substitute for them.
 */
export function SpeedCard({ metrics }: { metrics: SessionMetrics }) {
  const t = useT();
  const { locale } = useLocale();
  const ride = metrics.ride_speed;

  if (ride === null) {
    return <ChartCard title="speed.title" absent="speed.unavailable" />;
  }

  const meanKmh = ride.mean_ms * 3.6;
  const sdKmh = ride.sd_ms * 3.6;
  const measured = histogram(ride.bin_edges_ms, ride.counts);

  return (
    <ChartCard title="speed.title">
      <svg className="chart-svg" viewBox="0 0 400 156" role="img" aria-label={t("speed.axis")}>
        <title>{t("speed.axis")}</title>
        <Bars measured={measured} />
        <line className="speed-mean" x1={speedX(meanKmh)} y1={14} x2={speedX(meanKmh)} y2={118} />
        <SdLine kmh={meanKmh - sdKmh} />
        <SdLine kmh={meanKmh + sdKmh} />
        <line className="chart-baseline" x1={0} y1={118} x2={400} y2={118} />
        {[0, 10, 20, 30, 40].map((v) => (
          <text key={v} className="chart-tick" x={speedX(v)} y={132} textAnchor="middle">
            {integer(locale, v)}
          </text>
        ))}
        <text className="chart-axis" x={200} y={150} textAnchor="middle">
          {t("speed.axis")}
        </text>
        <text
          className="chart-lead chart-lead-amber"
          x={speedX(meanKmh)}
          y={11}
          textAnchor="middle"
        >
          {t("speed.mean", { value: kmh(locale, ride.mean_ms) })}
        </text>
        <text className="chart-sigma" x={speedX(meanKmh - sdKmh)} y={44} textAnchor="middle">
          {t("speed.sdLow")}
        </text>
        <text className="chart-sigma" x={speedX(meanKmh + sdKmh)} y={44} textAnchor="middle">
          {t("speed.sdHigh")}
        </text>
      </svg>
      <p className="chart-note">
        {t("speed.sample", {
          seconds: integer(locale, ride.n_seconds),
          waves: integer(locale, metrics.wave_count),
        })}
        {measured.overflow
          ? ` · ${t("speed.overflow", { seconds: integer(locale, measured.overflow.seconds) })}`
          : null}
      </p>
    </ChartCard>
  );
}

/**
 * The paddle back out, wave by wave.
 *
 * `returns` has one fewer entry than there are waves — it measures the gaps between them —
 * so a session with a single wave has nothing to draw and says so.
 */
export function ReturnCard({ metrics }: { metrics: SessionMetrics }) {
  const t = useT();
  const { locale } = useLocale();

  if (metrics.returns.length === 0) {
    return <ChartCard title="returns.title" absent="returns.unavailable" />;
  }

  const values = metrics.returns.map((gap) => gap.seconds / 60);
  const top = headroom(values, 1.18);
  const points = seriesPoints(values, top);
  const bars = seriesBars(values, top);

  return (
    <ChartCard title="returns.title">
      <svg className="chart-svg" viewBox="0 0 400 168" role="img" aria-label={t("returns.axis")}>
        <title>{t("returns.axis")}</title>
        {gridLines().map((y) => (
          <line key={y} className="chart-grid" x1={SERIES.left} y1={y} x2={SERIES.right} y2={y} />
        ))}
        {bars.map((bar, i) => (
          <rect
            key={metrics.returns[i]?.after_wave}
            className="return-bar"
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={bar.height}
            rx={1}
          />
        ))}
        <path className="return-line" d={linePath(points)} />
        {points.map((point, i) => (
          <circle
            key={metrics.returns[i]?.after_wave}
            className="chart-dot chart-dot-amber"
            cx={point.x}
            cy={point.y}
            r={3}
          />
        ))}
        <line
          className="chart-baseline"
          x1={SERIES.left}
          y1={SERIES.baseline}
          x2={SERIES.right}
          y2={SERIES.baseline}
        />
        <text className="chart-axis" x={SERIES.left} y={12}>
          {t("returns.axis")}
        </text>
        <text className="chart-lead chart-lead-amber" x={SERIES.right} y={12} textAnchor="end">
          {metrics.return_mean_s === null
            ? ""
            : t("returns.mean", { value: decimal(locale, metrics.return_mean_s / 60) })}
        </text>
        <text className="chart-tick" x={SERIES.left} y={148}>
          {t("returns.firstWave", { count: metrics.returns[0]?.after_wave ?? 1 })}
        </text>
        <text className="chart-tick" x={SERIES.right} y={148} textAnchor="end">
          {t("returns.lastWave", { count: metrics.returns.at(-1)?.after_wave ?? 1 })}
        </text>
      </svg>
      {metrics.return_median_s === null ? null : (
        <p className="chart-note">
          {t("returns.median", { value: decimal(locale, metrics.return_median_s / 60) })}
        </p>
      )}
    </ChartCard>
  );
}

/** The measured one: L6's bins, with anything past the axis kept and marked. */
function Bars({ measured }: { measured: ReturnType<typeof histogram> }) {
  return (
    <>
      {measured.bars.map((bar: Bar) => (
        <rect
          key={bar.x}
          className="speed-bar"
          x={bar.x}
          y={bar.y}
          width={bar.width}
          height={bar.height}
          rx={1}
        />
      ))}
      {measured.overflow ? (
        <rect
          className="speed-bar speed-bar-overflow"
          x={measured.overflow.x}
          y={measured.overflow.y}
          width={measured.overflow.width}
          height={measured.overflow.height}
          rx={1}
        />
      ) : null}
    </>
  );
}

function SdLine({ kmh: at }: { kmh: number }) {
  return <line className="speed-sd" x1={speedX(at)} y1={48} x2={speedX(at)} y2={118} />;
}

function Readout({
  swatch,
  label,
  metres,
  children,
}: {
  swatch: string;
  label: string;
  metres: number;
  children?: React.ReactNode;
}) {
  const { locale } = useLocale();
  const t = useT();
  const shown = distance(locale, metres);
  return (
    <div className="readout">
      <span className="readout-label">
        <span className={`readout-swatch ${swatch}`} />
        {label}
      </span>
      <span className="readout-value">
        {shown.value}
        <span className="chart-unit">{t(shown.unit)}</span>
      </span>
      {children ? <span className="readout-sub">{children}</span> : null}
    </div>
  );
}

function ChartCard({
  title,
  absent,
  children,
}: {
  title: keyof Messages;
  absent?: keyof Messages;
  children?: React.ReactNode;
}) {
  const t = useT();
  return (
    <section className={absent ? "chart-card chart-card-absent" : "chart-card"}>
      <p className="panel-eyebrow">{t(title)}</p>
      {absent ? <p className="absent-message">{t(absent)}</p> : children}
    </section>
  );
}
