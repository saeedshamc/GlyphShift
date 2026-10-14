"""Optional CFF <-> TrueType outline conversion (intentionally lossy for hints)."""

from __future__ import annotations

import logging
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph as TTGlyph

from glyphshift.core.errors import ConversionError
from glyphshift.core.formats import Format
from glyphshift.core.wrapper import _atomic_save, resolve_output_path

logger = logging.getLogger(__name__)

HINTING_TABLES = ("fpgm", "prep", "cvt ", "gasp")


def cff_to_glyf(
    src: Path,
    dst: Path,
    *,
    max_err: float = 1.0,
    reverse_direction: bool = True,
    overwrite: bool = False,
) -> tuple[Path, list[str], float]:
    """Convert OpenType CFF outlines to TrueType glyf.

    Returns (output_path, warnings, max_error_used).
    """
    out = resolve_output_path(src, dst, Format.TTF, overwrite=overwrite)
    warnings: list[str] = [
        "CFF->TTF approximates cubic curves with quadratic segments; "
        f"max_err={max_err} em-units.",
        "CFF hinting is dropped; TrueType hinting is not generated "
        "(consider running ttfautohint externally).",
    ]

    try:
        font = TTFont(str(src), recalcTimestamp=False, recalcBBoxes=False, lazy=False)
    except Exception as exc:  # noqa: BLE001
        raise ConversionError(f"Failed to open {src}: {exc}") from exc

    try:
        if "fvar" in font:
            raise ConversionError(
                "Refusing outline conversion of a variable font. "
                "Use a wrapper conversion (e.g. to WOFF2) to keep variation tables, "
                "or pass --instance to produce a static instance first."
            )
        if "CFF " not in font and "CFF2" not in font:
            raise ConversionError(f"Source has no CFF/CFF2 table: {src}")

        glyph_order = list(font.getGlyphOrder())
        glyph_set = font.getGlyphSet()
        tt_glyphs: dict[str, TTGlyph] = {}
        actual_max_err = float(max_err)

        def _empty_glyph() -> TTGlyph:
            g = TTGlyph()
            g.numberOfContours = 0
            g.xMin = g.yMin = g.xMax = g.yMax = 0
            g.flags = []
            g.coordinates = []
            g.endPtsOfContours = []
            g.instructions = b""
            return g

        for name in glyph_order:
            tt_pen = TTGlyphPen(glyph_set)
            cu_pen = Cu2QuPen(tt_pen, max_err, reverse_direction=reverse_direction)
            try:
                glyph_set[name].draw(cu_pen)
                glyph = tt_pen.glyph()
                # Empty draws can yield an uninitialized glyph — normalize.
                if getattr(glyph, "numberOfContours", None) in (0, None) and not getattr(
                    glyph, "coordinates", None
                ):
                    glyph = _empty_glyph()
                tt_glyphs[name] = glyph
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to convert glyph %s: %s — using empty glyph", name, exc)
                tt_glyphs[name] = _empty_glyph()
                warnings.append(f"Glyph '{name}' failed Cu2Qu conversion: {exc}")

        # Build glyf + loca
        from fontTools.ttLib import newTable

        glyf = newTable("glyf")
        glyf.glyphs = dict(tt_glyphs)
        glyf.glyphOrder = list(glyph_order)
        font["glyf"] = glyf
        for name in glyph_order:
            try:
                glyf[name].recalcBounds(glyf)
            except Exception:  # noqa: BLE001
                glyf[name] = _empty_glyph()

        # Update hmtx LSB from new glyph bounds where possible.
        if "hmtx" in font:
            metrics = font["hmtx"].metrics
            for name in glyph_order:
                if name not in metrics:
                    continue
                width, _lsb = metrics[name]
                g = glyf[name]
                lsb = int(getattr(g, "xMin", 0) or 0)
                metrics[name] = (width, lsb)

        # loca is rebuilt on save from glyf
        loca = newTable("loca")
        font["loca"] = loca

        # maxp version 1.0 for TrueType — populate every required field.
        max_points = 0
        max_contours = 0
        max_composite_points = 0
        max_composite_contours = 0
        max_component_elements = 0
        max_component_depth = 0
        for name in glyph_order:
            g = glyf[name]
            n_contours = getattr(g, "numberOfContours", 0) or 0
            if n_contours > 0:
                coords = getattr(g, "coordinates", None) or []
                max_points = max(max_points, len(coords))
                max_contours = max(max_contours, n_contours)
            elif n_contours < 0:  # composite
                comps = getattr(g, "components", None) or []
                max_component_elements = max(max_component_elements, len(comps))
                max_component_depth = max(max_component_depth, 1)

        maxp = font["maxp"]
        maxp.tableVersion = 0x00010000
        maxp.numGlyphs = len(glyph_order)
        maxp.maxPoints = max_points
        maxp.maxContours = max_contours
        maxp.maxCompositePoints = max_composite_points
        maxp.maxCompositeContours = max_composite_contours
        maxp.maxZones = 2
        maxp.maxTwilightPoints = 0
        maxp.maxStorage = 0
        maxp.maxFunctionDefs = 0
        maxp.maxInstructionDefs = 0
        maxp.maxStackElements = 0
        maxp.maxSizeOfInstructions = 0
        maxp.maxComponentElements = max_component_elements
        maxp.maxComponentDepth = max_component_depth

        # post format 2 preserves glyph names
        if "post" in font:
            post = font["post"]
            post.formatType = 2.0
            post.extraNames = []
            post.mapping = {}
        else:
            post = newTable("post")
            post.formatType = 2.0
            post.italicAngle = 0
            post.underlinePosition = -100
            post.underlineThickness = 50
            post.isFixedPitch = 0
            post.minMemType42 = 0
            post.maxMemType42 = 0
            post.minMemType1 = 0
            post.maxMemType1 = 0
            font["post"] = post

        # Remove CFF tables
        for tag in ("CFF ", "CFF2"):
            if tag in font:
                del font[tag]

        font.sfntVersion = "\x00\x01\x00\x00"
        if "head" in font:
            font["head"].glyphDataFormat = 0

        font.flavor = None
        try:
            _atomic_save(font, out)
        except Exception as exc:  # noqa: BLE001
            raise ConversionError(f"Failed to save TTF to {out}: {exc}") from exc
    finally:
        font.close()

    logger.info("Converted CFF->glyf %s -> %s", src, out)
    return out, warnings, actual_max_err


