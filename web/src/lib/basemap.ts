/**
 * The maplibre style for our own tile routes, shared by every map in the product.
 *
 * Built here rather than fetched from a vendor because there is no vendor — the API serves
 * the tiles (ADR-0018, ADR-0019) and the style is a loop. One copy, so the two maps cannot
 * drift into crediting the sea floor differently.
 *
 * **Every layer is always in the style; ticks change `visibility`.** maplibre diffs a style
 * it is handed, so flipping visibility is a targeted update rather than a rebuild, and the
 * tiles already in the GL context survive being toggled off and on again.
 *
 * `attribution` is not decoration: the licences require it, and maplibre renders it from the
 * source's own field — and only for sources a *visible* layer uses, so the credit follows
 * the ticks without anything here having to manage it.
 */
import type { BasemapInfo } from "./schema";

export interface LayerView {
  /** Layer ids currently drawn. Order is the style's, not this list's. */
  shown: readonly string[];
  /** Opacity per layer id, 0–1. Absent means fully opaque. */
  opacity?: Readonly<Record<string, number>>;
}

/** What the map shows when nobody has ticked anything: whichever layer the API defaults to. */
export function defaultView(basemap: BasemapInfo): LayerView {
  return { shown: basemap.layers.filter((layer) => layer.default).map((layer) => layer.id) };
}

export function rasterStyle(basemap: BasemapInfo, apiBase: string, view?: LayerView) {
  const on = new Set(view ? view.shown : defaultView(basemap).shown);
  return {
    version: 8 as const,
    sources: Object.fromEntries(
      basemap.layers.map((layer) => [
        layer.id,
        {
          type: "raster" as const,
          tiles: [`${apiBase}${layer.tile_url}`],
          tileSize: 256,
          minzoom: layer.min_zoom,
          // Past a source's own ceiling maplibre stretches its last tile, which looks soft
          // rather than claiming detail the data does not have. EMODnet's grid runs out
          // long before the imagery's does, so this is per layer or the map asks for tiles
          // that were never rendered and draws nothing at all.
          maxzoom: layer.max_zoom,
          attribution: layer.attribution,
        },
      ]),
    ),
    layers: basemap.layers.map((layer) => ({
      id: layer.id,
      type: "raster" as const,
      source: layer.id,
      layout: { visibility: on.has(layer.id) ? ("visible" as const) : ("none" as const) },
      paint: { "raster-opacity": view?.opacity?.[layer.id] ?? layer.opacity },
    })),
  };
}
