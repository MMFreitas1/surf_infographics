"""Helpers shared by the XML parsers.

GPX and TCX both bury their content under namespaces that vary by exporter and schema
version, so everything here matches on *local* names. That keeps one Garmin namespace
revision from silently producing an empty activity.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from xml.etree.ElementTree import Element


def local_name(tag: str) -> str:
    """The tag without its ``{namespace}`` prefix."""
    return tag.rsplit("}", 1)[-1]


def iter_local(element: Element, name: str) -> Iterator[Element]:
    """Every descendant whose local name matches, at any depth and any namespace."""
    for child in element.iter():
        if local_name(child.tag) == name:
            yield child


def first_local(element: Element, name: str) -> Element | None:
    """The first matching descendant, or None."""
    return next(iter_local(element, name), None)


def parse_iso_time(text: str | None) -> float | None:
    """Parse an ISO 8601 timestamp into Unix seconds."""
    if not text:
        return None
    cleaned = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).timestamp()
    except ValueError:
        return None


def float_of(element: Element | None) -> float | None:
    """Element text as a float, or None when absent or unparsable."""
    if element is None or element.text is None:
        return None
    try:
        return float(element.text.strip())
    except ValueError:
        return None


def int_of(element: Element | None) -> int | None:
    """Element text as an int, tolerating a decimal point."""
    value = float_of(element)
    return None if value is None else int(value)


def text_of(element: Element | None) -> str:
    """Element text, stripped, or an empty string."""
    if element is None or element.text is None:
        return ""
    return element.text.strip()