def glyf_to_cff(
    src: Path,
    dst: Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, list[str]]:
    """Convert TrueType glyf outlines to OpenType CFF.

    Quadratic->cubic is geometrically exact; TrueType hinting is dropped.
    """
    out = resolve_output_path(src, dst, Format.OTF, overwrite=overwrite)
    warnings: list[str] = [
        "TTF->OTF converts quadratic curves to cubics (geometrically exact).",
        "TrueType hinting/instructions (fpgm, prep, cvt, glyph programs) are dropped.",
    ]

    try:
        font = TTFont(str(src), recalcTimestamp=False, recalcBBoxes=False, lazy=False)
    except Exception as exc:  # noqa: BLE001
        raise ConversionError(f"Failed to open {src}: {exc}") from exc

    try:
        if "fvar" in font:
            raise ConversionError(
                "Refusing outline conversion of a variable font. "
                "Use a wrapper conversion to keep variation tables, "
                "or pass --instance to produce a static instance first."
            )
        if "glyf" not in font:
            raise ConversionError(f"Source has no glyf table: {src}")

        glyph_order = list(font.getGlyphOrder())
        glyph_set = font.getGlyphSet()

        # Advance widths from hmtx
        hmtx = font["hmtx"].metrics
        advance_widths = {n: hmtx[n][0] if n in hmtx else 0 for n in glyph_order}

        charstrings = {}
        for name in glyph_order:
            width = advance_widths.get(name, 0)
            pen = T2CharStringPen(width, glyphSet=glyph_set)
            try:
                glyph_set[name].draw(pen)
                charstrings[name] = pen.getCharString()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to convert glyph %s: %s", name, exc)
                empty = T2CharStringPen(width, glyphSet=glyph_set)
                charstrings[name] = empty.getCharString()
                warnings.append(f"Glyph '{name}' failed T2 conversion: {exc}")

        # Family / PS name for CFF header
        ps_name = "ConvertedFont"
        family = "ConvertedFont"
        if "name" in font:
            for nid, attr in ((6, "ps_name"), (1, "family")):
                for rec in font["name"].names:
                    if rec.nameID == nid:
                        try:
                            val = rec.toUnicode()
                            if attr == "ps_name":
                                ps_name = val
                            else:
                                family = val
                            break
                        except Exception:  # noqa: BLE001
                            continue

        # Build a CFF table via FontBuilder, then inject into the original font
        # so GSUB/GPOS/cmap/name/etc. are preserved untouched.
        builder = FontBuilder(font["head"].unitsPerEm, isTTF=False)
        builder.setupGlyphOrder(glyph_order)
        builder.setupCharacterMap({})  # placeholder; we keep original cmap
        metrics = {}
        for n in glyph_order:
            w, lsb = hmtx.get(n, (0, 0))
            metrics[n] = (w, lsb)
        builder.setupHorizontalMetrics(metrics)
        builder.setupHorizontalHeader(
            ascent=font["hhea"].ascent if "hhea" in font else 800,
            descent=font["hhea"].descent if "hhea" in font else -200,
        )
        builder.setupNameTable({"familyName": family, "styleName": "Regular", "psName": ps_name})
        builder.setupCFF(
            ps_name,
            {"FullName": ps_name, "FamilyName": family},
            charstrings,
            {},
        )

        cff_table = builder.font["CFF "]
        font["CFF "] = cff_table

        # Remove TrueType outline + hinting tables
        for tag in ("glyf", "loca", *HINTING_TABLES):
            if tag in font:
                del font[tag]

        # maxp version 0.5 for CFF
        maxp = font["maxp"]
        maxp.tableVersion = 0x00005000
        maxp.numGlyphs = len(glyph_order)

        if "post" in font:
            font["post"].formatType = 3.0

        font.sfntVersion = "OTTO"
        font.flavor = None

        try:
            _atomic_save(font, out)
        except Exception as exc:  # noqa: BLE001
            raise ConversionError(f"Failed to save OTF to {out}: {exc}") from exc
    finally:
        font.close()

    logger.info("Converted glyf->CFF %s -> %s", src, out)
    return out, warnings


