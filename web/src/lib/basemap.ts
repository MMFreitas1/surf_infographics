/**
 * The maplibre style for our own tile route, shared by every map in the product.
 *
 * Built here rather than fetched from a vendor because there is no vendor — the API serves
 * the tiles (ADR-0018) and the style is four lines. One copy, so the two maps cannot drift
 * into crediting the imagery differently.
 *
 * `attribution` is not decoration: the Esri licence requires it, and maplibre renders it
 * from this field, so the credit appears exactly when imagery does and vanishes with it
 * offline.
 */
import type { BasemapInfo } from "./schema";

export function rasterStyle(basemap: BasemapInfo, apiBase: string) {
  return {
    version: 8 as const,
    sources: {
      satellite: {
        type: "raster" as const,
        tiles: [`${apiBase}${basemap.tile_url}`],
        tileSize: 256,
        minzoom: basemap.min_zoom,
        maxzoom: basemap.max_zoom,
        attribution: basemap.attribution,
      },
    },
    layers: [{ id: "satellite", type: "raster" as const, source: "satellite" }],
  };
}
