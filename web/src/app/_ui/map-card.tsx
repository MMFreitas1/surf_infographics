"use client";

/**
 * The track card: imagery, the session drawn on it, playback, and what is selected.
 *
 * deck.gl is loaded lazily. It is the heaviest thing on the page and the rest of the screen
 * — the count, the aerobic panel, device confidence — is useful before a map has painted,
 * so nothing above waits on it.
 */
import dynamic from "next/dynamic";
import { useState } from "react";
import { percent } from "@/lib/format";
import { useLocale, useT } from "@/lib/i18n";
import type { BasemapInfo, SmoothedSample, WaveVerdict } from "@/lib/schema";
import type { Span } from "@/lib/trace";
import { Playback } from "./playback";

const TrackMap = dynamic(() => import("./track-map").then((m) => m.TrackMap), {
  ssr: false,
  loading: () => <div className="map-body map-loading" style={{ height: 470 }} />,
});

interface Props {
  samples: SmoothedSample[];
  waves: WaveVerdict[];
  basemap: BasemapInfo | null;
  apiBase: string;
  /** Stretches L0.6 says were not surfing. Drawn, but never as surfing (ADR-0015). */
  excluded: Span[];
}

export function MapCard({ samples, waves, basemap, apiBase, excluded }: Props) {
  const t = useT();
  const { locale } = useLocale();
  const [now, setNow] = useState(samples[0]?.t ?? 0);
  const [selected, setSelected] = useState<WaveVerdict | null>(null);

  return (
    <section className="panel map-card">
      <header className="panel-head">
        <p className="panel-eyebrow">{t("map.title")}</p>
      </header>

      <div className="map-frame">
        <TrackMap
          samples={samples}
          basemap={basemap}
          apiBase={apiBase}
          now={now}
          waves={waves}
          selected={selected}
          onSelect={setSelected}
          excluded={excluded}
        />

        {selected ? (
          <div className="selection-callout">
            <p className="selection-eyebrow">{t("selection.isolated")}</p>
            <p className="selection-meta">
              {t("selection.coverage", {
                percent: percent(locale, selected.position_coverage),
              })}{" "}
              · {t(`selection.decidedBy.${selected.decided_by}` as const)}
            </p>
            {/* The verdict's own words, carried to the screen unchanged. The pipeline
                committed to this wave and said why; paraphrasing it here would put a
                second, subtly different explanation into the product. */}
            <p className="selection-reason">{selected.reason}</p>
            <button type="button" className="button-ghost" onClick={() => setSelected(null)}>
              {t("selection.showAll")}
            </button>
          </div>
        ) : null}

        <div className="map-legend">
          <span>
            <span className="key key-measured" /> {t("legend.measured")}
          </span>
          <span>
            <span className="key key-estimated" /> {t("legend.estimated")}
          </span>
          <span>
            <span className="key key-excluded" /> {t("legend.excluded")}
          </span>
          {/* The imagery credit is rendered by maplibre itself, from the source's own
              `attribution` field -- so it appears exactly when imagery does, and vanishes
              with it offline. A second copy here duplicated it and overlapped the first. */}
        </div>
      </div>

      <Playback
        samples={samples}
        waves={waves}
        now={now}
        onNow={setNow}
        selected={selected}
        onSelect={setSelected}
      />
    </section>
  );
}
