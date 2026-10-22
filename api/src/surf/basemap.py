"""Basemap tiles, fetched once and kept on disk.

**Why this is a server concern at all.** `architecture.md` section 7 requires the app to
work with no network, and a basemap that reaches the internet on every pan does not. So the
browser asks *this* process for a tile, and this process answers from disk — fetching from
upstream only the first time it sees one. A session covers a few hundred metres of coast, so
the whole surface is a handful of tiles and caching it is trivially correct.

**Why these layers.** A surf session is coastline, sandbanks and a peak, none of which a
street map draws (ADR-0018). Bathymetry answers that at least as well as imagery does, so the
default is the sea floor and the imagery sits on a tick above it (ADR-0019).

**Ocean comes from EMODnet** rather than a vendor basemap because it is open data with an
attribution condition and nothing else — the one layer we may keep without asking anybody.
**Imagery is still Esri**, which is keyless but not clearly licensed for a commercial product
that caches tiles the way this module does. ADR-0019 records that and the route out.

**Each layer owns its own everything** — URL template, path order, zoom range, media type and
attribution — because getting one of those from another layer is a bug that renders. Esri's
imagery orders its path ``{z}/{y}/{x}``, not ``{z}/{x}/{y}``: getting that backwards yields a
perfectly valid tile of the wrong piece of the planet, which is the kind of bug that looks
like a projection error for an afternoon.

**Nothing here sees a session.** A tile is addressed by layer and z/x/y, so this module never
learns which coordinates the user asked about beyond the tile itself, and no activity id
passes through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import httpx

SourceMode = Literal["upstream", "local"]
"""Where a layer's tiles come from.

``upstream`` fetches once and caches, as every layer does today. ``local`` has no upstream at
all: the pyramid was rendered ahead of time into the cache directory, and a miss is simply a
miss. It exists because rendering our own imagery is the way off the one licensing question
in the product, and a layer that flips to it should not need this module to change.
"""


@dataclass(frozen=True)
class Layer:
    """One basemap, and everything about it that differs from the others."""

    id: str
    url: str
    """Template over ``{z}``, ``{x}`` and ``{y}``. Empty when ``source`` is ``local``."""
    attribution: str
    """Required by the licence and rendered in the map's corner. Not optional, never empty."""
    min_zoom: int
    max_zoom: int
    """The service's real ceiling, read from its own metadata. Past it maplibre overzooms the
    last tile, which is honest — a stretched tile looks soft rather than claiming detail it
    does not have. Getting it *wrong* is what breaks: the map asks for tiles that cannot
    exist and draws nothing at all."""
    media_type: str
    extension: str
    source: SourceMode = "upstream"
    opacity: float = 1.0
    """How strongly the layer draws when it is on.

    A hillshade is a *shading* layer: at full strength it replaces what it was meant to
    shade. That is a property of the layer rather than a preference of the screen, so it
    lives here with the rest of the facts about it."""


