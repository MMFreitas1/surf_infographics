/**
 * Copy maplibre's worker bundle into `public/`, so the browser can load it from our origin.
 *
 * maplibre 6.11 ships the worker as a module that imports a sibling chunk, and finds itself
 * at runtime from `import.meta.url`. Under Turbopack that is the hashed chunk the library
 * was bundled into, so the worker resolves to a `/_next/static/chunks/` path that does not
 * exist and every map logs `Worker failed to load`. Serving the two files ourselves and
 * naming them through `setWorkerUrl` is the fix maplibre documents for bundlers.
 *
 * Copied rather than committed: taking them from `node_modules` at `predev`/`prebuild`/
 * `pretest` means the worker can never be a different version from the library that talks
 * to it, which a vendored copy would eventually become.
 */

import { copyFile, mkdir, readdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

/** The worker and the chunk it imports. Both, or the module worker fails on its first import. */
const FILES = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/dist/maplibre-gl.mjs"));
const out = join(import.meta.dirname, "..", "public", "maplibre");

const shipped = await readdir(dist);
const missing = FILES.filter((file) => !shipped.includes(file));
if (missing.length > 0) {
  // A maplibre upgrade renamed or split the worker. Failing here is the point: the
  // alternative is a dev server that starts and a map that logs an error in the browser.
  throw new Error(`maplibre no longer ships ${missing.join(", ")} — check its dist layout`);
}

await mkdir(out, { recursive: true });
await Promise.all(FILES.map((file) => copyFile(join(dist, file), join(out, file))));
