"use client";

import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import DeckGL from "@deck.gl/react";
import { useMemo, useState } from "react";
import BaseMap from "react-map-gl/maplibre";
import type { SessionFrame, SmoothedSample } from "@/lib/schema";
import { withRuns } from "@/lib/trace";
import "maplibre-gl/dist/maplibre-gl.css";

interface Props {
  samples: SmoothedSample[];
  frame: SessionFrame;
  now: number;
  height?: number;
}

const MAPTILER_KEY = process.env.NEXT_PUBLIC_MAPTILER_KEY ?? "";

/** Every fifth blind second. Drawing 1900 discs says nothing 380 does not. */
const SIGMA_STRIDE = 5;

/**
 * The session on a map, with its uncertainty drawn in the units uncertainty comes in.
 *
 * `position_sigma_m` is metres, and on a map metres are a radius — so each estimated second
 * gets a disc the size of what we do not know about it. That is the one place in this UI
 * where the honest rendering is also the obvious one: a stretch of fat translucent circles
 * is a stretch nobody should be marking a wave inside of without thinking twice.
 *
 * The basemap is optional by design. `docs/architecture.md` §7 requires the app to work with
 * no network, so a missing key or a failed tile load leaves the track drawn on a plain
 * ground and says so, rather than leaving the labeller staring at an empty panel.
 */
export function TrackMap({ samples, frame, now, height = 260 }: Props) {
  const [basemapFailed, setBasemapFailed] = useState(false);
  const wantsBasemap = MAPTILER_KEY !== "" && !basemapFailed;

  const { measured, estimated, sigma, here, view } = useMemo(() => {
    const runs = withRuns(samples);
    const paths = (series: "measured" | "estimated") => {
      const byRun = new Map<number, [number, number][]>();
      for (const point of runs) {
        if (point.series !== series) continue;
        const path = byRun.get(point.run) ?? [];
        path.push([point.lon, point.lat]);
        byRun.set(point.run, path);
      }
      return [...byRun.values()].filter((path) => path.length > 1).map((path) => ({ path }));
    };

    const lats = samples.map((s) => s.lat);
    const lons = samples.map((s) => s.lon);
    const current =
      samples.reduce<SmoothedSample | null>(
        (best, s) => (best === null || Math.abs(s.t - now) < Math.abs(best.t - now) ? s : best),
        null,
      ) ?? samples[0];

    return {
      measured: paths("measured"),
      estimated: paths("estimated"),
      sigma: samples.filter((s, i) => !s.observed && i % SIGMA_STRIDE === 0),
      here: current,
      view: {
        longitude: lons.length ? (Math.min(...lons) + Math.max(...lons)) / 2 : frame.origin_lon,
        latitude: lats.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : frame.origin_lat,
        zoom: 15,
      },
    };
  }, [samples, frame, now]);

  const layers = [
    new ScatterplotLayer({
      id: "position-uncertainty",
      data: sigma,
      getPosition: (d: SmoothedSample) => [d.lon, d.lat],
      getRadius: (d: SmoothedSample) => d.position_sigma_m,
      radiusUnits: "meters",
      getFillColor: [120, 120, 140, 28],
      pickable: false,
    }),
    new PathLayer({
      id: "estimated-track",
      data: estimated,
      getPath: (d: { path: [number, number][] }) => d.path,
      getColor: [150, 150, 165, 170],
      getWidth: 2,
      widthUnits: "pixels",
    }),
    new PathLayer({
      id: "measured-track",
      data: measured,
      getPath: (d: { path: [number, number][] }) => d.path,
      getColor: [15, 118, 178],
      getWidth: 3,
      widthUnits: "pixels",
    }),
    new ScatterplotLayer({
      id: "playhead",
      data: here ? [here] : [],
      getPosition: (d: SmoothedSample) => [d.lon, d.lat],
      getRadius: 5,
      radiusUnits: "pixels",
      getFillColor: (d: SmoothedSample) => (d.observed ? [220, 80, 40] : [220, 80, 40, 120]),
      stroked: true,
      getLineColor: [255, 255, 255],
      lineWidthUnits: "pixels",
      getLineWidth: 1.5,
    }),
  ];

  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Track</h2>
        <p className="caveat">
          {here?.observed === false ? "playhead is on an estimated second · " : ""}
          {wantsBasemap ? null : "no basemap (offline or no key) — track only"}
        </p>
      </header>
      <div className="map-host" style={{ height }}>
        <DeckGL initialViewState={view} controller={true} layers={layers}>
          {wantsBasemap ? (
            <BaseMap
              mapStyle={`https://api.maptiler.com/maps/streets-v2/style.json?key=${MAPTILER_KEY}`}
              onError={() => setBasemapFailed(true)}
            />
          ) : null}
        </DeckGL>
      </div>
      <p className="legend">
        <span className="key key-measured" /> measured
        <span className="key key-estimated" /> estimated
        <span className="key key-unknown" /> ±1σ position uncertainty, to scale
      </p>
    </section>
  );
}

export default TrackMap;
