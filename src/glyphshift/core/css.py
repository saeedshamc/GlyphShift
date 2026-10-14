"""Generate @font-face CSS snippets (with optional unicode-range)."""

from __future__ import annotations

from pathlib import Path

from glyphshift.core.info import inspect_font

# Common unicode-range presets for web fonts.
UNICODE_RANGE_PRESETS: dict[str, str] = {
    "latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F",
    "arabic": "U+0600-06FF, U+200C-200D, U+25CC, U+FB50-FDFF, U+FE70-FEFF",
    "persian": "U+0600-06FF, U+200C-200D, U+06F0-06F9, U+FB50-FDFF, U+FE70-FEFF",
}


def _format_name(path: Path) -> str:
    try:
        info = inspect_font(path)
        if info.family:
            return info.family
    except Exception:
        pass
    return path.stem


def _css_format(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    mapping = {
        "woff2": "woff2",
        "woff": "woff",
        "ttf": "truetype",
        "otf": "opentype",
    }
    return mapping.get(ext, ext or "truetype")


def suggest_unicode_ranges(path: Path | str) -> list[str]:
    """Suggest unicode-range preset names based on font coverage."""
    info = inspect_font(path)
    suggested: list[str] = []
    if info.has_arabic or info.has_persian_digits or info.has_zwnj:
        suggested.append("persian")
        suggested.append("arabic")
    # Always offer latin as optional companion for mixed pages.
    suggested.append("latin")
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s in suggested:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def font_face_css(
    path: Path | str,
    *,
    family: str | None = None,
    url: str | None = None,
    unicode_range: str | None = None,
    unicode_range_preset: str | None = None,
    font_display: str = "swap",
    font_weight: str = "normal",
    font_style: str = "normal",
) -> str:
    """Build a single ``@font-face`` rule."""
    path = Path(path)
    fam = family or _format_name(path)
    src_url = url or path.name
    fmt = _css_format(path)

    ur = unicode_range
    if ur is None and unicode_range_preset:
        key = unicode_range_preset.lower()
        if key not in UNICODE_RANGE_PRESETS:
            raise ValueError(
                f"Unknown unicode-range preset '{unicode_range_preset}'. "
                f"Known: {', '.join(UNICODE_RANGE_PRESETS)}"
            )
        ur = UNICODE_RANGE_PRESETS[key]

    lines = [
        "@font-face {",
        f"  font-family: '{fam}';",
        f"  src: url('{src_url}') format('{fmt}');",
        f"  font-weight: {font_weight};",
        f"  font-style: {font_style};",
        f"  font-display: {font_display};",
    ]
    if ur:
        lines.append(f"  unicode-range: {ur};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def font_face_bundle(
    path: Path | str,
    *,
    presets: list[str] | None = None,
    url: str | None = None,
) -> str:
    """Multiple @font-face blocks for suggested or given presets."""
    path = Path(path)
    use = presets or suggest_unicode_ranges(path)
    blocks = [
        font_face_css(path, url=url, unicode_range_preset=p)
        for p in use
        if p in UNICODE_RANGE_PRESETS
    ]
    return "\n".join(blocks)
