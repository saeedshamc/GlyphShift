"""Magic-byte format detection and outline-type inspection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from glyphshift.core.errors import CorruptFontError, UnsupportedFormatError

logger = logging.getLogger(__name__)

# Note: deep inspection imports fontTools lazily inside helpers to keep
# module import light and to allow magic-byte-only detection.

# First-4-byte signatures
_SIG_TRUETYPE = b"\x00\x01\x00\x00"
_SIG_TRUE = b"true"
_SIG_TYP1 = b"typ1"
_SIG_OTTO = b"OTTO"
_SIG_WOFF = b"wOFF"
_SIG_WOFF2 = b"wOF2"
_SIG_TTCF = b"ttcf"


class Format(str, Enum):
    """Supported container / sfnt formats."""

    TTF = "ttf"
    OTF = "otf"
    WOFF = "woff"
    WOFF2 = "woff2"
    TTC = "ttc"
    OTC = "otc"

    @property
    def extension(self) -> str:
        return f".{self.value}"

    @classmethod
    def from_string(cls, value: str) -> Format:
        key = value.lower().lstrip(".")
        try:
            return cls(key)
        except ValueError as exc:
            raise UnsupportedFormatError(
                f"Unknown format '{value}'. Supported: ttf, otf, woff, woff2"
            ) from exc


class OutlineType(str, Enum):
    """Glyph outline technology inside an sfnt font."""

    GLYF = "glyf"
    CFF = "cff"
    CFF2 = "cff2"
    UNKNOWN = "unknown"
    NONE = "none"  # collections / undecided wrappers


@dataclass(frozen=True)
class DetectedFont:
    """Result of inspecting a font file's magic bytes and tables."""

    format: Format
    outline: OutlineType
    is_variable: bool
    is_collection: bool
    extension_mismatch: bool
    warnings: tuple[str, ...] = ()


def _extension_to_format(path: Path) -> Format | None:
    ext = path.suffix.lower().lstrip(".")
    mapping = {
        "ttf": Format.TTF,
        "otf": Format.OTF,
        "woff": Format.WOFF,
        "woff2": Format.WOFF2,
        "ttc": Format.TTC,
        "otc": Format.OTC,
    }
    return mapping.get(ext)


def _read_magic(path: Path) -> bytes:
    try:
        with path.open("rb") as fh:
            data = fh.read(4)
    except OSError as exc:
        raise CorruptFontError(f"Cannot read font file: {path}") from exc
    if len(data) < 4:
        raise CorruptFontError(f"File too short to be a font (truncated?): {path}")
    return data


def _outline_from_tables(table_tags: set[str]) -> OutlineType:
    if "CFF2" in table_tags:
        return OutlineType.CFF2
    if "CFF " in table_tags:
        return OutlineType.CFF
    if "glyf" in table_tags:
        return OutlineType.GLYF
    return OutlineType.UNKNOWN


def _inspect_sfnt_tables(path: Path) -> tuple[OutlineType, bool]:
    """Load sfnt (including WOFF/WOFF2) and return (outline, is_variable)."""
    from fontTools.ttLib import TTFont

    try:
        font = TTFont(str(path), recalcTimestamp=False, recalcBBoxes=False, lazy=True)
    except Exception as exc:  # noqa: BLE001 — wrap into CorruptFontError
        raise CorruptFontError(f"Failed to parse font tables in {path}: {exc}") from exc
    try:
        tags = set(font.keys())
        outline = _outline_from_tables(tags)
        is_variable = "fvar" in tags
        return outline, is_variable
    finally:
        font.close()


