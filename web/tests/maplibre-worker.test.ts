import { readdirSync, readFileSync } from "node:fs";
import { getWorkerUrl } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import { WORKER_URL } from "@/lib/maplibre-worker";

/**
 * The failure this guards is silent in CI and loud in a browser: maplibre resolves its
 * worker against its own bundled chunk, finds nothing, and logs `Worker failed to load`
 * on every map. `pnpm run pretest` copies the worker into `public/`, so these run against
 * the same files the dev server and the build serve.
 */
const PUBLIC = new URL("../public/maplibre/", import.meta.url);

describe("the maplibre worker", () => {
  it("is where the client says it is", () => {
    const name = WORKER_URL.split("/").pop();
    expect(readdirSync(PUBLIC)).toContain(name);
  });

  it("brings the chunk it imports with it", () => {
    const worker = readFileSync(new URL("maplibre-gl-worker.mjs", PUBLIC), "utf8");
    const siblings = [...worker.matchAll(/from"\.\/([^"]+)"/g)].map((m) => m[1]);
    const copied = readdirSync(PUBLIC);
    expect(siblings.length).toBeGreaterThan(0);
    for (const sibling of siblings) {
      expect(copied).toContain(sibling);
    }
  });

  it("is the url maplibre will actually ask for", () => {
    expect(getWorkerUrl()).toBe(WORKER_URL);
  });

  it("is served from our own origin, so the worker stays a module", () => {
    expect(WORKER_URL.startsWith("/")).toBe(true);
  });
});
