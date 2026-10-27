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
import { defaultView, type LayerView } from "@/lib/basemap";
import { percent } from "@/lib/format";
import { useLocale, useT } from "@/lib/i18n";
import type { Messages } from "@/lib/i18n/catalog";
import type { BasemapInfo, Peak, SmoothedSample, WaveVerdict } from "@/lib/schema";
import type { Span } from "@/lib/trace";
import { Playback } from "./playback";

/**
 * What each layer is called. Keyed by the id the API serves, so a layer added there with no
 * name here still appears -- labelled by its id, which is ugly and visible, rather than
 * silently missing from the control.
 */
const LAYER_LABELS: Partial<Record<string, keyof Messages>> = {
  ocean: "layer.ocean",
  imagery: "layer.imagery",
  relief: "layer.relief",
};

/**
 * The one layer that hides what is under it rather than shading it, so the one with a
 * strength control. Blended over the sea floor is the view this feature exists for.
 */
const BLENDABLE = "imagery";

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
  /** Where the session sat still. Empty is a normal state -- a session that never held
   *  still for a minute has no sit spots, and that is an answer. */
  peaks?: Peak[];
  /**
   * Which wave is isolated. Held by the screen rather than here, because the profile
   * cards below open a wave *on this map* -- the N3 Onda screen waits on Phases 6 and 7,
   * and two copies of "which wave is selected" is how they come to disagree.
   */
  selected: WaveVerdict | null;
  onSelect: (wave: WaveVerdict | null) => void;
}

export function MapCard({
  samples,
  waves,
  basemap,
  apiBase,
  excluded,
  selected,
  onSelect,
  peaks = [],
}: Props) {
  const t = useT();
  const { locale } = useLocale();
  const [now, setNow] = useState(samples[0]?.t ?? 0);
  const [shown, setShown] = useState<readonly string[]>(() =>
    basemap ? defaultView(basemap).shown : [],
  );
  const [blend, setBlend] = useState(1);

  // Order is the style's, never this list's: a tick says whether a layer draws, not where.
  const view: LayerView = { shown, opacity: { [BLENDABLE]: blend } };

  function toggle(id: string) {
    setShown((on) => (on.includes(id) ? on.filter((other) => other !== id) : [...on, id]));
  }

  return (
    <section className="panel map-card">
      <header className="panel-head">
        <p className="panel-eyebrow">{t("map.title")}</p>
      </header>

      <div className="map-frame">
        <TrackMap
          samples={samples}
          basemap={basemap}
          layerView={view}
          apiBase={apiBase}
          now={now}
          waves={waves}
          selected={selected}
          onSelect={onSelect}
          excluded={excluded}
          peaks={peaks}
        />

        {basemap && basemap.layers.length > 1 ? (
          <div className="layer-control">
            {basemap.layers.map((layer) => {
              const label = LAYER_LABELS[layer.id];
              return (
                <label key={layer.id} className="layer-tick">
                  <input
                    type="checkbox"
                    checked={shown.includes(layer.id)}
                    onChange={() => toggle(layer.id)}
                  />
                  {label ? t(label) : layer.id}
                </label>
              );
            })}
            {shown.includes(BLENDABLE) ? (
              <label className="layer-blend">
                {t("layer.blend")}
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(blend * 100)}
                  onChange={(event) => setBlend(Number(event.target.value) / 100)}
                  aria-label={t("layer.blend")}
                />
              </label>
            ) : null}
          </div>
        ) : null}

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
            <button type="button" className="button-ghost" onClick={() => onSelect(null)}>
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
          {peaks.length > 0 ? (
            <span>
              <span className="key key-sit" /> {t("map.sitSpots")}
            </span>
          ) : null}
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
        onSelect={onSelect}
      />
    </section>
  );
}
