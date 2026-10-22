# ADR-0021: The imagery layer is DGT's OrtoSat 2023, and the licence is why

**Status:** accepted · 2026-10-22 · supersedes the imagery row of
[ADR-0019](0019-basemap-is-a-stack-of-layers.md), and **retires its premise** that leaving
Esri means rendering our own pyramid

## Context

ADR-0019 recorded imagery as the one layer in the product with a real commercial licensing
problem: Esri's endpoints are free to call, the imagery is sub-licensed from third parties,
and ADR-0018's whole design — fetch each tile once and serve it from our own machine forever
— is the pattern those terms restrict. The route out it wrote down was to **render our own
tiles** from open imagery, with a `source="local"` mode waiting for the pyramid.

That premise was never tested. Before cutting a pyramid, the alternatives were put side by
side on the reference session's own frame — 675 m across, the same 1,849 positioned points
drawn on each.

## The comparison

| Source | Ground resolution | Licence | What it shows at session zoom |
|---|---|---|---|
| **DGT OrtoSat 2023** | ~50 cm | **CC BY 4.0** | waves breaking around the point, the reef shelf through the water, the sandbank |
| DGT Ortos 2018 (aerial) | 25 cm | CC BY 4.0 | sharpest of all — individual cars — but shot on a flat day, water almost black |
| Esri World Imagery | sub-metre | **not licensed for resale** | comparable; nothing the DGT layers do not give |
| Sentinel-2 cloudless | 10 m | CC BY-NC-SA (2018+) | unusable: a 675 m frame is about 67 pixels across |
| EOX commercial licence | 10 m | paid, and **forbids re-serving under our own name** | which is exactly what `/basemap/{layer}/{z}/{x}/{y}` does |

## Decision

**Imagery is DGT's OrtoSat 2023, served by their WMS, proxied and cached exactly as before.**

- **The pyramid is not needed, and that is the substantive finding.** Rendering our own was
  never the goal; it was the escape from terms that forbid caching. CC BY 4.0 does not forbid
  it. So **ADR-0018's proxy-and-cache design stands untouched**, `source="local"` stays
  available as an optimisation rather than a prerequisite, and the work this ADR replaces is
  the pyramid PR in its entirety.
- **The open layer is also the better one.** OrtoSat 2023 is the most recent capture of the
  five and the only one that happens to show swell: the comparison was run expecting a
  quality sacrifice for the licence and found none to make.
- **A WMS answers a bounding box, not a tile index.** `_mercator_bbox` turns z/x/y into one
  and the layer's template spells `{bbox}` where another spells `{z}/{x}/{y}`. That is the
  only mechanical difference, and it lives in the layer, which is what ADR-0019's registry
  was for. WMS **1.1.1**, not the 1.3.0 the service also advertises: 1.3.0 reverses the axis
  order of geographic CRSs, and the version that does not is one fewer way to draw the right
  tile of the wrong hemisphere.
- **Attribution is `Ortos Satélite 2023, Direção-Geral do Território (CC BY 4.0)`.** The
  service's own capabilities declare `Fees: no conditions apply` and `AccessConstraints:
  None`, but the binding grant is the dataset's CC BY 4.0 on dados.gov.pt, and attribution is
  its one condition.
- **A role is not a provider.** `id` stays `imagery` — the contract, the ticks and the
  opacity slider all name it — and the tiles now live under `cache_id="imagery-ortosat2023"`.
  Keyed on the role alone, the previous provider's tiles would be served as this one's: a
  different picture of the same three integers, with nothing on screen to say so. ADR-0019's
  lesson, one level down.

## What was measured, not assumed

**The zoom ceiling is 18, and it was measured on 2026-10-22.** The service declares a 1:500
scale limit — about z20 — but that is a *rendering* limit, not a resolution claim. Asked for
one fixed 128 m square at rising pixel densities, the returned JPEG stops gaining information
below about 50 cm/px:

| requested | 100 cm/px | 50 cm/px | 25 cm/px | 12.5 cm/px | 6.2 cm/px |
|---|---|---|---|---|---|
| bytes per pixel | 0.339 | 0.291 | 0.217 | 0.166 | 0.124 |

At this latitude z18 is 0.47 m of ground per pixel, which is where the source saturates. Past
18 maplibre overzooms our last tile and it looks soft — honest — where letting the server
interpolate to z20 would look sharp and claim detail the imagery does not hold.

**Coverage is declared, because the service does not refuse.** Asked for Hossegor, or for
open ocean, DGT answers **200 with a valid, uniform 667-byte JPEG**. Fetched once and kept,
that is a white square served forever, indistinguishable on screen from a very pale sea. So
the layer carries the `EX_GeographicBoundingBox` from its own capabilities — continental
Portugal, and not the Azores or Madeira — and a tile outside it is refused by the same door
as an impossible one, before the network and before the disk.

## Consequences

- **Imagery is Portugal-only.** A session surfed anywhere else now renders with the sea floor
  and the track and no imagery, which is a designed state (ADR-0012: the track never depends
  on the basemap) rather than a blank. France's BD ORTHO (Licence Ouverte 2.0, ~20 cm) and
  Spain's PNOA (CC BY 4.0) are the same shape of layer under the same shape of licence, so
  extending coverage is a registry entry — which is what ADR-0019 bought.
- **`bounds` is enforced server-side only.** maplibre would stop asking altogether if the
  `/basemap` contract carried it; today it asks and is refused. A cheap follow-up, and not
  one that changes what is drawn.
- **Relief is still Esri, and this ADR does not fix it.** The hillshade is off by default and
  draws no part of a surf session, but it is the same licence question in a smaller box, and
  pretending otherwise would make this ADR read better than the truth. Recorded as open.
- **Tiles cached under the previous provider are orphaned by construction**, not by a
  migration. They re-fetch under the new directory; deleting `data/tiles/imagery` reclaims
  them.
- **The $0 stack rule holds**, and now holds for a product with a price on it rather than
  only for personal use — which was the whole point of the audit that started this.
