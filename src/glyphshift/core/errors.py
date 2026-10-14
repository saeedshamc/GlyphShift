"""Custom exception hierarchy for GlyphShift."""

from __future__ import annotations


class GlyphShiftError(Exception):
    """Base class for all GlyphShift errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class UnsupportedFormatError(GlyphShiftError):
    """Raised when the input font format is not supported."""


class CorruptFontError(GlyphShiftError):
    """Raised when a font file is truncated, corrupt, or unreadable."""


class ConversionError(GlyphShiftError):
    """Raised when a conversion step fails."""


class VerificationError(GlyphShiftError):
    """Raised when post-conversion verification fails in strict mode."""

    def __init__(self, message: str, report: object | None = None) -> None:
        super().__init__(message)
        self.report = report


class OutputExistsError(GlyphShiftError):
    """Raised when the output path already exists and overwrite is disabled."""
