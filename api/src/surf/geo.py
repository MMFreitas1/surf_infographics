"""A local metric frame for one session.

The smoother works in metres, not degrees: a Kalman filter needs a space where a metre
north and a metre east are the same size, and degrees are not that. A session spans a few
hundred metres, so an equirectangular projection about a session origin is exact to well
under a centimetre here -- three orders of magnitude below GPS noise -- while staying
cheap and exactly invertible. UTM or a geodesic would add a dependency and change nothing
that matters at this scale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

M_PER_DEG_LAT = 111_320.0
"""Metres per degree of latitude. Constant enough over a surf break."""

_MAX_ABS_LAT = 89.0
"""Beyond this the meridians converge hard and the projection stops being invertible."""


@dataclass(frozen=True)
class LocalFrame:
    """Metres east and north of a fixed origin."""

    lat0: float
    lon0: float

    def __post_init__(self) -> None:
        if abs(self.lat0) > _MAX_ABS_LAT:
            msg = f"origin latitude {self.lat0} is too close to a pole to project locally"
            raise ValueError(msg)

    @property
    def m_per_deg_lon(self) -> float:
        """Metres per degree of longitude at this origin's latitude."""
        return M_PER_DEG_LAT * math.cos(math.radians(self.lat0))

    def to_metres(self, lat: float, lon: float) -> tuple[float, float]:
        """Degrees to (east, north) metres from the origin."""
        return (lon - self.lon0) * self.m_per_deg_lon, (lat - self.lat0) * M_PER_DEG_LAT

    def to_degrees(self, x_m: float, y_m: float) -> tuple[float, float]:
        """(east, north) metres back to (lat, lon)."""
        return self.lat0 + y_m / M_PER_DEG_LAT, self.lon0 + x_m / self.m_per_deg_lon
