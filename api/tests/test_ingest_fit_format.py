"""Decoder coverage for the parts of the FIT format the reference session never exercises.

The one real file we hold is entirely little-endian, carries no compressed-timestamp
header, and its CRC is valid. Everything below is therefore built byte by byte.
"""

import struct

import pytest

from fit_builder import (
    BASE_UINT8,
    BASE_UINT32,
    compressed_message,
    data_message,
    definition_message,
    fit_file,
    record_fields,
    record_payload,
)
from surf.ingest.fit import (
    FIT_EPOCH_OFFSET,
    FitError,
    _apply_time_offset,
    decode_messages,
    is_fit,
    parse_fit,
)

MSG_RECORD = 20
TIMESTAMP = 1_000_000


def test_little_endian_record_decodes():
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP, heart_rate=120, speed_mms=3500))
    records = decode_messages(fit_file(body))[MSG_RECORD]
    assert records == [{253: TIMESTAMP, 3: 120, 73: 3500}]


def test_big_endian_definition_decodes_to_the_same_values():
    """The architecture byte is per definition message, and both paths must agree."""
    little = definition_message(0, MSG_RECORD, record_fields())
    little += data_message(0, record_payload(TIMESTAMP, heart_rate=120, speed_mms=3500))
    big = definition_message(1, MSG_RECORD, record_fields(), endian=">")
    big += data_message(1, record_payload(TIMESTAMP, heart_rate=120, speed_mms=3500, endian=">"))

    decoded = decode_messages(fit_file(little + big))[MSG_RECORD]
    assert decoded[0] == decoded[1]


def test_invalid_sentinels_become_absent_not_zero():
    """A sentinel means 'nothing was recorded'. Reading it as 0 would invent a measurement."""
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP))  # every field left at its sentinel
    assert decode_messages(fit_file(body))[MSG_RECORD] == [{253: TIMESTAMP}]


def test_developer_fields_are_skipped_without_shifting_alignment():
    """ADR-0009: the block is stepped over by declared size and never decoded."""
    body = definition_message(
        0, MSG_RECORD, record_fields(), developer_fields=[(0, 4, 0), (1, 2, 0)]
    )
    body += data_message(
        0,
        record_payload(TIMESTAMP, heart_rate=120) + struct.pack("<IH", 0xDEADBEEF, 0xCAFE),
    )
    body += data_message(
        0,
        record_payload(TIMESTAMP + 1, heart_rate=121) + struct.pack("<IH", 0x11111111, 0x2222),
    )
    records = decode_messages(fit_file(body))[MSG_RECORD]

    assert records == [{253: TIMESTAMP, 3: 120}, {253: TIMESTAMP + 1, 3: 121}]
    assert 0xDEADBEEF not in {v for record in records for v in record.values()}


def test_compressed_timestamps_expand_against_the_last_full_timestamp():
    fields = [(253, 4, BASE_UINT32), (3, 1, BASE_UINT8)]
    body = definition_message(0, MSG_RECORD, fields)
    body += data_message(0, struct.pack("<IB", TIMESTAMP, 100))

    compressed_fields = [(3, 1, BASE_UINT8)]
    body += definition_message(1, MSG_RECORD, compressed_fields)
    base = TIMESTAMP & 0x1F
    body += compressed_message(1, (base + 1) & 0x1F, bytes([101]))
    body += compressed_message(1, (base + 2) & 0x1F, bytes([102]))

    stamps = [record[253] for record in decode_messages(fit_file(body))[MSG_RECORD]]
    assert stamps == [TIMESTAMP, TIMESTAMP + 1, TIMESTAMP + 2]


def test_compressed_timestamp_rolls_over_past_five_bits():
    """The offset counts only 32 s. Dropping the roll would rewind the session 32 s."""
    assert _apply_time_offset(0x100 | 0x1E, 0x1F) == (0x100 | 0x1E) + 1
    assert _apply_time_offset(0x100 | 0x1F, 0x00) == (0x100 | 0x1F) + 1
    assert _apply_time_offset(0x100 | 0x1E, 0x01) == (0x100 | 0x1E) + 3


