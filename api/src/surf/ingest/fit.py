"""FIT decoding: the primary and only full-fidelity source (ADR-0002).

This replaces the throwaway spike in ``research/fit_probe.py``, which existed to answer
"what is actually in the file?" and is not fit to run in production: it drops the offset
carried by compressed-timestamp headers, has no contracts and no CRC checking.

Two rules shape this module:

* **Only first-party recorded signal is decoded** (ADR-0008). The messages and fields read
  here are enumerated as constants below. Nothing else is interpreted.
* **Developer fields are skipped by their declared byte size and never decoded** (ADR-0009).
  Walking the reference file this way consumes exactly to the data end, so resolving
  ``field_description`` (message 206) is unnecessary as well as unwanted.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Any, Final

from surf.ingest.blind import GAP_TOLERANCE, derive_blind_windows
from surf.ingest.errors import IngestError
from surf.models import Activity, Fidelity, Sample
from surf.pipeline import content_hash

FIT_EPOCH_OFFSET: Final = 631_065_600
"""Seconds between the FIT epoch (1989-12-31T00:00:00Z) and the Unix epoch."""

SEMICIRCLES_TO_DEGREES: Final = 180.0 / 2**31
"""FIT stores angles as semicircles: a signed 32-bit sweep of the full circle."""

# --- global message numbers we consume. Anything absent here is not interpreted. ------
MSG_FILE_ID: Final = 0
MSG_SESSION: Final = 18
MSG_RECORD: Final = 20

FIELD_TIMESTAMP: Final = 253
"""Field 253 is ``timestamp`` in every message that has one; it anchors compressed stamps."""

# --- file_id (0) ---
FILE_ID_TYPE: Final = 0
FILE_ID_MANUFACTURER: Final = 1
FILE_ID_PRODUCT: Final = 2
FILE_ID_SERIAL: Final = 3
FILE_ID_TIME_CREATED: Final = 4
FILE_TYPE_ACTIVITY: Final = 4

# --- session (18) ---
SESSION_START_TIME: Final = 2
SESSION_SPORT: Final = 5

# --- record (20) ---
RECORD_POSITION_LAT: Final = 0
RECORD_POSITION_LONG: Final = 1
RECORD_SPEED: Final = 6
RECORD_HEART_RATE: Final = 3
RECORD_DISTANCE: Final = 5
RECORD_TEMPERATURE: Final = 13
RECORD_ENHANCED_SPEED: Final = 73

SPORT_NAMES: Final[dict[int, str]] = {
    0: "generic",
    1: "running",
    2: "cycling",
    5: "swimming",
    11: "walking",
    19: "paddling",
    37: "stand_up_paddleboarding",
    38: "surfing",
    39: "wakeboarding",
    41: "kayaking",
    43: "windsurfing",
    44: "kitesurfing",
}
"""Sport ids we can name with confidence. Anything else keeps its number -- see _sport_name."""

MANUFACTURER_NAMES: Final[dict[int, str]] = {1: "garmin"}
"""Deliberately minimal. We record the ids we read, we do not guess marketing model names."""

BASE_TYPE_STRING: Final = 7


class FitError(IngestError):
    """The bytes are not a FIT file we can decode.

    An ``IngestError``, so a caller handling "this file cannot be read" catches every
    format's failure the same way -- a corrupt FIT is a bad request, not a server fault.
    """


@dataclass(frozen=True)
class BaseType:
    """One FIT base type: its width, struct code, and 'no reading' sentinel."""

    size: int
    fmt: str
    invalid: int | None


BASE_TYPES: Final[dict[int, BaseType]] = {
    0: BaseType(1, "B", 0xFF),  # enum
    1: BaseType(1, "b", 0x7F),  # sint8
    2: BaseType(1, "B", 0xFF),  # uint8
    3: BaseType(2, "h", 0x7FFF),  # sint16
    4: BaseType(2, "H", 0xFFFF),  # uint16
    5: BaseType(4, "i", 0x7FFFFFFF),  # sint32
    6: BaseType(4, "I", 0xFFFFFFFF),  # uint32
    7: BaseType(1, "s", 0x00),  # string
    8: BaseType(4, "f", None),  # float32 -- invalid is NaN
    9: BaseType(8, "d", None),  # float64 -- invalid is NaN
    10: BaseType(1, "B", 0x00),  # uint8z
    11: BaseType(2, "H", 0x00),  # uint16z
    12: BaseType(4, "I", 0x00),  # uint32z
    13: BaseType(1, "B", 0xFF),  # byte
    14: BaseType(8, "q", 0x7FFFFFFFFFFFFFFF),  # sint64
    15: BaseType(8, "Q", 0xFFFFFFFFFFFFFFFF),  # uint64
    16: BaseType(8, "Q", 0x00),  # uint64z
}

_CRC_TABLE: Final = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)  # fmt: skip


def crc16(data: bytes, crc: int = 0) -> int:
    """The FIT CRC-16, computed a nibble at a time as the spec defines it."""
    for byte in data:
        for nibble in (byte & 0x0F, (byte >> 4) & 0x0F):
            check = _CRC_TABLE[crc & 0x0F]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ check ^ _CRC_TABLE[nibble]
    return crc


@dataclass(frozen=True)
class _FieldDef:
    """One field slot inside a definition message."""

    number: int
    size: int
    base_type: int


@dataclass(frozen=True)
class _MessageDef:
    """A local message type: what its data messages look like on the wire."""

    global_number: int
    endian: str
    fields: tuple[_FieldDef, ...]
    developer_bytes: int
    """Total width of the developer-field block, which we skip whole (ADR-0009)."""


def is_fit(data: bytes) -> bool:
    """True when the bytes carry the FIT signature at its fixed offset."""
    return len(data) >= 12 and data[8:12] == b".FIT"


def _read_header(data: bytes) -> tuple[int, int]:
    """Validate the file header and return (header size, data size)."""
    if len(data) < 12:
        msg = "too short to be a FIT file"
        raise FitError(msg)
    header_size = data[0]
    if header_size not in (12, 14):
        msg = f"unexpected FIT header size {header_size}"
        raise FitError(msg)
    if not is_fit(data):
        msg = "missing .FIT signature"
        raise FitError(msg)
    data_size: int = struct.unpack_from("<I", data, 4)[0]
    if header_size == 14:
        stored: int = struct.unpack_from("<H", data, 12)[0]
        if stored and crc16(data[:12]) != stored:
            msg = "header CRC mismatch"
            raise FitError(msg)
    return header_size, data_size


def _verify_file_crc(data: bytes, end: int) -> None:
    """Check the trailing CRC over header and data. A corrupt file fails here, not later."""
    if len(data) < end + 2:
        msg = "file ends before its CRC"
        raise FitError(msg)
    stored: int = struct.unpack_from("<H", data, end)[0]
    actual = crc16(data[:end])
    if stored != actual:
        msg = f"file CRC mismatch: stored {stored:#06x}, computed {actual:#06x}"
        raise FitError(msg)


def _is_invalid(value: Any, invalid: int | None) -> bool:
    """FIT encodes 'nothing was recorded' as a per-type sentinel, or NaN for floats."""
    if isinstance(value, float) and math.isnan(value):
        return True
    return invalid is not None and value == invalid


def _read_value(data: bytes, pos: int, field: _FieldDef, endian: str) -> tuple[Any, int]:
    """Decode one field, returning its value (None when absent) and the new position."""
    end = pos + field.size
    if end > len(data):
        msg = "truncated field"
        raise FitError(msg)
    base = BASE_TYPES.get(field.base_type)
    if base is None:
        return None, end  # unknown base type: skip its declared width, interpret nothing
    raw = data[pos:end]
    if field.base_type == BASE_TYPE_STRING:
        text = raw.split(b"\x00")[0].decode("utf-8", "replace")
        return (text or None), end
    if base.size == 0 or field.size % base.size:
        return None, end  # declared width is not a whole number of elements
    count = field.size // base.size
    values = struct.unpack(f"{endian}{count}{base.fmt}", raw)
    kept = [v for v in values if not _is_invalid(v, base.invalid)]
    if not kept:
        return None, end
    if count == 1:
        return kept[0], end
    return kept, end


def _read_definition(data: bytes, pos: int, *, developer: bool) -> tuple[_MessageDef, int]:
    """Parse a definition message, including the width of any developer-field block."""
    pos += 1  # reserved
    endian = "<" if data[pos] == 0 else ">"
    pos += 1
    global_number: int = struct.unpack_from(f"{endian}H", data, pos)[0]
    pos += 2
    field_count = data[pos]
    pos += 1
    fields = []
    for _ in range(field_count):
        fields.append(_FieldDef(data[pos], data[pos + 1], data[pos + 2] & 0x1F))
        pos += 3
    developer_bytes = 0
    if developer:
        developer_count = data[pos]
        pos += 1
        for _ in range(developer_count):
            developer_bytes += data[pos + 1]
            pos += 3
    return _MessageDef(global_number, endian, tuple(fields), developer_bytes), pos


def _read_data_message(
    data: bytes, pos: int, definition: _MessageDef
) -> tuple[dict[int, Any], int]:
    """Decode the declared fields, then step over the developer block without reading it."""
    values: dict[int, Any] = {}
    for field in definition.fields:
        value, pos = _read_value(data, pos, field, definition.endian)
        if value is not None:
            values[field.number] = value
    return values, pos + definition.developer_bytes  # ADR-0009


def _apply_time_offset(last: int, offset: int) -> int:
    """Expand a 5-bit compressed timestamp offset against the last full timestamp.

    The offset counts seconds in the low 5 bits only, so it rolls over every 32 s. An
    offset below the previous one means a roll happened, and 32 s must be added back.
    """
    previous = last & 0x1F
    if offset >= previous:
        return last + (offset - previous)
    return last + (offset - previous) + 0x20


def decode_messages(data: bytes, *, verify_crc: bool = True) -> dict[int, list[dict[int, Any]]]:
    """Decode a FIT file into ``{global message number: [{field number: value}]}``."""
    header_size, data_size = _read_header(data)
    end = header_size + data_size
    if len(data) < end:
        msg = f"declared data size {data_size} runs past the end of the file"
        raise FitError(msg)
    if verify_crc:
        _verify_file_crc(data, end)

    definitions: dict[int, _MessageDef] = {}
    messages: dict[int, list[dict[int, Any]]] = {}
    last_timestamp: int | None = None
    pos = header_size

    while pos < end:
        header = data[pos]
        pos += 1
        if header & 0x80:  # compressed timestamp header
            local = (header >> 5) & 0x03
            definition = definitions.get(local)
            if definition is None:
                msg = f"data message for undefined local type {local}"
                raise FitError(msg)
            values, pos = _read_data_message(data, pos, definition)
            if last_timestamp is not None:
                last_timestamp = _apply_time_offset(last_timestamp, header & 0x1F)
                values.setdefault(FIELD_TIMESTAMP, last_timestamp)
            messages.setdefault(definition.global_number, []).append(values)
            continue

        local = header & 0x0F
        if header & 0x40:  # definition message
            definitions[local], pos = _read_definition(data, pos, developer=bool(header & 0x20))
            continue

        definition = definitions.get(local)
        if definition is None:
            msg = f"data message for undefined local type {local}"
            raise FitError(msg)
        values, pos = _read_data_message(data, pos, definition)
        stamp = values.get(FIELD_TIMESTAMP)
        if isinstance(stamp, int):
            last_timestamp = stamp
        messages.setdefault(definition.global_number, []).append(values)

    return messages


def _semicircles(value: Any) -> float | None:
    """Convert semicircles to degrees."""
    if not isinstance(value, int):
        return None
    return value * SEMICIRCLES_TO_DEGREES


def _scaled(value: Any, divisor: float) -> float | None:
    """Apply a FIT field scale, e.g. centimetres or millimetres per second."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value) / divisor


