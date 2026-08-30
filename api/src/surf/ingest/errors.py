"""Failures raised while reading a source file."""

from __future__ import annotations


class IngestError(ValueError):
    """A source file could not be read into a canonical Activity."""


class UnsupportedFormatError(IngestError):
    """The bytes are not a format we parse."""
