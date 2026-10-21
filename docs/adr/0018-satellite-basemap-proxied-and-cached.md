# ADR-0018: The basemap is satellite imagery, proxied and cached by this API

**Status:** accepted · 2026-09-30 · supersedes the MapTiler row in `architecture.md` §6

## Context

`architecture.md` §6 named MapTiler street tiles, fetched by the browser, degrading to a bare
track with no key. That predates the design handover. Two things have changed since.

**A street map draws none of what a surf session is.** The session is a peak, a sandbank and
a stretch of coast; street tiles render a road and a blank blue rectangle where the surfing
happened. Decided with Miguel on 2026-09-15 and recorded in PLAN.md under "Decisions taken on
the handover", which this ADR is the implementation of rather than a new choice.

**A browser fetching tiles directly cannot satisfy §7.** The app must work with no network.
Tiles fetched from a vendor per pan are a network dependency on every visit, and the "degrades
to a bare track" escape hatch means a real session opens with no coast on it — which is the
one thing the map exists to show.

## Decision

**Esri World Imagery, requested from this API, cached to disk on first fetch.**

- **Keyless**, so the $0 stack rule holds with no account and no secret to manage.
- **Attribution is required** by the imagery licence. `GET /basemap` serves it alongside the
  tile URL so the credit travels with the thing that serves the tiles, and maplibre renders
  it from the source definition — appearing exactly when imagery does.
- **`GET /basemap/{z}/{x}/{y}`** answers from `data/tiles`, fetching upstream at most once
  per tile. A session covers a few hundred metres of coast, so the whole surface is a handful
  of tiles and bounding it is trivial.
- **A tile that is neither cached nor reachable is a 404, not a 500.** Offline is a designed
  state: the UI draws the warm grid beneath the map and the track renders over it. Nothing
  failed; there was simply no network, which this app is required to survive.

## Consequences

- **The track still never depends on the basemap** (ADR-0012). Every tile can fail and the
  session still draws. The warm grid sits *behind* the map rather than replacing it, so the
  fallback needs no error path to trigger it.
- **`data/tiles` is gitignored**, and this matters more than it looks. A cached tile
  directory is a list of the coordinates someone surfed at; this repo is public and that is
  exactly the data `.gitignore` exists to keep out of it.
- **The tile route never learns an activity id.** A tile is addressed by z/x/y and nothing
  else, which is what stops a basemap request from being a location lookup with extra steps.
- **Esri's path order is `{z}/{y}/{x}`**, not `{z}/{x}/{y}`. Swapping them returns a valid
  tile of the wrong piece of the planet, which renders as a plausible coastline somewhere
  else entirely. There is a test for it by name.
- **MapTiler is dropped everywhere**, along with `NEXT_PUBLIC_MAPTILER_KEY` in
  `.env.example` and `docker-compose.yml`. Nothing in the product needs a key now.
- **The labeling UI moved to the same tiles.** It had its own MapTiler basemap behind that
  key, which would have left two basemap systems, two credits and one stale config knob.
  Both maps now build their style from one helper, so they cannot drift into crediting the
  imagery differently. Its "no basemap — track only" state stays: that map has never
  depended on one (ADR-0012) and still does not.
