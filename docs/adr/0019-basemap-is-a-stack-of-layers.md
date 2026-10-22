# ADR-0019: The basemap is a stack of layers, the sea floor underneath

**Status:** accepted · 2026-10-22 · supersedes ADR-0018 **in part** — the proxy-and-cache
decision stands untouched; the single-source choice does not

## Context

ADR-0018 chose satellite imagery because "a street map draws none of what a surf session is".
That reasoning was right and it was also incomplete: a session is a peak, a sandbank and a
stretch of coast, and the thing those sit on is the sea floor. The argument for imagery over
streets is an argument for **bathymetry** at least as strongly, and the product had no way to
show it because the source was three module constants.

A second question arrived with it. A licensing audit found that Esri's keyless endpoints are
the one dependency in the product with a real commercial problem: they are free to call, but
the imagery is sub-licensed from third parties, and ADR-0018's whole design — fetch each tile
once and serve it from our own machine forever — is the pattern those terms restrict. For
personal use nobody cares. For a product with a price on it, it has to change.

## Decision

**A registry of layers, each owning everything that differs between them**, and ticks on the
map to compose them. Bottom to top: **sea floor → imagery → relief.**

- **Sea floor is EMODnet Bathymetry**, which is open data with an attribution condition and
  nothing else — the one layer we may keep without asking anybody.
- **Imagery is still Esri**, and this ADR records plainly that it is the layer with the open
  commercial question. The way out is to render our own tiles from open imagery into the same
  cache layout; a layer declares `source="local"` for exactly that, and a local layer never
  reaches for the network at all. Until then, nothing about the product depends on *which*
  provider the imagery comes from, which is the point of the registry.
- **Relief is Esri hillshade**, at 0.55 strength. A shading layer at full strength replaces
  what it was meant to shade, so its strength is a property of the layer and lives with it.
- **Each layer carries its own URL template, path order, zoom ceiling, media type and
  attribution.** Taking any of those from another layer is a bug that renders: Esri orders
  its path `{z}/{y}/{x}` and EMODnet does not; EMODnet is PNG and Esri is JPEG; EMODnet's
  grid runs out at a zoom where the imagery has four more levels to give.
- **The cache is keyed by layer**, `data/tiles/{layer}/{z}/{x}/{y}.{ext}`. Two sources at one
  z/x/y are the same three integers, and a cache that cannot tell them apart serves the sea
  floor as a beach, silently and forever.
- **Attribution is per layer and follows the ticks.** maplibre credits only the sources a
  visible layer uses, so turning a layer off takes its credit with it and nothing here has to
  manage that.
- **An unknown layer is a 404 before the network**, by the same door as an impossible tile.
  The id indexes a closed registry; it is not a URL a caller supplies.

## What was measured, not assumed

Every zoom ceiling came from the service's own metadata (`?f=json`, and direct tile requests
for EMODnet) on 2026-10-22, not from documentation or memory. Two results changed the design:

**ADR-0018's attribution string had gone stale.** It read `Esri, Maxar, Earthstar
Geographics, and the GIS User Community`; the service now returns `… Vantor …`. Attribution
is a licence condition, and `basemap.py`'s own docstring warned that "an attribution string
duplicated in two repositories is one that goes stale in one of them". It did.

**The sea floor is blank at session zoom, and that is not a bug.** It was drawn on its own
first. A session spans a few hundred metres; EMODnet's grid is about 100 m and its rendering
is a smooth depth ramp, so the entire frame falls inside one shade of grey. It earns its
place when you zoom out to the bay. So it opens **under** the imagery rather than instead of
it, with a strength slider on the imagery for anyone who wants to see the ramp through the
water. A sandbank, meanwhile, is not in any public bathymetry at any resolution — the banks
move faster than anyone surveys them. What shows a bank is imagery of breaking water.

## Consequences

- The map can show the sea floor, which is what a surf session happens on, and can blend the
  imagery over it.
- Swapping a provider is a registry entry rather than a rewrite — which is what makes leaving
  Esri a contained piece of work rather than a reason to delay the control.
- `GET /basemap` returns a list; `GET /basemap/{layer}/{z}/{x}/{y}` serves one layer's tile.
  Both sides of that contract are pinned by `evals/goldens/basemap_contract_v1.json`.
- Tiles cached under the old pathless layout are orphaned. There are 130 of them, 1.6 MB, and
  they re-fetch under the new path; deleting `data/tiles` reclaims them. A migration that
  runs once and is never exercised again is worse than a re-fetch.
- ADR-0012 still holds: the track never depends on the basemap, so none of this can move a
  figure on the screen. That is what makes it a safe change to make now.
