"""Satellite basemap tiles, fetched once and kept on disk.

**Why this is a server concern at all.** `architecture.md` section 7 requires the app to
work with no network, and a basemap that reaches the internet on every pan does not. So the
browser asks *this* process for a tile, and this process answers from disk — fetching from
upstream only the first time it sees one. A session covers a few hundred metres of coast, so
the whole surface is a handful of tiles and caching it is trivially correct.

**Why satellite rather than street.** A surf session is coastline, sandbanks and a peak, none
of which a street map draws. Decided with Miguel on 2026-09-15 and recorded in PLAN.md;
`architecture.md` section 6 named MapTiler before that and is corrected in this change.

**Esri World Imagery** is keyless and free, which satisfies the $0 stack rule — and requires
attribution, which :data:`ATTRIBUTION` carries to the map's corner. Note its URL template
orders the path ``{z}/{y}/{x}``, not ``{z}/{x}/{y}``: getting that backwards yields a
perfectly valid tile of the wrong piece of the planet, which is the kind of bug that looks
like a projection error for an afternoon.

**Nothing here sees a session.** A tile is addressed by z/x/y, so this module never learns
which coordinates the user asked about beyond the tile itself, and no activity id passes
through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

UPSTREAM = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
"""Esri World Imagery. Path order is z/y/x -- deliberately spelled out, see the module note."""

ATTRIBUTION = "Esri, Maxar, Earthstar Geographics, and the GIS User Community"
"""Required by the imagery licence and rendered in the map's corner. Not optional."""

MIN_ZOOM = 10
MAX_ZOOM = 19
"""A session is a few hundred metres of coast. Below 10 the tile shows a country and above
19 Esri has no imagery, so anything outside this range is a bug in the caller rather than a
request worth forwarding."""

MEDIA_TYPE = "image/jpeg"

_CACHE_CONTROL = "public, max-age=31536000, immutable"
"""Satellite imagery for a past session does not change. Once a browser has a tile it should
never ask again -- the disk cache below is for the first visit and for other browsers."""


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


def _valid(z: int, x: int, y: int) -> bool:
    """Whether z/x/y names a tile that can exist.

    At zoom z the world is a 2^z grid, so an index outside it is not a missing tile but a
    nonsensical one. Checked before touching the disk, because the path is built from these
    numbers and an unchecked index is how a path escapes its directory.
    """
    if not MIN_ZOOM <= z <= MAX_ZOOM:
        return False
    limit = 1 << z
    return 0 <= x < limit and 0 <= y < limit


class TileCache:
    """Tiles on disk, keyed by z/x/y, fetched from upstream at most once each."""

    def __init__(self, root: Path, *, timeout_s: float = 10.0) -> None:
        self.root = root
        self.timeout_s = timeout_s

    def path_for(self, z: int, x: int, y: int) -> Path:
        """Where a tile lives. Integers only, so the path cannot be steered by a caller."""
        return self.root / str(z) / str(x) / f"{y}.jpg"

    def cached(self, z: int, x: int, y: int) -> bytes | None:
        path = self.path_for(z, x, y)
        return path.read_bytes() if path.is_file() else None

    def get(self, z: int, x: int, y: int) -> Tile:
        """A tile from disk, or from upstream and then disk.

        Raises :class:`TileError` when it is neither cached nor reachable. That is the
        offline case and it is not an error state in the product: the UI draws the
        designed warm-grid fallback, which is a *state*, not a failure message.
        """
        if not _valid(z, x, y):
            msg = f"no such tile: z={z} x={x} y={y}"
            raise TileError(msg)

        if (hit := self.cached(z, x, y)) is not None:
            return Tile(data=hit, cached=True)

        try:
            response = httpx.get(
                UPSTREAM.format(z=z, x=x, y=y),
                timeout=self.timeout_s,
                follow_redirects=True,
                headers={"User-Agent": "surf-infographics/0.1 (local-first, personal use)"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"tile z={z} x={x} y={y} is not cached and upstream is unreachable: {exc}"
            raise TileError(msg) from exc

        data = response.content
        if not data:
            msg = f"upstream returned an empty tile for z={z} x={x} y={y}"
            raise TileError(msg)

        self._store(z, x, y, data)
        return Tile(data=data, cached=False)

    def _store(self, z: int, x: int, y: int, data: bytes) -> None:
        """Write a tile, atomically.

        Via a temporary file in the same directory and a rename, so a process killed
        mid-write leaves no half tile behind. A truncated JPEG on disk would be served
        forever after, and would look like a rendering bug rather than a storage one.
        """
        path = self.path_for(z, x, y)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{id(data):x}.part")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def count(self) -> int:
        """How many tiles are on disk. For the diagnostics view, and for tests."""
        return sum(1 for _ in self.root.rglob("*.jpg")) if self.root.is_dir() else 0


def cache_headers() -> dict[str, str]:
    """Headers every tile response carries."""
    return {"Cache-Control": _CACHE_CONTROL}