LAYERS: Final[dict[str, Layer]] = {
    "ocean": Layer(
        id="ocean",
        url="https://tiles.emodnet-bathymetry.eu/2020/baselayer/web_mercator/{z}/{x}/{y}.png",
        attribution="EMODnet Bathymetry Consortium",
        min_zoom=0,
        # EMODnet renders at any zoom asked of it, and its *rendering* is worth having well
        # past the point its *data* saturates: the grid is about 100 m, fully resolved by
        # z11, but the service draws a styled depth ramp and a coastline that stay legible
        # much deeper. Capping at 11 and letting maplibre stretch that tile was tried first
        # and produced a featureless grey smear at session zoom -- 16 is where it stops
        # being worth the tiles. Either way a sandbank moves faster than anyone surveys it:
        # this layer reads the bay, the channel and the depth gradient, never the bank.
        max_zoom=16,
        media_type="image/png",
        extension="png",
    ),
    "imagery": Layer(
        id="imagery",
        url=(
            "https://server.arcgisonline.com/ArcGIS/rest/services"
            "/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attribution="Esri, Vantor, Earthstar Geographics, and the GIS User Community",
        min_zoom=0,
        max_zoom=19,
        media_type="image/jpeg",
        extension="jpg",
    ),
    "relief": Layer(
        id="relief",
        url=(
            "https://server.arcgisonline.com/ArcGIS/rest/services"
            "/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}"
        ),
        attribution="Esri, Vantor, Airbus DS, USGS, NGA, NASA, CGIAR, NCEAS, NLS, OS, NMA",
        min_zoom=0,
        max_zoom=19,
        media_type="image/jpeg",
        extension="jpg",
        opacity=0.55,
    ),
}

DEFAULT_LAYERS: Final[frozenset[str]] = frozenset({"ocean", "imagery"})
"""Ticked on when the map opens.

The sea floor is the base and the thing a surf session actually happens on -- but it was
drawn on its own first and **it is blank at session zoom**. A session spans a few hundred
metres; EMODnet's grid is about 100 m and its rendering is a smooth depth ramp, so the whole
frame falls inside one shade of grey. It earns its place when you zoom out to the bay, and it
is under the imagery the rest of the time rather than instead of it.

So both open ticked: the sea floor at the bottom, the imagery over it, and the strength
slider between them for anyone who wants to see the ramp through the water."""

_CACHE_CONTROL = "public, max-age=31536000, immutable"
"""Imagery and bathymetry for a past session do not change. Once a browser has a tile it
should never ask again -- the disk cache below is for the first visit and for other
browsers."""


class TileError(RuntimeError):
    """A tile could not be produced, and is not on disk to fall back to."""


@dataclass(frozen=True)
class Tile:
    """One tile, and whether it came from disk.

    ``cached`` exists so "the map works offline after the first visit" is observable in the
    log rather than asserted in a doc.
    """

    data: bytes
    cached: bool


def _valid(layer: Layer, z: int, x: int, y: int) -> bool:
    """Whether z/x/y names a tile that can exist in this layer.

    At zoom z the world is a 2^z grid, so an index outside it is not a missing tile but a
    nonsensical one. Checked before touching the disk, because the path is built from these
    numbers and an unchecked index is how a path escapes its directory.
    """
    if not layer.min_zoom <= z <= layer.max_zoom:
        return False
    limit = 1 << z
    return 0 <= x < limit and 0 <= y < limit


class TileCache:
    """Tiles on disk, keyed by layer and z/x/y, fetched from upstream at most once each."""

    def __init__(self, root: Path, *, timeout_s: float = 10.0) -> None:
        self.root = root
        self.timeout_s = timeout_s

    def path_for(self, layer: Layer, z: int, x: int, y: int) -> Path:
        """Where a tile lives.

        The layer is part of the path, so two sources cannot collide at one z/x/y -- which
        would otherwise serve a bathymetry tile as imagery, silently and forever. The id
        comes from :data:`LAYERS` and the rest are integers, so a caller cannot steer it.
        """
        return self.root / layer.id / str(z) / str(x) / f"{y}.{layer.extension}"

    def cached(self, layer: Layer, z: int, x: int, y: int) -> bytes | None:
        path = self.path_for(layer, z, x, y)
        return path.read_bytes() if path.is_file() else None

    def get(self, layer: Layer, z: int, x: int, y: int) -> Tile:
        """A tile from disk, or from upstream and then disk.

        Raises :class:`TileError` when it is neither cached nor reachable. That is the
        offline case and it is not an error state in the product: the UI draws the
        designed warm-grid fallback, which is a *state*, not a failure message.
        """
        if not _valid(layer, z, x, y):
            msg = f"no such tile: layer={layer.id} z={z} x={x} y={y}"
            raise TileError(msg)

        if (hit := self.cached(layer, z, x, y)) is not None:
            return Tile(data=hit, cached=True)

        if layer.source == "local":
            # Pre-rendered, so a miss is the whole answer. Asking the network here would
            # quietly reintroduce the dependency the layer exists to be free of.
            msg = f"layer {layer.id} is pre-rendered and has no tile z={z} x={x} y={y}"
            raise TileError(msg)

        try:
            response = httpx.get(
                layer.url.format(z=z, x=x, y=y),
                timeout=self.timeout_s,
                follow_redirects=True,
                headers={"User-Agent": "surf-infographics/0.1 (local-first, personal use)"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = (
                f"tile layer={layer.id} z={z} x={x} y={y} is not cached "
                f"and upstream is unreachable: {exc}"
            )
            raise TileError(msg) from exc

        data = response.content
        if not data:
            msg = f"upstream returned an empty tile for layer={layer.id} z={z} x={x} y={y}"
            raise TileError(msg)

        self._store(layer, z, x, y, data)
        return Tile(data=data, cached=False)

    def _store(self, layer: Layer, z: int, x: int, y: int, data: bytes) -> None:
        """Write a tile, atomically.

        Via a temporary file in the same directory and a rename, so a process killed
        mid-write leaves no half tile behind. A truncated JPEG on disk would be served
        forever after, and would look like a rendering bug rather than a storage one.
        """
        path = self.path_for(layer, z, x, y)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{id(data):x}.part")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def count(self) -> int:
        """How many tiles are on disk, across every layer. For diagnostics, and for tests.

        Counts files rather than one extension: the layers do not agree on a format, and a
        counter that only sees JPEG would report the ocean layer as empty.
        """
        if not self.root.is_dir():
            return 0
        return sum(1 for path in self.root.rglob("*") if path.is_file())


def cache_headers() -> dict[str, str]:
    """Headers every tile response carries."""
    return {"Cache-Control": _CACHE_CONTROL}
