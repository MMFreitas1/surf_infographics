"""Source-file parsers. FIT is primary; GPX/TCX are degraded tiers (ADR-0002).

Ingest reads only first-party recorded signal. Developer fields written by third-party
apps are skipped without being decoded (ADR-0008, ADR-0009).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from xml.etree.ElementTree import ParseError, fromstring

from surf.ingest.blind import (
    GAP_TOLERANCE,
    blind_from_missing_positions,
    blind_from_time_gaps,
    derive_blind_windows,
    nominal_interval,
)
from surf.ingest.errors import IngestError, UnsupportedFormatError
from surf.ingest.fit import FitError, is_fit, parse_fit
from surf.ingest.gpx import parse_gpx
from surf.ingest.tcx import parse_tcx
from surf.ingest.xml_common import local_name
from surf.models import Activity

__all__ = [
    "GAP_TOLERANCE",
    "Activity",
    "FitError",
    "IngestError",
    "UnsupportedFormatError",
    "blind_from_missing_positions",
    "blind_from_time_gaps",
    "derive_blind_windows",
    "is_fit",
    "nominal_interval",
    "parse_activity",
    "parse_file",
    "parse_fit",
    "parse_gpx",
    "parse_tcx",
    "source_digest",
]


def source_digest(data: bytes) -> str:
    """SHA-256 of the uploaded bytes. Two uploads of one file are one activity."""
    return hashlib.sha256(data).hexdigest()


def _xml_root_name(data: bytes) -> str | None:
    """Local name of the XML root element, or None when the bytes are not XML."""
    try:
        # Local, first-party files only: nothing here is fetched from a network.
        return local_name(fromstring(data).tag)
    except ParseError:
        return None


def parse_activity(
    data: bytes, source_file: str = "", *, gap_tolerance: float = GAP_TOLERANCE
) -> Activity:
    """Parse any supported activity file, dispatching on content rather than filename.

    The extension is not trusted: a ``.fit`` that is really a GPX still parses correctly,
    and a file with no extension at all still works.
    """
    if is_fit(data):
        return parse_fit(data, source_file, gap_tolerance=gap_tolerance)
    root = _xml_root_name(data)
    if root == "gpx":
        return parse_gpx(data, source_file, gap_tolerance=gap_tolerance)
    if root == "TrainingCenterDatabase":
        return parse_tcx(data, source_file, gap_tolerance=gap_tolerance)
    msg = "unrecognised activity file: expected FIT, GPX or TCX"
    raise UnsupportedFormatError(msg)


def parse_file(path: Path, *, gap_tolerance: float = GAP_TOLERANCE) -> Activity:
    """Parse an activity file from disk, recording its name on the Activity."""
    return parse_activity(path.read_bytes(), source_file=path.name, gap_tolerance=gap_tolerance)
