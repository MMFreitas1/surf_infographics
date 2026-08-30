"""GPX and TCX parsing, against committed fixtures with fabricated coordinates.

CI never holds the reference session, so these fixtures are the only coverage the degraded
tiers get there.
"""

from pathlib import Path

import pytest

from surf.ingest import parse_activity, parse_file
from surf.ingest.errors import IngestError, UnsupportedFormatError
from surf.models import BlindCause, Fidelity

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def gpx():
    return parse_file(FIXTURES / "minimal.gpx")


@pytest.fixture
def tcx():
    return parse_file(FIXTURES / "minimal.tcx")


def test_gpx_is_tagged_as_degraded_fidelity(gpx):
    assert gpx.fidelity is Fidelity.GPX


def test_gpx_reads_points_time_and_heart_rate(gpx):
    assert len(gpx.samples) == 6
    assert gpx.samples[0].hr_bpm == 100
    assert gpx.samples[0].temp_c == 21.0
    assert gpx.duration_s == 8.0


def test_gpx_sport_drops_garmins_version_suffix(gpx):
    """The file says ``surfing_v2``; the sport is surfing."""
    assert gpx.sport == "surfing"


def test_gpx_has_no_speed_or_distance_because_the_export_omits_them(gpx):
    assert all(sample.speed_ms is None for sample in gpx.samples)
    assert all(sample.distance_m is None for sample in gpx.samples)


def test_gpx_gap_becomes_a_missing_record_window(gpx):
    """GPX drops position-less records, so its blind time can only appear as a gap."""
    assert [w.cause for w in gpx.blind_windows] == [BlindCause.MISSING_RECORD]
    assert gpx.blind_seconds == 3.0


def test_gpx_does_not_claim_a_device(gpx):
    """The file names Garmin Connect, which exported it -- not the watch that recorded it."""
    assert gpx.device == ""


def test_tcx_is_tagged_as_partial_fidelity(tcx):
    assert tcx.fidelity is Fidelity.TCX


def test_tcx_reads_distance_speed_and_device(tcx):
    assert len(tcx.samples) == 4
    assert tcx.samples[1].distance_m == 1.5
    assert tcx.samples[1].speed_ms == 1.5
    assert tcx.device == "Fixture Watch"


def test_tcx_trackpoint_without_position_is_a_no_fix_window(tcx):
    assert tcx.samples[2].has_position is False
    assert tcx.samples[2].hr_bpm == 102
    assert [w.cause for w in tcx.blind_windows] == [BlindCause.NO_FIX]
    assert tcx.blind_seconds == 1.0


def test_dispatch_reads_content_not_the_file_name():
    """A GPX named .fit still parses. The extension is a hint, not evidence."""
    data = (FIXTURES / "minimal.gpx").read_bytes()
    assert parse_activity(data, "mislabelled.fit").fidelity is Fidelity.GPX


def test_unrecognised_bytes_are_rejected():
    with pytest.raises(UnsupportedFormatError):
        parse_activity(b"just some text")


def test_xml_that_is_not_an_activity_is_rejected():
    with pytest.raises(UnsupportedFormatError):
        parse_activity(b"<?xml version='1.0'?><something-else/>")


def test_a_gpx_with_no_track_is_rejected():
    with pytest.raises(IngestError, match="no trkpt"):
        parse_activity(b"<?xml version='1.0'?><gpx><trk><trkseg/></trk></gpx>")
