"""The shore's angle, from a committed geometry file. Not a stage: a lookup.

L2 needs to know which way the coast runs so it can turn "travelled east" into "travelled
shoreward" (ADR-0003). ADR-0011 estimates that from the session's own velocity, and ADR-0022
adds this as a **second, unrelated witness**: on the reference session the two land 4.2 deg
apart, which is what licenses trusting either. Agreement between them is the reliability test
that replaced coherence.

**Three things this module deliberately does not do.**

*It does not say where the water is.* It returns an angle mod 180 and nothing else. GSHHG
places the reference session's sit spot -- where Miguel floated for 23 minutes -- 15 m inland,
*inside* its land polygon, so a point-in-polygon test answers confidently and wrongly. Which
perpendicular points to shore comes from the walk instead (ADR-0022): the audit separates the
walk from the session, and all 489 observed walking seconds of the reference recording fall on
one side with no exceptions.

*It does not draw.* Nothing renders this line. Natural Earth would place the same spot 549 m
out to sea and GSHHG 15 m inland, and neither error reaches the arithmetic precisely because
only the angle is read. That is what makes a coarse source viable, and it is why there is no
waterline in any API response.

*It does not parse a shapefile.* The upstream distribution is a 150 MB shapefile archive;
``reference/coast/vendor.py`` converts it once, by hand, and product code reads the GeoJSON
that comes out with stdlib ``json``. No binary geometry parser and no geo dependency.

**The window is a declared parameter, because it is the dominant lever.** Fitted on the dense
OSM measuring stick, the same anchor gives 142.0 deg at +-200 m and 168.7 deg at +-1500 m: a
20.6 deg swing, with rms residual growing 14.7 -> 123.9 m. The coast genuinely curves, so a
window is a choice rather than a fitting artefact, and a quadratic local-tangent fit does not
rescue it (19.6 deg). ``DEFAULT_RADIUS_M`` is 1000, where this source's 96-281 m spacing
supports a fit and where it agrees with OSM to 0.2 deg.

**Residual is reported and is not a quality gate.** Natural Earth scores a 4.3 m rms residual
near the reference peak against GSHHG's far larger one, and Natural Earth is the worse source:
its fit is straight because it has one vertex within a kilometre, so the line is straight by
poverty rather than by agreement. A fit that cannot be wrong is not thereby right.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

import numpy as np

from surf.geo import LocalFrame

COAST_PATH = Path(__file__).resolve().parent / "reference" / "coast" / "gshhg-2.3.7-pt.geojson"
"""The committed extract, which ships **inside the package**.

Two constraints picked this path. ``data/`` is gitignored wholesale -- it holds activity
files, which are GPS traces and must never be committed (CLAUDE.md) -- so the extract cannot
live there; reference geography is the opposite case and is committed deliberately (ADR-0022).
And ``api/Dockerfile`` copies only ``pyproject.toml``, ``uv.lock`` and ``src``, so anything at
the repo root is absent from the container. A missing coastline would not fail loudly: L2
would fall through to its velocity fallback and the frame would quietly carry one witness
instead of two. Package data is what makes that impossible."""

DEFAULT_RADIUS_M = 1000.0
"""How far either way along the shore to fit. Measured, not assumed -- see the module note."""

DEFAULT_STEP_M = 50.0
"""Spacing the polyline is resampled at before fitting.

