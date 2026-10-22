import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { defaultView, rasterStyle } from "@/lib/basemap";
import { BasemapInfo, BasemapLayer } from "@/lib/schema";

/**
 * The other half of the basemap contract — `api/tests/test_contract_parity.py` holds the
 * same fixture to the Pydantic models — plus the style builder, which is pure and so can be
 * asserted rather than looked at.
 */
const fixturePath = new URL("../../evals/goldens/basemap_contract_v1.json", import.meta.url)
  .pathname;
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));

const basemap = BasemapInfo.parse(fixture.basemap);
const API = "http://127.0.0.1:8000";

describe("the basemap contract", () => {
  it("parses as BasemapInfo", () => {
    expect(basemap.layers).toHaveLength(3);
  });

  it("carries exactly the fields the schema declares", () => {
    for (const layer of fixture.basemap.layers) {
      expect(Object.keys(layer).sort()).toEqual(Object.keys(BasemapLayer.shape).sort());
    }
  });

  it("opens with the sea floor under the imagery", () => {
    // The sea floor on its own is blank at session zoom -- a few hundred metres inside one
    // shade of EMODnet's ramp. It is the base, not the picture.
    expect(defaultView(basemap).shown).toEqual(["ocean", "imagery"]);
  });

  it("credits every layer, because that is a licence condition and not a label", () => {
    for (const layer of basemap.layers) {
      expect(layer.attribution.length).toBeGreaterThan(0);
    }
  });
});

describe("the style it builds", () => {
  it("puts every layer in the style and draws only the ticked ones", () => {
    const style = rasterStyle(basemap, API, { shown: ["ocean", "imagery"] });
    const visibility = Object.fromEntries(
      style.layers.map((layer) => [layer.id, layer.layout.visibility]),
    );

    expect(Object.keys(style.sources)).toEqual(["ocean", "imagery", "relief"]);
    expect(visibility).toEqual({ ocean: "visible", imagery: "visible", relief: "none" });
  });

  it("keeps the stack order of the registry, not of the tick list", () => {
    const style = rasterStyle(basemap, API, { shown: ["relief", "ocean"] });

    expect(style.layers.map((layer) => layer.id)).toEqual(["ocean", "imagery", "relief"]);
  });

  it("takes each ceiling from its own source", () => {
    const style = rasterStyle(basemap, API);
    const ceiling = (id: string) => style.sources[id]?.maxzoom;

    // EMODnet stops being worth the tiles at z16; the imagery goes to 19. One ceiling for
    // both would either blur the imagery or over-fetch the sea floor.
    expect(ceiling("ocean")).toBe(16);
    expect(ceiling("imagery")).toBe(19);
  });

  it("points at our own origin, never at the source", () => {
    const style = rasterStyle(basemap, API);

    for (const source of Object.values(style.sources)) {
      expect(source.tiles[0]?.startsWith(`${API}/basemap/`)).toBe(true);
    }
  });

  it("carries each source's own attribution, so the credit follows the ticks", () => {
    const style = rasterStyle(basemap, API);
    const credit = (id: string) => style.sources[id]?.attribution;

    expect(credit("ocean")).toContain("EMODnet");
    expect(credit("imagery")).toContain("Esri");
  });

  it("falls back to the layer's own strength, and lets the view override it", () => {
    const plain = rasterStyle(basemap, API, { shown: ["ocean", "imagery", "relief"] });
    const opacity = (style: typeof plain, id: string) =>
      style.layers.find((layer) => layer.id === id)?.paint["raster-opacity"];

    // Relief is a shading layer: at full strength it replaces what it was meant to shade.
    expect(opacity(plain, "relief")).toBe(0.55);
    expect(opacity(plain, "imagery")).toBe(1);

    const blended = rasterStyle(basemap, API, {
      shown: ["ocean", "imagery"],
      opacity: { imagery: 0.6 },
    });
    expect(opacity(blended, "imagery")).toBe(0.6);
  });

  it("draws the default layers when nothing has been ticked yet", () => {
    const style = rasterStyle(basemap, API);
    const visible = style.layers.filter((layer) => layer.layout.visibility === "visible");

    expect(visible.map((layer) => layer.id)).toEqual(["ocean", "imagery"]);
  });
});
