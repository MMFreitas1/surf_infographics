"""The shore's angle, from the committed extract (ADR-0022).

Three claims are defended here, and only the first is arithmetic.

**The fit has no preferred direction.** A coastline is not a function of easting, so ordinary
least squares of northing on easting is the wrong estimator: a shore running due north-south
has infinite slope and OLS answers plausibly and wrongly rather than failing.
`test_a_coast_running_due_north_recovers_due_north` is the pin, and it would fail on any
implementation that fitted `y = mx + c`.

**An angle is all this module returns.** Not a side, not a waterline, not a position. GSHHG
places the reference session's sit spot *inside* its land polygon, so anything derived from
which side of the line a point falls on would be confidently wrong; handedness comes from the
walk instead, in L2.

**Absence is a state, never a default.** A position the extract does not cover returns
nothing, so a caller cannot accidentally receive due north and treat it as a measurement.
"""

import json
import math
from itertools import pairwise
from pathlib import Path

import pytest

from surf.coast import (
    COAST_PATH,
    DEFAULT_RADIUS_M,
    Coastline,
    CoastlineError,
    bearing_near,
    fit_bearing,
    load,
    segment_near,
)

M_PER_DEG_LAT = 111_320.0


def straight_coast(bearing_deg: float, *, lat: float = 38.0, lon: float = -9.0, span_m=4000.0):
    """A synthetic coast running at a known compass bearing through a known point.

    Built in metres and converted back, so the bearing the test asks for is the bearing in
    the local tangent plane -- which is the plane the fit works in.
    """
    theta = math.radians(bearing_deg)
    east, north = math.sin(theta), math.cos(theta)
    per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat))
    vertices = []
    for step in range(-int(span_m // 2), int(span_m // 2) + 1, 100):
        vertices.append([lon + east * step / per_deg_lon, lat + north * step / M_PER_DEG_LAT])
    return Coastline(
        lines=(tuple((x, y) for x, y in vertices),),
        sha256="synthetic",
        source="synthetic straight coast",
        licence="n/a",
        vertices=len(vertices),
    )


# -- the estimator -----------------------------------------------------------------------


@pytest.mark.parametrize("bearing", [0.0, 15.0, 45.0, 90.0, 120.0, 165.3, 179.0])
def test_a_synthetic_coast_at_a_known_angle_recovers_that_angle(bearing):
    coast = straight_coast(bearing)

    fit = bearing_near(38.0, -9.0, 1500.0, coast=coast)

    assert fit is not None
    assert fit.bearing_deg == pytest.approx(bearing, abs=0.1)
    assert fit.residual_m == pytest.approx(0.0, abs=0.5)


def test_a_coast_running_due_north_recovers_due_north():
    """The OLS trap, by name.

    Fitting northing as a function of easting gives this coast infinite slope. Total least
    squares has no preferred axis, so it recovers 0 degrees exactly -- and an implementation
    that regressed one coordinate on the other would fail here and nowhere else.
    """
    fit = bearing_near(38.0, -9.0, 1500.0, coast=straight_coast(0.0))

    assert fit is not None
    assert fit.bearing_deg == pytest.approx(0.0, abs=0.05)


def test_the_angle_is_mod_180_because_a_line_has_no_direction():
    """The same coast described forwards and backwards is the same coast."""
    forward = straight_coast(30.0)
    backward = Coastline(
        lines=(tuple(reversed(forward.lines[0])),),
        sha256="synthetic",
        source="reversed",
        licence="n/a",
        vertices=forward.vertices,
    )

    assert bearing_near(38.0, -9.0, 1500.0, coast=forward).bearing_deg == pytest.approx(
        bearing_near(38.0, -9.0, 1500.0, coast=backward).bearing_deg, abs=0.05
    )
    assert 0.0 <= bearing_near(38.0, -9.0, 1500.0, coast=forward).bearing_deg < 180.0


def test_too_few_points_is_nothing_rather_than_a_line_through_two():
    assert fit_bearing([]) is None
    assert fit_bearing([(0.0, 0.0)]) is None
    assert fit_bearing([(0.0, 0.0), (10.0, 10.0)]) is None


def test_a_cluster_with_no_axis_is_refused():
    """Identical points have no direction. Inventing one would be worse than admitting it."""
    assert fit_bearing([(5.0, 5.0)] * 20) is None


def test_the_residual_is_reported_and_grows_with_a_bend():
    """Reported, never a gate -- Natural Earth's 4.3 m residual near the reference peak comes
    from having one vertex within a kilometre, so a small residual can mean a poor source."""
    bent = Coastline(
        lines=(((-9.0, 38.0), (-9.0, 38.009), (-8.99, 38.018)),),
        sha256="synthetic",
        source="a bend",
        licence="n/a",
        vertices=3,
    )

    straight = bearing_near(38.009, -9.0, 1500.0, coast=straight_coast(0.0))
    curved = bearing_near(38.009, -9.0, 1500.0, coast=bent)

    assert curved.residual_m > straight.residual_m


# -- resampling --------------------------------------------------------------------------


def test_points_come_back_at_the_requested_spacing_not_at_the_vertices():
    """A source digitised every 100 m and one digitised every 2.7 km must mean the same thing
    at the same radius, which is only true if the window is walked rather than filtered."""
    points = segment_near(38.0, -9.0, 1000.0, step_m=50.0, coast=straight_coast(90.0))

    gaps = [math.dist(a, b) for a, b in pairwise(points) if math.dist(a, b) > 0]
    assert gaps
    assert max(gaps) == pytest.approx(50.0, abs=1.0)


def test_nothing_outside_the_window_is_returned():
    points = segment_near(38.0, -9.0, 300.0, coast=straight_coast(90.0))

    assert points
    assert max(math.hypot(x, y) for x, y in points) <= 300.0


def test_a_position_the_extract_does_not_cover_returns_nothing():
    """Absence is a state the caller handles. Never a default bearing."""
    coast = straight_coast(90.0, lat=38.0, lon=-9.0)

    assert segment_near(10.0, 100.0, DEFAULT_RADIUS_M, coast=coast) == []
    assert bearing_near(10.0, 100.0, DEFAULT_RADIUS_M, coast=coast) is None


# -- the committed extract ---------------------------------------------------------------


def test_the_committed_extract_loads_and_identifies_itself():
    coast = load()

    assert coast.lines
    assert coast.vertices > 5_000
    assert len(coast.sha256) == 64
    assert "GSHHG 2.3.7" in coast.source
    assert "LGPL" in coast.licence


def test_the_extract_is_read_once_per_path():
    """Memoised: the file is a quarter of a megabyte and the answer never changes."""
    assert load() is load()


def test_the_extract_covers_the_portuguese_coast_and_not_the_atlantic():
    """Two cheap sanity checks on reach, using landmarks rather than the session's own spot.

    Cape St Vincent is the south-west corner of Europe and Cape Carvoeiro is the Peniche
    headland; both are public geography and neither is anywhere Miguel surfed.
    """
    assert bearing_near(37.023, -8.997, DEFAULT_RADIUS_M) is not None  # Cape St Vincent
    assert bearing_near(39.360, -9.408, DEFAULT_RADIUS_M) is not None  # Cape Carvoeiro
    assert bearing_near(38.0, -20.0, DEFAULT_RADIUS_M) is None  # mid-Atlantic


def test_a_bearing_from_the_extract_is_stable_across_windows():
    """Measured 2026-10-24: this source swings 3.0 degrees across 200-2000 m at the reference
    peak where the dense OSM measuring stick swings 20.6. The coarser spacing is what does
    that, so the declared window is not a knife-edge. Checked here on a public headland."""
    bearings = [
        bearing_near(39.360, -9.408, radius).bearing_deg for radius in (500.0, 1000.0, 1500.0)
    ]

    spread = max(bearings) - min(bearings)
    assert spread < 25.0, f"window sensitivity grew to {spread:.1f} deg"


def test_the_sha256_is_of_the_file_and_changes_with_it(tmp_path):
    """It travels into L2's params, so a bearing can never be served under a coastline it was
    not computed from. That only holds if it is the file's own digest."""
    original = load()
    document = {
        "properties": {"source": "t", "licence": "t"},
        "features": [
            {"geometry": {"type": "LineString", "coordinates": [[-9.0, 38.0], [-9.0, 38.01]]}}
        ],
    }
    first = tmp_path / "a.geojson"
    first.write_text(json.dumps(document))
    document["features"][0]["geometry"]["coordinates"][1][1] = 38.02
    second = tmp_path / "b.geojson"
    second.write_text(json.dumps(document))

    assert load(first).sha256 != load(second).sha256
    assert load(first).sha256 != original.sha256


def test_a_missing_extract_is_an_error_and_not_a_silent_default(tmp_path):
    with pytest.raises(CoastlineError):
        load(tmp_path / "nope.geojson")


def test_a_document_with_no_lines_is_an_error(tmp_path):
    empty = tmp_path / "empty.geojson"
    empty.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

    with pytest.raises(CoastlineError):
        load(empty)


def test_the_extract_ships_inside_the_package():
    """Enforced, not remembered.

    ``api/Dockerfile`` copies only ``pyproject.toml``, ``uv.lock`` and ``src``, so an extract
    anywhere else is absent from the container -- and the failure would be quiet, because L2
    falls through to its velocity fallback rather than erroring. ``.gitignore`` also carries
    ``data/`` with no leading slash, which matches ``api/data/`` and would have stopped the
    file being committed in the first place. This test fails if either trap is walked into
    again.
    """
    import surf

    package = Path(surf.__file__).resolve().parent

    assert COAST_PATH.is_relative_to(package)
    assert COAST_PATH.is_file()
    assert "data" not in COAST_PATH.relative_to(package).parts