def instantiate_variable(
    src: Path,
    dst: Path,
    instance_spec: str,
    *,
    overwrite: bool = False,
    target: Format = Format.TTF,
) -> tuple[Path, list[str]]:
    """Produce a static instance from a variable font (intentionally lossy)."""
    from fontTools.varLib import instancer

    out = resolve_output_path(src, dst, target, overwrite=overwrite)
    warnings = [
        f"Instancing variable font with '{instance_spec}' — variation axes are collapsed; "
        "this is intentionally lossy."
    ]
    axis_limits: dict[str, float] = {}
    for part in instance_spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ConversionError(
                f"Invalid instance spec '{part}'; expected tag=value (e.g. wght=400)"
            )
        tag, val = part.split("=", 1)
        axis_limits[tag.strip()] = float(val.strip())

    try:
        font = TTFont(str(src), recalcTimestamp=False, recalcBBoxes=False, lazy=False)
    except Exception as exc:  # noqa: BLE001
        raise ConversionError(f"Failed to open {src}: {exc}") from exc

    try:
        if "fvar" not in font:
            raise ConversionError(f"Not a variable font (no fvar): {src}")
        instantiated = instancer.instantiateVariableFont(font, axis_limits, inplace=False)
        from glyphshift.core.wrapper import _FLAVOR_MAP

        instantiated.flavor = _FLAVOR_MAP.get(target)
        _atomic_save(instantiated, out)
    except ConversionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConversionError(f"Instancing failed: {exc}") from exc
    finally:
        font.close()

    return out, warnings