def detect_format(path: Path | str, *, deep: bool = True) -> DetectedFont:
    """Detect font format from magic bytes (not the file extension).

    Parameters
    ----------
    path:
        Path to the font file.
    deep:
        If True, also open the font to detect outline type and variable axes.
    """
    path = Path(path)
    if not path.is_file():
        raise CorruptFontError(f"Not a file: {path}")

    magic = _read_magic(path)
    warnings: list[str] = []
    is_collection = False
    outline = OutlineType.NONE
    is_variable = False

    if magic == _SIG_TTCF:
        is_collection = True
        # Distinguish TTC vs OTC by peeking at first face if deep.
        fmt = Format.TTC
        if deep:
            try:
                from fontTools.ttLib import TTCollection

                coll = TTCollection(str(path))
                try:
                    if coll.fonts:
                        tags = set(coll.fonts[0].keys())
                        outline = _outline_from_tables(tags)
                        is_variable = "fvar" in tags
                        if outline in (OutlineType.CFF, OutlineType.CFF2):
                            fmt = Format.OTC
                finally:
                    coll.close()
            except Exception as exc:  # noqa: BLE001
                raise CorruptFontError(f"Corrupt font collection: {path}: {exc}") from exc
        detected = DetectedFont(
            format=fmt,
            outline=outline,
            is_variable=is_variable,
            is_collection=True,
            extension_mismatch=False,
            warnings=tuple(warnings),
        )
    elif magic == _SIG_WOFF:
        fmt = Format.WOFF
        if deep:
            outline, is_variable = _inspect_sfnt_tables(path)
        detected = DetectedFont(
            format=fmt,
            outline=outline,
            is_variable=is_variable,
            is_collection=False,
            extension_mismatch=False,
            warnings=tuple(warnings),
        )
    elif magic == _SIG_WOFF2:
        fmt = Format.WOFF2
        if deep:
            outline, is_variable = _inspect_sfnt_tables(path)
        detected = DetectedFont(
            format=fmt,
            outline=outline,
            is_variable=is_variable,
            is_collection=False,
            extension_mismatch=False,
            warnings=tuple(warnings),
        )
    elif magic == _SIG_OTTO:
        fmt = Format.OTF
        if deep:
            outline, is_variable = _inspect_sfnt_tables(path)
        else:
            outline = OutlineType.CFF
        detected = DetectedFont(
            format=fmt,
            outline=outline,
            is_variable=is_variable,
            is_collection=False,
            extension_mismatch=False,
            warnings=tuple(warnings),
        )
    elif magic in (_SIG_TRUETYPE, _SIG_TRUE, _SIG_TYP1):
        fmt = Format.TTF
        if deep:
            outline, is_variable = _inspect_sfnt_tables(path)
            # Some "TTF" files are actually CFF with wrong sfntVersion — rare.
            if outline in (OutlineType.CFF, OutlineType.CFF2):
                warnings.append(
                    "sfntVersion looks TrueType but CFF/CFF2 table present; treating as OTF."
                )
                fmt = Format.OTF
        else:
            outline = OutlineType.GLYF
        detected = DetectedFont(
            format=fmt,
            outline=outline,
            is_variable=is_variable,
            is_collection=False,
            extension_mismatch=False,
            warnings=tuple(warnings),
        )
    else:
        raise UnsupportedFormatError(
            f"Unsupported or unknown font signature {magic!r} in {path}"
        )

    ext_fmt = _extension_to_format(path)
    mismatch = False
    if ext_fmt is not None and not is_collection:
        # WOFF/WOFF2 vs TTF/OTF are clear mismatches; TTF vs OTF also matters.
        if ext_fmt != detected.format:
            # Allow .otf extension on CFF and .ttf on glyf only — already handled.
            # Collection extensions handled separately.
            if not (
                detected.format in (Format.TTC, Format.OTC)
                and ext_fmt in (Format.TTC, Format.OTC)
            ):
                mismatch = True
                msg = (
                    f"Extension '.{path.suffix.lstrip('.')}' does not match "
                    f"detected format '{detected.format.value}'"
                )
                warnings.append(msg)
                logger.warning("%s: %s", path, msg)

    return DetectedFont(
        format=detected.format,
        outline=detected.outline if deep else detected.outline,
        is_variable=detected.is_variable,
        is_collection=detected.is_collection,
        extension_mismatch=mismatch,
        warnings=tuple(warnings),
    )


def is_wrapper_only(src: Format, dst: Format) -> bool:
    """True when conversion only changes the container (fully lossless)."""
    sfnt = {Format.TTF, Format.OTF}
    web = {Format.WOFF, Format.WOFF2}
    # Same outline family, only container changes.
    if src in sfnt and dst in web:
        return True
    if src in web and dst in sfnt:
        return True
    if src in web and dst in web:
        return True
    if src in sfnt and dst in sfnt:
        # TTF<->OTF requires outline conversion — NOT wrapper-only.
        return src == dst
    return False


def needs_outline_conversion(src_outline: OutlineType, dst: Format) -> bool:
    """True when the target format requires a different outline technology."""
    if dst == Format.TTF:
        return src_outline in (OutlineType.CFF, OutlineType.CFF2)
    if dst == Format.OTF:
        return src_outline == OutlineType.GLYF
    # WOFF/WOFF2 keep whatever outline the source has.
    return False


def conversion_is_lossless(
    src_format: Format,
    src_outline: OutlineType,
    dst: Format,
) -> bool:
    """Whether the requested conversion path is fully lossless."""
    if needs_outline_conversion(src_outline, dst):
        return False
    # Instance extraction is lossy — handled separately via options.
    if src_format == dst and not needs_outline_conversion(src_outline, dst):
        return True
    return is_wrapper_only(src_format, dst) or (
        src_format in (Format.WOFF, Format.WOFF2)
        and dst in (Format.WOFF, Format.WOFF2, Format.TTF, Format.OTF)
        and not needs_outline_conversion(src_outline, dst)
    )
