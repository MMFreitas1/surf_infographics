"""TCX: a partial tier (ADR-0002).

TCX keeps more than GPX -- distance, and speed where the exporter wrote a ``TPX``
extension -- but it is still a summary export, not the recording. Unlike GPX it *can*
carry a trackpoint with no ``Position``, so a TCX activity may contain both kinds of
blind window.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element, ParseError, fromstring

from surf.ingest.blind import GAP_TOLERANCE, derive_blind_windows
from surf.ingest.errors import IngestError
from surf.ingest.xml_common import (
    first_local,
    float_of,
    int_of,
    iter_local,
    parse_iso_time,
    text_of,
)
from surf.models import Activity, Fidelity, Sample
from surf.pipeline import content_hash


def _heart_rate(point: Element) -> int | None:
    """``HeartRateBpm/Value``, dropped when outside the range a pulse can take."""
    container = first_local(point, "HeartRateBpm")
    if container is None:
        return None
    value = int_of(first_local(container, "Value"))
    if value is None or not 20 <= value <= 250:
        return None
    return value


def _coordinates(point: Element) -> tuple[float | None, float | None]:
    """Both coordinates or neither. A trackpoint may legitimately have no Position."""
    position = first_local(point, "Position")
    if position is None:
        return None, None
    lat = float_of(first_local(position, "LatitudeDegrees"))
    lon = float_of(first_local(position, "LongitudeDegrees"))
    if lat is None or lon is None or abs(lat) > 90.0 or abs(lon) > 180.0:
        return None, None
    return lat, lon


def _speed(point: Element) -> float | None:
    """Speed from the TPX extension, in m/s, when the exporter wrote one."""
    speed = float_of(first_local(point, "Speed"))
    return speed if speed is not None and speed >= 0.0 else None


def _to_sample(point: Element) -> Sample | None:
    """Build a sample from one ``Trackpoint``, or None when it carries no usable time."""
    t = parse_iso_time(text_of(first_local(point, "Time")))
    if t is None:
        return None
    lat, lon = _coordinates(point)
    distance = float_of(first_local(point, "DistanceMeters"))
    return Sample(
        t=t,
        lat=lat,
        lon=lon,
        speed_ms=_speed(point),
        hr_bpm=_heart_rate(point),
        distance_m=distance if distance is not None and distance >= 0.0 else None,
    )


def _device_name(root: Element) -> str:
    """The ``Creator`` block names the recording device -- unlike GPX's exporter tag."""
    for activity in iter_local(root, "Activity"):
        creator = first_local(activity, "Creator")
        if creator is not None:
            name = text_of(first_local(creator, "Name"))
            if name:
                return name
    return ""


def parse_tcx(
    data: bytes, source_file: str = "", *, gap_tolerance: float = GAP_TOLERANCE
) -> Activity:
    """Parse a TCX activity into the canonical Activity, tagged as partial fidelity."""
    try:
        root = fromstring(data)  # local, first-party files only
    except ParseError as exc:
        msg = f"not valid XML: {exc}"
        raise IngestError(msg) from exc

    points = list(iter_local(root, "Trackpoint"))
    if not points:
        msg = "no Trackpoint elements: this TCX holds no track"
        raise IngestError(msg)

    samples = [sample for sample in map(_to_sample, points) if sample is not None]
    if not samples:
        msg = "no Trackpoint carried a usable timestamp"
        raise IngestError(msg)
    samples.sort(key=lambda sample: sample.t)

    activity = first_local(root, "Activity")
    sport = (activity.attrib.get("Sport", "").lower() if activity is not None else "") or "unknown"
    declared = None
    if activity is not None:
        declared = parse_iso_time(text_of(first_local(activity, "Id")))
    start = declared if declared is not None else samples[0].t

    return Activity(
        activity_id=content_hash("tcx", start, samples[0].t, len(samples))[:16],
        sport=sport,
        start_time=start,
        fidelity=Fidelity.TCX,
        samples=samples,
        blind_windows=derive_blind_windows(samples, gap_tolerance=gap_tolerance),
        device=_device_name(root),
        source_file=source_file,
    )
