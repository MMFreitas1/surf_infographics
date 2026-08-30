"""The local metric frame. A projection error here would look like a kinematics bug."""

import math

import pytest

from surf.geo import M_PER_DEG_LAT, LocalFrame

FRAME = LocalFrame(lat0=38.0, lon0=-9.0)


def test_the_origin_is_the_origin():
    assert FRAME.to_metres(38.0, -9.0) == (0.0, 0.0)


def test_a_degree_of_latitude_is_a_degree_of_latitude():
    _, north = FRAME.to_metres(39.0, -9.0)
    assert north == pytest.approx(M_PER_DEG_LAT)


def test_longitude_shrinks_with_latitude():
    """At 38 degrees a degree of longitude is about cos(38) of one of latitude."""
    east, _ = FRAME.to_metres(38.0, -8.0)
    assert east == pytest.approx(M_PER_DEG_LAT * math.cos(math.radians(38.0)))
    assert east < M_PER_DEG_LAT


def test_the_projection_round_trips():
    for lat, lon in ((38.001, -9.002), (37.998, -8.997), (38.0, -9.0)):
        x, y = FRAME.to_metres(lat, lon)
        back_lat, back_lon = FRAME.to_degrees(x, y)
        assert back_lat == pytest.approx(lat, abs=1e-12)
        assert back_lon == pytest.approx(lon, abs=1e-12)


def test_metres_round_trip_too():
    for x, y in ((0.0, 0.0), (250.0, -80.0), (-1000.0, 1000.0)):
        lat, lon = FRAME.to_degrees(x, y)
        back_x, back_y = FRAME.to_metres(lat, lon)
        assert back_x == pytest.approx(x, abs=1e-6)
        assert back_y == pytest.approx(y, abs=1e-6)


def test_a_pole_is_refused_rather_than_dividing_by_a_vanishing_cosine():
    with pytest.raises(ValueError, match="too close to a pole"):
        LocalFrame(lat0=89.5, lon0=0.0)
