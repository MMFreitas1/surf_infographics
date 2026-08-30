"""GPX: a degraded tier, and the UI must say so (ADR-0002).

Garmin Connect's GPX export **drops every record that had no GPS fix**. Measured on the
reference session that is 1941 of 3790 records -- and it discards the heart rate and
cumulative distance those records carried perfectly well. Speed and cumulative distance
are absent from the export entirely.

So a GPX activity has no ``NO_FIX`` windows by construction: the seconds that had no fix
are simply not in the file. They surface as ``MISSING_RECORD`` gaps instead, which is why
this parser's blind seconds still agree with the FIT's.
"""

from __future__ import annotations

import re
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

_SPORT_VERSION_SUFFIX = re.compile(r"_v\d+$")
"""Garmin versions its sport slugs (``surfing_v2``); the version is not part of the sport."""


def _sport_name(track: Element | None) -> str:
    """The track's declared type, with Garmin's version suffix removed."""
    if track is None:
        return "unknown"
    raw = text_of(first_local(track, "type")).lower()
    if not raw:
        return "unknown"
    return _SPORT_VERSION_SUFFIX.sub("", raw)


def _heart_rate(element: Element | None) -> int | None:
    """Heart rate, dropped when outside the range a pulse can take."""
    value = int_of(element)
    if value is None or not 20 <= value <= 250:
        return None
    return value


def _coordinates(point: Element) -> tuple[float | None, float | None]:
    """Both coordinates or neither, and never a point off the globe."""
    try:
        lat = float(point.attrib["lat"])
        lon = float(point.attrib["lon"])
    except (KeyError, ValueError):
        return None, None
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None, None
    return lat, lon


def _to_sample(point: Element) -> Sample | None:
    """Build a sample from one ``trkpt``, or None when it carries no usable time."""
    t = parse_iso_time(text_of(first_local(point, "time")))
    if t is None:
        return None
    lat, lon = _coordinates(point)
    return Sample(
        t=t,
        lat=lat,
        lon=lon,
        hr_bpm=_heart_rate(first_local(point, "hr")),
        temp_c=float_of(first_local(point, "atemp")),
    )


def _start_time(root: Element, samples: list[Sample]) -> float:
    """Prefer the file's own metadata time, fall back to the first point."""
    metadata = first_local(root, "metadata")
    if metadata is not None:
        declared = parse_iso_time(text_of(first_local(metadata, "time")))
        if declared is not None:
            return declared
    return samples[0].t


def parse_gpx(
    data: bytes, source_file: str = "", *, gap_tolerance: float = GAP_TOLERANCE
) -> Activity:
    """Parse a GPX track into the canonical Activity, tagged as degraded fidelity."""
    try:
        root = fromstring(data)  # local, first-party files only
    except ParseError as exc:
        msg = f"not valid XML: {exc}"
        raise IngestError(msg) from exc

    points = list(iter_local(root, "trkpt"))
    if not points:
        msg = "no trkpt elements: this GPX holds no track"
        raise IngestError(msg)

    samples = [sample for sample in map(_to_sample, points) if sample is not None]
    if not samples:
        msg = "no trkpt carried a usable timestamp"
        raise IngestError(msg)
    samples.sort(key=lambda sample: sample.t)
    start = _start_time(root, samples)

    return Activity(
        activity_id=content_hash("gpx", start, samples[0].t, len(samples))[:16],
        sport=_sport_name(first_local(root, "trk")),
        start_time=start,
        fidelity=Fidelity.GPX,
        samples=samples,
        blind_windows=derive_blind_windows(samples, gap_tolerance=gap_tolerance),
        device="",  # the file names its exporter, not the watch. We do not conflate them.
        source_file=source_file,
    )
