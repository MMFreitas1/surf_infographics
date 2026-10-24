"""Convert GSHHG's full-resolution shoreline to the committed GeoJSON extract.

**Run by hand, once, and imported by nothing.** `surf.coast` reads the GeoJSON this writes
with stdlib ``json``; keeping the shapefile reader here is what stops a binary format parser
from becoming product code (ADR-0022).

Usage::

    python reference/coast/vendor.py path/to/GSHHS_shp/f/GSHHS_f_L1.shp

The archive is ~150 MB and is not committed. Download it from
https://www.soest.hawaii.edu/pwessel/gshhg/ -- version 2.3.7, the ``shp`` distribution --
and keep its LICENSE.TXT, which is reproduced in this repo's NOTICE.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

OUT = (
    Path(__file__).resolve().parents[2]
    / "api/src/surf/reference/coast/gshhg-2.3.7-pt.geojson"
)
"""Written **into the package**, not beside this script.

``api/Dockerfile`` copies only ``src``, so an extract at the repo root would be missing
from the container -- and L2 would quietly fall back to its velocity estimator rather
than fail. This script stays outside the package on purpose: it is run by hand and
nothing should be able to import a shapefile reader (ADR-0022)."""

BBOX = (-9.70, 36.90, -6.90, 42.20)
"""Mainland Portugal's Atlantic and Algarve coast, with a little Spain at either end.

Generous on purpose: a coastline does not stop at a border, and clipping exactly to one
would put an artificial discontinuity in the middle of a beach near Caminha or Vila Real de
Santo Antonio. The reach matches the Portugal-only imagery (ADR-0021).
"""

PRECISION = 6
"""Decimal places kept, about 0.1 m. Finer than the 96-281 m vertex spacing this source has
near the reference peak, so rounding cannot be what limits the fit."""


def rings_overlapping(shp: Path, bbox: tuple[float, float, float, float]):
    """Every ring of every polygon whose own bounding box overlaps bbox.

    A minimal ESRI shapefile reader: the header gives the file length in 16-bit words, then
    records follow as (number, length) big-endian pairs with a little-endian body. Only
    shape type 5 (polygon) appears in GSHHS, and its per-record bounding box is what makes
    skipping the rest of the planet cheap.
    """
    west, south, east, north = bbox
    out: list[list[tuple[float, float]]] = []
    with shp.open("rb") as fh:
        total = struct.unpack(">i", fh.read(100)[24:28])[0] * 2
        pos = 100
        while pos < total:
            fh.seek(pos)
            head = fh.read(8)
            if len(head) < 8:
                break
            _, words = struct.unpack(">ii", head)
            if struct.unpack("<i", fh.read(4))[0] == 5:
                xmin, ymin, xmax, ymax = struct.unpack("<4d", fh.read(32))
                if not (xmax < west or xmin > east or ymax < south or ymin > north):
                    n_parts, n_points = struct.unpack("<2i", fh.read(8))
                    parts = struct.unpack(f"<{n_parts}i", fh.read(4 * n_parts))
                    coords = struct.unpack(f"<{2 * n_points}d", fh.read(16 * n_points))
                    for i, start in enumerate(parts):
                        end = parts[i + 1] if i + 1 < n_parts else n_points
                        ring = [(coords[2 * j], coords[2 * j + 1]) for j in range(start, end)]
                        if len(ring) >= 2:
                            out.append(ring)
            pos += 8 + words * 2
    return out


def clip(rings, bbox: tuple[float, float, float, float]):
    """Keep the vertices inside bbox, splitting a ring wherever it leaves.

    A polygon becomes open lines, which is what the consumer wants: `surf.coast` fits a line
    through the shore near a point and never asks which side is land -- that is measured to
    be unanswerable from this file, which places the reference sit spot *inside* its land
    polygon (ADR-0022).
    """
    west, south, east, north = bbox
    out: list[list[tuple[float, float]]] = []
    for ring in rings:
        run: list[tuple[float, float]] = []
        for lon, lat in ring:
            if west <= lon <= east and south <= lat <= north:
                run.append((lon, lat))
            else:
                if len(run) >= 2:
                    out.append(run)
                run = []
        if len(run) >= 2:
            out.append(run)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    shp = Path(argv[1])
    if not shp.is_file():
        print(f"not a file: {shp}")
        return 1

    rings = rings_overlapping(shp, BBOX)
    lines = clip(rings, BBOX)
    vertices = sum(len(line) for line in lines)
    print(f"{len(rings)} ring(s) overlap the box -> {len(lines)} line(s), {vertices} vertices")

    document = {
        "type": "FeatureCollection",
        "properties": {
            "source": "GSHHG 2.3.7, full resolution, level 1 (land/ocean boundary)",
            "upstream": "https://www.soest.hawaii.edu/pwessel/gshhg/",
            "licence": "LGPL v3 or later -- see this repo's NOTICE",
            "extract": "mainland Portugal, clipped at vendor time by reference/coast/vendor.py",
            "bbox": list(BBOX),
            "coordinate_precision": PRECISION,
            "vertices": vertices,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [[round(lon, PRECISION), round(lat, PRECISION)] for lon, lat in line]
                        for line in lines
                    ],
                },
            }
        ],
    }
    OUT.write_text(json.dumps(document, separators=(",", ":")))
    size = OUT.stat().st_size
    print(f"wrote {OUT.name}: {size / 1024:.0f} KiB ({size / 1024 / 1024:.2f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
