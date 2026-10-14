"""Core conversion library. CLI and GUI must only call these public APIs."""

from __future__ import annotations

from glyphshift.core.converter import convert_file, convert_many
from glyphshift.core.formats import Format, OutlineType, detect_format
from glyphshift.core.info import FontInfo, inspect_font
from glyphshift.core.models import ConversionOptions, ConversionResult, Issue, VerifyReport
from glyphshift.core.verify import verify

__all__ = [
    "ConversionOptions",
    "ConversionResult",
    "FontInfo",
    "Format",
    "Issue",
    "OutlineType",
    "VerifyReport",
    "convert_file",
    "convert_many",
    "detect_format",
    "inspect_font",
    "verify",
]
