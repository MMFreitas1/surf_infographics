"use client";

/**
 * The session on satellite imagery, with measured and estimated drawn as different things.
 *
 * Basemap tiles come from **this project's own API**, not from Esri directly: the API keeps
 * them on disk so a session opens with no network after the first visit, which
 * `architecture.md` section 7 requires. When a tile is neither cached nor reachable the API
 * answers 404 and maplibre simply draws nothing — which is why the warm grid sits *behind*
 * the map rather than replacing it. Offline is a designed state, not an error.
 *
 * The track never depends on the basemap (ADR-0012). Tiles can all fail and the session
 * still renders over the grid.
 */
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import DeckGL from "@deck.gl/react";
import { useMemo } from "react";
import BaseMap from "react-map-gl/maplibre";
import { rasterStyle } from "@/lib/basemap";
import type { BasemapInfo, SmoothedSample, WaveVerdict } from "@/lib/schema";
import { dashPath, type LngLat, type Span, withRuns } from "@/lib/trace";
import "maplibre-gl/dist/maplibre-gl.css";

/** Design tokens that have to reach a WebGL layer, where CSS cannot go. */
const MEASURED: [number, number, number] = [30, 134, 196]; // --blue-600
const ESTIMATED: [number, number, number] = [62, 107, 124]; // --ink-500, the design's dashed stroke
const WAVE: [number, number, number] = [232, 149, 28]; // --amber-500
const WARM_0: [number, number, number] = [255, 255, 255];
const EXCLUDED: [number, number, number] = [179, 160, 132]; // --warm-400

/** Dash geometry, in metres of travel. Long enough to read, short enough to follow a turn. */
const DASH_M = 6;
const GAP_M = 5;

interface Props {
  samples: SmoothedSample[];
  basemap: BasemapInfo | null;
  apiBase: string;
  now: number;
  waves: WaveVerdict[];
  selected: WaveVerdict | null;
  onSelect: (wave: WaveVerdict | null) => void;
  /** Stretches the audit says were not surfing -- the walk down and the walk back. */
  excluded: Span[];
  height?: number;
}

export function TrackMap({
  samples,
  basemap,
  apiBase,
  now,
  waves,
  selected,
  onSelect,
  excluded,
  height = 470,
}: Props) {
  const { measured, dashes, view, here, waveMarks, notSurfing } = useMemo(() => {
    // The walk down the beach and the walk back are measured perfectly well and are not
    // surfing (ADR-0015). They are *excluded*, never demoted -- so they are still drawn,
    // because the watch really did see them, but never in the colour that means surfing.
    // Leaving them indistinguishable would make the one screen whose job is to keep states
    // apart quietly merge two of them.
    const isExcluded = (t: number) => excluded.some((span) => t >= span.t_start && t < span.t_end);
    // Selecting a wave *hides* the rest, as the design specifies -- the track is filtered to
    // the ride, not merely highlighted, so no off-wave second can be read as part of it.
    const shown = (
      selected === null
        ? samples
        : samples.filter((s) => s.t >= selected.t_start && s.t < selected.t_end)
    ).filter((s) => !isExcluded(s.t));
    const runs = withRuns(shown);
    const byRun = new Map<number, { series: string; path: LngLat[] }>();
    for (const point of runs) {
      const entry = byRun.get(point.run) ?? { series: point.series, path: [] };
      entry.path.push([point.lon, point.lat]);
      byRun.set(point.run, entry);
    }
    const paths = (series: string) =>
      [...byRun.values()].filter((r) => r.series === series && r.path.length > 1);

    const lats = samples.filter((s) => s.observed).map((s) => s.lat);
    const lons = samples.filter((s) => s.observed).map((s) => s.lon);

    const excludedRuns = withRuns(samples.filter((s) => isExcluded(s.t)));
    const excludedByRun = new Map<number, LngLat[]>();
    for (const point of excludedRuns) {
      excludedByRun.set(point.run, [
        ...(excludedByRun.get(point.run) ?? []),
        [point.lon, point.lat],
      ]);
    }

    return {
      notSurfing: [...excludedByRun.values()].filter((p) => p.length > 1),
      measured: paths("measured").filter((r) => r.path.length > 1),
      dashes: paths("estimated").flatMap((r) => dashPath(r.path, DASH_M, GAP_M)),
      here: samples.find((s) => s.t >= now) ?? samples.at(-1) ?? null,
      waveMarks: (selected === null ? waves : [selected])
        .map((wave) => ({
          wave,
          at: samples.find((s) => s.t >= wave.t_start),
        }))
        .filter((m): m is { wave: WaveVerdict; at: SmoothedSample } => m.at !== undefined),
      view: {
        longitude: lons.length ? (Math.min(...lons) + Math.max(...lons)) / 2 : 0,
        latitude: lats.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : 0,
        zoom: 16,
      },
    };
  }, [samples, now, waves, selected, excluded]);

  const layers = [
    new PathLayer({
      id: "not-surfing",
      data: notSurfing,
      getPath: (d: LngLat[]) => d,
      getColor: [...EXCLUDED, 150] as [number, number, number, number],
      getWidth: 1.6,
      widthUnits: "pixels",
      pickable: false,
    }),
    new PathLayer({
      id: "estimated-track",
      data: dashes,
      getPath: (d: LngLat[]) => d,
      getColor: [...ESTIMATED, 110] as [number, number, number, number],
      getWidth: 2,
      widthUnits: "pixels",
      pickable: false,
    }),
    new PathLayer({
      id: "measured-track",
      data: measured,
      getPath: (d: { path: LngLat[] }) => d.path,
      getColor: MEASURED,
      getWidth: 2.4,
      widthUnits: "pixels",
      pickable: false,
    }),
    new ScatterplotLayer({
      id: "wave-marks",
      data: waveMarks,
      getPosition: (d: { at: SmoothedSample }) => [d.at.lon, d.at.lat],
      getRadius: 5,
      radiusUnits: "pixels",
      getFillColor: (d: { wave: WaveVerdict }) =>
        selected !== null && d.wave.t_start === selected.t_start
          ? ([...WAVE, 255] as [number, number, number, number])
          : ([...WAVE, 190] as [number, number, number, number]),
      stroked: true,
      getLineColor: WARM_0,
      lineWidthUnits: "pixels",
      getLineWidth: 1.5,
      pickable: true,
      onClick: (info: { object?: { wave: WaveVerdict } }) => {
        onSelect(info.object?.wave ?? null);
        return true;
      },
    }),
    new ScatterplotLayer({
      id: "playhead",
      data: here ? [here] : [],
      getPosition: (d: SmoothedSample) => [d.lon, d.lat],
      getRadius: 6,
      radiusUnits: "pixels",
      // A playhead on an estimated second is drawn hollow-ish, because "where the surfer is
      // right now" is itself an estimate there and a solid dot would not say so.
      getFillColor: (d: SmoothedSample) =>
        d.observed
          ? ([...MEASURED, 255] as [number, number, number, number])
          : ([...ESTIMATED, 140] as [number, number, number, number]),
      stroked: true,
      getLineColor: WARM_0,
      lineWidthUnits: "pixels",
      getLineWidth: 2,
    }),
  ];

  return (
    <div className="map-body" style={{ height }}>
      {/* The designed fallback, always behind the imagery. When a tile 404s offline,
          maplibre draws nothing and this is what shows through. */}
      <div className="map-grid" aria-hidden="true" />
      <DeckGL initialViewState={view} controller={true} layers={layers}>
        {basemap ? <BaseMap mapStyle={rasterStyle(basemap, apiBase)} /> : null}
      </DeckGL>
    </div>
  );
}
