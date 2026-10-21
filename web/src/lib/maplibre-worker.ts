"use client";

/**
 * Tell maplibre where its worker is, because it cannot work that out for itself here.
 *
 * Left alone, maplibre derives the worker's URL from its own `import.meta.url`. Turbopack
 * bundles the library into a hashed chunk, so that resolves to a `/_next/static/chunks/`
 * sibling which was never emitted: the worker fails to load on every map. The style is
 * raster-only, so the map still draws -- which is exactly why this is worth naming rather
 * than living with. A console error nobody can act on trains you to ignore the next one,
 * and `pnpm run verify` fails the whole suite on any error at all, by design.
 *
 * `scripts/copy-maplibre-worker.mjs` puts the file (and the chunk it imports) under
 * `public/` before dev, build and test, so this URL is same-origin and maplibre loads it
 * as a module worker rather than fetching it into a blob.
 */
import { setWorkerUrl } from "maplibre-gl";

/** Must match what `scripts/copy-maplibre-worker.mjs` writes. Asserted by `tests/maplibre-worker.test.ts`. */
export const WORKER_URL = "/maplibre/maplibre-gl-worker.mjs";

setWorkerUrl(WORKER_URL);