Fitting raw vertices would weight a source by how densely it happened to be digitised: OSM
carries a vertex every 29 m near the reference peak and Natural Earth one every 2.7 km, so
the same window would mean two different things. Resampling is what makes a radius comparable
across sources."""

MIN_POINTS = 3
"""Below this there is no line worth fitting, only one through any two points."""


@dataclass(frozen=True)
class Coastline:
    """The extract, in memory, with the identity a cache key needs."""

    lines: tuple[tuple[tuple[float, float], ...], ...]
    """Open polylines as (lon, lat) vertices. Open because a clipped polygon is not a ring,
    and because nothing here needs it to be one."""
    sha256: str
    """Of the file's bytes. Travels into L2's params so a bearing can never be served under a
    coastline it was not computed from -- the reproducibility argument that chose a committed
    file over a live Overpass query (ADR-0022)."""
    source: str
    licence: str
    vertices: int


@dataclass(frozen=True)
class CoastBearing:
    """A fitted shore angle, with everything needed to argue about it."""

    bearing_deg: float
    """The axis the coast runs along, in [0, 180). **Mod 180 by construction**: a line has no
    direction, and pretending otherwise is how a shore axis acquires a sign it never measured."""
    residual_m: float
    """Rms perpendicular distance from the fitted line. Reported, never a gate."""
    points: int
    """How many resampled points the fit rested on."""
    radius_m: float
    """The window it was fitted over, because the answer is meaningless without it."""


class CoastlineError(RuntimeError):
    """The extract is missing or is not the document this module expects."""


@lru_cache(maxsize=4)
def load(path: Path | None = None) -> Coastline:
    """Read and cache the extract. One file read per process.

    Memoised on the path rather than on nothing, so a test can point at a fixture without
    poisoning the cache for the real file.
    """
    target = Path(path) if path is not None else COAST_PATH
    try:
        raw = target.read_bytes()
    except OSError as exc:
        msg = f"coastline extract not readable at {target}"
        raise CoastlineError(msg) from exc

    document = json.loads(raw)
    properties = document.get("properties") or {}
    lines: list[tuple[tuple[float, float], ...]] = []
    for feature in document.get("features", []):
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        if kind == "LineString":
            parts = [geometry["coordinates"]]
        elif kind == "MultiLineString":
            parts = geometry["coordinates"]
        else:
            continue
        for part in parts:
            if len(part) >= 2:
                lines.append(tuple((float(x), float(y)) for x, y in part))

    if not lines:
        msg = f"coastline extract at {target} carries no lines"
        raise CoastlineError(msg)

    return Coastline(
        lines=tuple(lines),
        sha256=hashlib.sha256(raw).hexdigest(),
        source=str(properties.get("source", "unknown")),
        licence=str(properties.get("licence", "unknown")),
        vertices=sum(len(line) for line in lines),
    )


def segment_near(
    lat: float,
    lon: float,
    radius_m: float = DEFAULT_RADIUS_M,
    *,
    step_m: float = DEFAULT_STEP_M,
    coast: Coastline | None = None,
) -> list[tuple[float, float]]:
    """Shore within ``radius_m`` of a point, resampled at fixed spacing, in local metres.

    Returns (easting, northing) about the query point, so the caller can fit a line in metres
    without caring about latitude. An empty list means the extract does not cover this
    position, which is a state for the caller to handle and never a default bearing.
    """
    shore = coast if coast is not None else load()
    frame = LocalFrame(lat0=lat, lon0=lon)
    out: list[tuple[float, float]] = []
    for line in shore.lines:
        projected = [frame.to_metres(vertex_lat, vertex_lon) for vertex_lon, vertex_lat in line]
        if not _touches(projected, radius_m):
            continue
        out.extend(_walk(projected, step_m, radius_m))
    return out


def fit_bearing(
    points: list[tuple[float, float]], radius_m: float = DEFAULT_RADIUS_M
) -> CoastBearing | None:
    """Total least squares through the points: the principal axis of the centred cloud.

    **Not** ordinary least squares of northing on easting. OLS minimises vertical offsets and
    assumes a function of easting, which a coastline is not: a shore running due north-south
    has infinite slope and OLS returns a plausible, wrong bearing instead of failing. The
    principal axis has no preferred direction, so it recovers that coast exactly as well as
    any other -- ``test_a_coast_running_due_north_recovers_due_north`` is the pin.

    ``None`` when there is nothing to fit, or when the points are so concentrated that no
    direction dominates -- a cluster has no axis, and inventing one would be worse than
    admitting it.
    """
    if len(points) < MIN_POINTS:
        return None

    array = np.asarray(points, dtype=float)
    centred = array - array.mean(axis=0)
    _, singular, basis = np.linalg.svd(centred, full_matrices=False)
    if singular[0] <= 0.0:
        return None

    east, north = basis[0]
    normal = np.array([-north, east])
    return CoastBearing(
        bearing_deg=math.degrees(math.atan2(east, north)) % 180.0,
        residual_m=float(np.sqrt(np.mean((centred @ normal) ** 2))),
        points=len(array),
        radius_m=radius_m,
    )


def bearing_near(
    lat: float,
    lon: float,
    radius_m: float = DEFAULT_RADIUS_M,
    *,
    step_m: float = DEFAULT_STEP_M,
    coast: Coastline | None = None,
) -> CoastBearing | None:
    """The shore's angle near a position, or ``None`` where the extract does not reach.

    What L2 calls. The two halves are public separately so the resampling can be inspected
    without the fit, which is how the window was measured in the first place.
    """
    return fit_bearing(
        segment_near(lat, lon, radius_m, step_m=step_m, coast=coast), radius_m=radius_m
    )


def _touches(points: list[tuple[float, float]], radius_m: float) -> bool:
    """Whether any vertex of a projected line falls inside the window.

    A cheap reject. It can miss a line that passes through the window with every *vertex*
    outside it, which at this source's 96-281 m spacing needs a window under ~140 m -- far
    below the measured 1000 m default, and `segment_near` is documented as returning nothing
    where the extract does not reach rather than as being exhaustive.
    """
    return any(math.hypot(x, y) <= radius_m for x, y in points)


def _walk(
    points: list[tuple[float, float]], step_m: float, radius_m: float
) -> list[tuple[float, float]]:
    """Step along a polyline at fixed spacing, keeping the part inside the window.

    The carry across segment boundaries is what makes the spacing uniform along the *line*
    rather than restarting at every vertex -- otherwise a densely digitised stretch would
    contribute more points than a sparse one, which is the weighting this exists to remove.
    """
    out: list[tuple[float, float]] = []
    carry = 0.0
    for (ax, ay), (bx, by) in pairwise(points):
        length = math.hypot(bx - ax, by - ay)
        if length <= 0.0:
            continue
        travelled = carry
        while travelled < length:
            fraction = travelled / length
            point = (ax + (bx - ax) * fraction, ay + (by - ay) * fraction)
            if math.hypot(*point) <= radius_m:
                out.append(point)
            travelled += step_m
        carry = travelled - length
    return out