def test_compressed_timestamps_survive_a_rollover_in_a_real_stream():
    fields = [(253, 4, BASE_UINT32), (3, 1, BASE_UINT8)]
    start = (TIMESTAMP & ~0x1F) | 0x1E  # two seconds short of a rollover
    body = definition_message(0, MSG_RECORD, fields)
    body += data_message(0, struct.pack("<IB", start, 100))
    body += definition_message(1, MSG_RECORD, [(3, 1, BASE_UINT8)])
    for offset in (0x1F, 0x00, 0x01):
        body += compressed_message(1, offset, bytes([101]))

    stamps = [record[253] for record in decode_messages(fit_file(body))[MSG_RECORD]]
    assert stamps == [start, start + 1, start + 2, start + 3]


def test_bad_file_crc_is_rejected():
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP, heart_rate=120))
    with pytest.raises(FitError, match="CRC mismatch"):
        decode_messages(fit_file(body, corrupt_crc=True))


def test_fourteen_byte_header_crc_is_checked():
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP, heart_rate=120))
    good = fit_file(body, header_size=14)
    assert decode_messages(good)[MSG_RECORD]

    corrupted = bytearray(good)
    corrupted[12] ^= 0xFF  # break the stored header CRC
    with pytest.raises(FitError, match="header CRC"):
        decode_messages(bytes(corrupted))


def test_missing_signature_and_short_files_are_rejected():
    with pytest.raises(FitError):
        decode_messages(b"not a fit file at all")
    with pytest.raises(FitError):
        decode_messages(b"\x0c\x10")


def test_data_message_before_its_definition_is_rejected():
    """Guessing a layout would silently produce plausible nonsense."""
    with pytest.raises(FitError, match="undefined local type"):
        decode_messages(fit_file(data_message(0, b"\x00\x00\x00\x00")))


def test_is_fit_distinguishes_formats():
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP))
    assert is_fit(fit_file(body)) is True
    assert is_fit(b"<?xml version='1.0'?><gpx/>") is False


def test_parse_fit_builds_an_activity_with_converted_units():
    file_id_fields = [(1, 2, 4), (2, 2, 4), (3, 4, BASE_UINT32), (4, 4, BASE_UINT32)]
    body = definition_message(2, 0, file_id_fields)
    body += data_message(2, struct.pack("<HHII", 1, 3291, 42, TIMESTAMP))
    body += definition_message(3, 18, [(5, 1, 0)])
    body += data_message(3, bytes([38]))
    body += definition_message(0, MSG_RECORD, record_fields())
    body += data_message(
        0,
        record_payload(
            TIMESTAMP,
            lat=int(37.0 / (180.0 / 2**31)),
            lon=int(-8.0 / (180.0 / 2**31)),
            heart_rate=120,
            speed_mms=3500,
        ),
    )

    activity = parse_fit(fit_file(body), source_file="made_up.fit")

    assert activity.sport == "surfing"
    assert activity.device == "garmin:3291"
    assert activity.fidelity == "fit"
    assert activity.start_time == TIMESTAMP + FIT_EPOCH_OFFSET
    assert activity.source_file == "made_up.fit"
    sample = activity.samples[0]
    assert sample.t == TIMESTAMP + FIT_EPOCH_OFFSET
    assert sample.lat == pytest.approx(37.0, abs=1e-6)
    assert sample.lon == pytest.approx(-8.0, abs=1e-6)
    assert sample.speed_ms == pytest.approx(3.5)
    assert sample.hr_bpm == 120


def test_parse_fit_rejects_a_file_with_no_records():
    body = definition_message(0, 0, [(4, 4, BASE_UINT32)])
    body += data_message(0, struct.pack("<I", TIMESTAMP))
    with pytest.raises(FitError, match="no record messages"):
        parse_fit(fit_file(body))


def test_unknown_sport_keeps_its_number_visible():
    body = definition_message(0, 18, [(5, 1, 0)])
    body += data_message(0, bytes([200]))
    body += definition_message(1, MSG_RECORD, record_fields())
    body += data_message(1, record_payload(TIMESTAMP, heart_rate=120))
    assert parse_fit(fit_file(body)).sport == "sport_200"


def test_half_a_fix_is_not_a_position():
    """A latitude with no longitude is not somewhere. It must not read as a fix."""
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP, lat=int(37.0 / (180.0 / 2**31))))
    sample = parse_fit(fit_file(body)).samples[0]
    assert sample.has_position is False
    assert sample.lat is None


def test_impossible_heart_rate_is_dropped_rather_than_failing_ingest():
    body = definition_message(0, MSG_RECORD, record_fields())
    body += data_message(0, record_payload(TIMESTAMP, heart_rate=0))
    assert parse_fit(fit_file(body)).samples[0].hr_bpm is None
