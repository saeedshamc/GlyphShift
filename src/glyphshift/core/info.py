"""Font metadata inspection."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont

from glyphshift.core.errors import CorruptFontError
from glyphshift.core.formats import Format, OutlineType, detect_format

logger = logging.getLogger(__name__)

# OS/2 ulUnicodeRange bit -> rough script/block name (subset we care about).
_UNICODE_RANGE_BITS = {
    0: "Basic Latin",
    1: "Latin-1 Supplement",
    2: "Latin Extended-A",
    13: "Arabic",
    58: "Arabic Presentation Forms-A",
    67: "Arabic Presentation Forms-B",
    11: "Basic Cyrillic",
    28: "Hangul",
    59: "CJK Compatibility",
}


@dataclass
class FontInfo:
    """Human-friendly summary of a font file."""

    path: str
    format: str
    outline: str
    flavor: str | None
    family: str | None = None
    subfamily: str | None = None
    full_name: str | None = None
    postscript_name: str | None = None
    version: str | None = None
    designer: str | None = None
    license: str | None = None
    copyright: str | None = None
    glyph_count: int = 0
    units_per_em: int = 0
    is_variable: bool = False
    axes: list[dict[str, Any]] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    mapped_codepoints: int = 0
    unicode_blocks: list[str] = field(default_factory=list)
    has_arabic: bool = False
    has_persian_digits: bool = False
    has_arabic_indic_digits: bool = False
    has_zwnj: bool = False
    has_gsub: bool = False
    has_gpos: bool = False
    is_collection: bool = False
    collection_faces: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _name_record(font: TTFont, name_id: int) -> str | None:
    if "name" not in font:
        return None
    name = font["name"]
    # Prefer Windows Unicode English, then any.
    for record in name.names:
        if record.nameID != name_id:
            continue
        if record.platformID == 3 and record.langID == 0x409:
            try:
                return record.toUnicode()
            except Exception:  # noqa: BLE001
                continue
    for record in name.names:
        if record.nameID == name_id:
            try:
                return record.toUnicode()
            except Exception:  # noqa: BLE001
                continue
    return None


def _scripts_from_layout(font: TTFont) -> list[str]:
    scripts: set[str] = set()
    for tag in ("GSUB", "GPOS"):
        if tag not in font:
            continue
        table = font[tag].table
        if not hasattr(table, "ScriptList") or table.ScriptList is None:
            continue
        for rec in table.ScriptList.ScriptRecord:
            scripts.add(rec.ScriptTag)
    return sorted(scripts)


def _os2_unicode_blocks(font: TTFont) -> list[str]:
    if "OS/2" not in font:
        return []
    os2 = font["OS/2"]
    bits = getattr(os2, "ulUnicodeRange1", 0) or 0
    bits2 = getattr(os2, "ulUnicodeRange2", 0) or 0
    bits3 = getattr(os2, "ulUnicodeRange3", 0) or 0
    bits4 = getattr(os2, "ulUnicodeRange4", 0) or 0
    all_bits = [bits, bits2, bits3, bits4]
    found: list[str] = []
    for bit_index, label in _UNICODE_RANGE_BITS.items():
        word = bit_index // 32
        offset = bit_index % 32
        if word < len(all_bits) and (all_bits[word] & (1 << offset)):
            found.append(label)
    return found


def _best_cmap(font: TTFont) -> dict[int, str]:
    if "cmap" not in font:
        return {}
    cmap = font.getBestCmap() or {}
    return dict(cmap)


def inspect_font(path: Path | str, *, face_index: int | None = None) -> FontInfo:
    """Inspect a font file and return structured metadata."""
    path = Path(path)
    detected = detect_format(path, deep=True)
    warnings = list(detected.warnings)

    if detected.is_collection:
        from fontTools.ttLib import TTCollection

        try:
            coll = TTCollection(str(path))
        except Exception as exc:  # noqa: BLE001
            raise CorruptFontError(f"Cannot open collection {path}: {exc}") from exc
        try:
            n = len(coll.fonts)
            idx = 0 if face_index is None else face_index
            if idx < 0 or idx >= n:
                raise CorruptFontError(
                    f"Collection face index {idx} out of range (0..{n - 1})"
                )
            # Work on a copy saved to memory is heavy; use the face directly.
            font = coll.fonts[idx]
            info = _fill_info(path, font, detected, collection_faces=n)
            info.is_collection = True
            info.warnings = warnings
            return info
        finally:
            coll.close()

    try:
        font = TTFont(str(path), recalcTimestamp=False, recalcBBoxes=False, lazy=True)
    except Exception as exc:  # noqa: BLE001
        raise CorruptFontError(f"Cannot open font {path}: {exc}") from exc
    try:
        info = _fill_info(path, font, detected)
        info.warnings = warnings
        return info
    finally:
        font.close()


def _fill_info(
    path: Path,
    font: TTFont,
    detected: Any,
    *,
    collection_faces: int = 0,
) -> FontInfo:
    cmap = _best_cmap(font)
    cps = set(cmap.keys())

    axes: list[dict[str, Any]] = []
    if "fvar" in font:
        for axis in font["fvar"].axes:
            axes.append(
                {
                    "tag": axis.axisTag,
                    "min": axis.minValue,
                    "default": axis.defaultValue,
                    "max": axis.maxValue,
                }
            )

    outline = detected.outline
    if isinstance(outline, OutlineType):
        outline_s = outline.value
    else:
        outline_s = str(outline)

    fmt = detected.format
    fmt_s = fmt.value if isinstance(fmt, Format) else str(fmt)

    flavor = getattr(font, "flavor", None)

    return FontInfo(
        path=str(path),
        format=fmt_s,
        outline=outline_s,
        flavor=flavor,
        family=_name_record(font, 1),
        subfamily=_name_record(font, 2),
        full_name=_name_record(font, 4),
        postscript_name=_name_record(font, 6),
        version=_name_record(font, 5),
        designer=_name_record(font, 9),
        license=_name_record(font, 13) or _name_record(font, 14),
        copyright=_name_record(font, 0),
        glyph_count=font["maxp"].numGlyphs if "maxp" in font else len(font.getGlyphOrder()),
        units_per_em=font["head"].unitsPerEm if "head" in font else 0,
        is_variable=bool(axes) or detected.is_variable,
        axes=axes,
        scripts=_scripts_from_layout(font),
        mapped_codepoints=len(cps),
        unicode_blocks=_os2_unicode_blocks(font),
        has_arabic=any(0x0600 <= cp <= 0x06FF for cp in cps),
        has_persian_digits=any(0x06F0 <= cp <= 0x06F9 for cp in cps),
        has_arabic_indic_digits=any(0x0660 <= cp <= 0x0669 for cp in cps),
        has_zwnj=0x200C in cps,
        has_gsub="GSUB" in font,
        has_gpos="GPOS" in font,
        is_collection=detected.is_collection,
        collection_faces=collection_faces,
    )