def _heart_rate(value: Any) -> int | None:
    """Heart rate, dropped when outside the range a pulse can take.

    The invalid sentinel is already gone by here; a surviving 0 bpm is the strap saying it
    had no contact, which is an absence, not a measurement.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    if not 20 <= value <= 250:
        return None
    return value


def _position(record: dict[int, Any]) -> tuple[float | None, float | None]:
    """Both coordinates or neither: half a fix is not a position."""
    lat = _semicircles(record.get(RECORD_POSITION_LAT))
    lon = _semicircles(record.get(RECORD_POSITION_LONG))
    if lat is None or lon is None:
        return None, None
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None, None  # off the globe: corrupt, not a fix
    return lat, lon


def _to_sample(record: dict[int, Any]) -> Sample | None:
    """Build a canonical sample from a record message, or None if it carries no time."""
    stamp = record.get(FIELD_TIMESTAMP)
    if not isinstance(stamp, int) or isinstance(stamp, bool):
        return None
    lat, lon = _position(record)
    speed = _scaled(record.get(RECORD_ENHANCED_SPEED), 1000.0)
    if speed is None:
        speed = _scaled(record.get(RECORD_SPEED), 1000.0)
    return Sample(
        t=float(stamp + FIT_EPOCH_OFFSET),
        lat=lat,
        lon=lon,
        speed_ms=speed,
        hr_bpm=_heart_rate(record.get(RECORD_HEART_RATE)),
        temp_c=_scaled(record.get(RECORD_TEMPERATURE), 1.0),
        distance_m=_scaled(record.get(RECORD_DISTANCE), 100.0),
    )


def _sport_name(value: Any) -> str:
    """Name the sport where we can cite the id, otherwise keep the number visible."""
    if not isinstance(value, int) or isinstance(value, bool):
        return "unknown"
    return SPORT_NAMES.get(value, f"sport_{value}")


def _device_name(file_id: dict[int, Any]) -> str:
    """``manufacturer:product`` from the ids in the file. We do not invent a model name."""
    manufacturer = file_id.get(FILE_ID_MANUFACTURER)
    product = file_id.get(FILE_ID_PRODUCT)
    if not isinstance(manufacturer, int):
        return ""
    name = MANUFACTURER_NAMES.get(manufacturer, f"manufacturer_{manufacturer}")
    return f"{name}:{product}" if isinstance(product, int) else name


def _activity_id(file_id: dict[int, Any], data: bytes) -> str:
    """A stable id from the recording's own identity, falling back to the file's digest.

    ``file_id`` carries manufacturer, product, serial number and creation time, which
    together identify the recording independently of what the file was named.
    """
    identity = [
        file_id.get(FILE_ID_MANUFACTURER),
        file_id.get(FILE_ID_PRODUCT),
        file_id.get(FILE_ID_SERIAL),
        file_id.get(FILE_ID_TIME_CREATED),
    ]
    if all(part is not None for part in identity):
        return content_hash("fit", *identity)[:16]
    return hashlib.sha256(data).hexdigest()[:16]


def _start_time(file_id: dict[int, Any], session: dict[int, Any], samples: list[Sample]) -> float:
    """Session start, preferring what the device recorded over what we can infer."""
    for stamp in (file_id.get(FILE_ID_TIME_CREATED), session.get(SESSION_START_TIME)):
        if isinstance(stamp, int) and not isinstance(stamp, bool):
            return float(stamp + FIT_EPOCH_OFFSET)
    return samples[0].t if samples else 0.0


def parse_fit(
    data: bytes, source_file: str = "", *, gap_tolerance: float = GAP_TOLERANCE
) -> Activity:
    """Decode a FIT activity into the canonical :class:`Activity`."""
    messages = decode_messages(data)
    records = messages.get(MSG_RECORD, [])
    if not records:
        msg = "no record messages: this FIT file holds no activity data"
        raise FitError(msg)

    file_ids = messages.get(MSG_FILE_ID, [])
    file_id = file_ids[0] if file_ids else {}
    sessions = messages.get(MSG_SESSION, [])
    session = sessions[0] if sessions else {}

    samples = [sample for sample in map(_to_sample, records) if sample is not None]
    samples.sort(key=lambda sample: sample.t)

    return Activity(
        activity_id=_activity_id(file_id, data),
        sport=_sport_name(session.get(SESSION_SPORT)),
        start_time=_start_time(file_id, session, samples),
        fidelity=Fidelity.FIT,
        samples=samples,
        blind_windows=derive_blind_windows(samples, gap_tolerance=gap_tolerance),
        device=_device_name(file_id),
        source_file=source_file,
    )
