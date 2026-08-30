"""Build FIT byte streams by hand, so the decoder can be tested on what real files omit.

The reference session is a single device's output: 33 definition messages, every one
little-endian, and not one compressed-timestamp header. Those paths are in the format and
other Garmin devices emit them, so the only way to cover them is to encode the bytes here
against the spec.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

from surf.ingest.fit import crc16

FieldDef = tuple[int, int, int]
"""(field definition number, size in bytes, base type number)."""

DeveloperFieldDef = tuple[int, int, int]
"""(field number, size in bytes, developer data index)."""

PROTOCOL_VERSION = 0x10
PROFILE_VERSION = 2195

BASE_UINT8 = 2
BASE_SINT32 = 5
BASE_UINT32 = 6


def definition_message(
    local: int,
    global_number: int,
    fields: Sequence[FieldDef],
    *,
    endian: str = "<",
    developer_fields: Sequence[DeveloperFieldDef] = (),
) -> bytes:
    """Encode a definition message, optionally declaring a developer-field block."""
    header = 0x40 | (local & 0x0F) | (0x20 if developer_fields else 0x00)
    architecture = 0 if endian == "<" else 1
    out = bytes([header, 0x00, architecture])
    out += struct.pack(f"{endian}H", global_number)
    out += bytes([len(fields)])
    for number, size, base_type in fields:
        out += bytes([number, size, base_type])
    if developer_fields:
        out += bytes([len(developer_fields)])
        for number, size, index in developer_fields:
            out += bytes([number, size, index])
    return out


def data_message(local: int, payload: bytes) -> bytes:
    """Encode a normal data message."""
    return bytes([local & 0x0F]) + payload


def compressed_message(local: int, time_offset: int, payload: bytes) -> bytes:
    """Encode a compressed-timestamp data message carrying a 5-bit seconds offset."""
    return bytes([0x80 | ((local & 0x03) << 5) | (time_offset & 0x1F)]) + payload


def fit_file(body: bytes, *, header_size: int = 12, corrupt_crc: bool = False) -> bytes:
    """Wrap message bytes in a FIT header and trailing CRC."""
    header = bytes([header_size, PROTOCOL_VERSION])
    header += struct.pack("<H", PROFILE_VERSION)
    header += struct.pack("<I", len(body))
    header += b".FIT"
    if header_size == 14:
        header += struct.pack("<H", crc16(header[:12]))
    payload = header + body
    checksum = crc16(payload)
    if corrupt_crc:
        checksum ^= 0xFFFF
    return payload + struct.pack("<H", checksum)


def record_fields() -> list[FieldDef]:
    """A record definition covering timestamp, position, heart rate and speed."""
    return [
        (253, 4, BASE_UINT32),  # timestamp
        (0, 4, BASE_SINT32),  # position_lat, semicircles
        (1, 4, BASE_SINT32),  # position_long, semicircles
        (3, 1, BASE_UINT8),  # heart_rate
        (73, 4, BASE_UINT32),  # enhanced_speed, mm/s
    ]


def record_payload(
    timestamp: int,
    *,
    lat: int = 0x7FFFFFFF,
    lon: int = 0x7FFFFFFF,
    heart_rate: int = 0xFF,
    speed_mms: int = 0xFFFFFFFF,
    endian: str = "<",
) -> bytes:
    """Encode one record. Every argument defaults to its 'nothing recorded' sentinel."""
    return struct.pack(f"{endian}IiiBI", timestamp, lat, lon, heart_rate, speed_mms)
