"""Core conversion library. CLI and GUI must only call these public APIs."""

from __future__ import annotations

from glyphshift.core.converter import convert_file, convert_many
from glyphshift.core.css import font_face_bundle, font_face_css
from glyphshift.core.formats import Format, OutlineType, detect_format
from glyphshift.core.info import FontInfo, inspect_font
from glyphshift.core.models import ConversionOptions, ConversionResult, Issue, VerifyReport
from glyphshift.core.profiles import Profile, apply_profile, list_profiles
from glyphshift.core.report import build_html_report, write_html_report
from glyphshift.core.verify import verify

__all__ = [
    "ConversionOptions",
    "ConversionResult",
    "FontInfo",
    "Format",
    "Issue",
    "OutlineType",
    "Profile",
    "VerifyReport",
    "apply_profile",
    "build_html_report",
    "convert_file",
    "convert_many",
    "detect_format",
    "font_face_bundle",
    "font_face_css",
    "inspect_font",
    "list_profiles",
    "verify",
    "write_html_report",
]
