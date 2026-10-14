"""Post-conversion verification — the 'no glyph loss' guarantee."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from glyphshift.core.models import Issue, Severity, VerifyMode, VerifyReport

logger = logging.getLogger(__name__)

# Tables intentionally removed / replaced during outline conversion.
OUTLINE_REMOVED_TTF_TO_OTF = frozenset({"glyf", "loca", "fpgm", "prep", "cvt ", "gasp"})
OUTLINE_REMOVED_OTF_TO_TTF = frozenset({"CFF ", "CFF2"})
OUTLINE_ADDED_TTF_TO_OTF = frozenset({"CFF "})
OUTLINE_ADDED_OTF_TO_TTF = frozenset({"glyf", "loca"})

LAYOUT_TABLES = ("GSUB", "GPOS", "GDEF", "BASE", "JSTF", "MATH")
VARIATION_TABLES = (
    "fvar",
    "gvar",
    "avar",
    "STAT",
    "HVAR",
    "VVAR",
    "MVAR",
    "CFF2",
    "cvar",
)

# Code points that must survive for Persian/Arabic reliability.
CRITICAL_CPS = (
    0x200C,  # ZWNJ
    0x200D,  # ZWJ
)
ARABIC_RANGE = range(0x0600, 0x0700)
PRESENTATION_A = range(0xFB50, 0xFE00)
PRESENTATION_B = range(0xFE70, 0xFF00)

ARABIC_FEATURES = (
    "init",
    "medi",
    "fina",
    "isol",
    "rlig",
    "liga",
    "calt",
    "mark",
    "mkmk",
    "kern",
    "curs",
)


def _open(path: Path) -> TTFont:
    return TTFont(str(path), recalcTimestamp=False, recalcBBoxes=False, lazy=False)


def _issue(severity: Severity, code: str, message: str) -> Issue:
    return Issue(severity=severity, code=code, message=message)


def _table_xml(font: TTFont, tag: str) -> str:
    """Serialize a single table to XML for semantic comparison.

    Strips the outer ``ttFont`` wrapper attributes (sfntVersion etc.) so that
    outline conversions, which legitimately change sfntVersion, do not create
    false positives when comparing table content.
    """
    buf = io.StringIO()
    font.saveXML(buf, tables=[tag])
    text = buf.getvalue()
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<?xml"):
            continue
        if stripped.startswith("<ttFont") or stripped.startswith("</ttFont>"):
            continue
        if not stripped:
            continue
        cleaned.append(line.rstrip())
    return "\n".join(cleaned)


def _cmap_subtables(font: TTFont) -> dict[tuple[int, int], dict[int, str]]:
    """Return {(platformID, platEncID): {codepoint: glyphName}} for all subtables."""
    result: dict[tuple[int, int], dict[int, str]] = {}
    if "cmap" not in font:
        return result
    for table in font["cmap"].tables:
        key = (table.platformID, table.platEncID)
        # Prefer the richer subtable if duplicates exist.
        mapping = dict(table.cmap) if table.cmap else {}
        if key not in result or len(mapping) > len(result[key]):
            result[key] = mapping
    return result


def _all_mapped_cps(font: TTFont) -> set[int]:
    cps: set[int] = set()
    for mapping in _cmap_subtables(font).values():
        cps.update(mapping.keys())
    return cps


def _glyph_outline_record(font: TTFont, name: str) -> list[Any] | None:
    """Record drawing commands for a glyph; None if not drawable."""
    glyph_set = font.getGlyphSet()
    if name not in glyph_set:
        return None
    pen = RecordingPen()
    try:
        glyph_set[name].draw(pen)
    except Exception:
        return None
    return pen.value


def _bbox_of_record(record: list[Any] | None) -> tuple[float, float, float, float] | None:
    if not record:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for op, args in record:
        if op in ("moveTo", "lineTo"):
            xs.append(args[0][0])
            ys.append(args[0][1])
        elif op == "qCurveTo" or op == "curveTo":
            for pt in args:
                if isinstance(pt, tuple):
                    xs.append(pt[0])
                    ys.append(pt[1])
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _feature_tags(font: TTFont, table_tag: str) -> set[str]:
    tags: set[str] = set()
    if table_tag not in font:
        return tags
    table = font[table_tag].table
    if not hasattr(table, "FeatureList") or table.FeatureList is None:
        return tags
    for rec in table.FeatureList.FeatureRecord:
        tags.add(rec.FeatureTag)
    return tags


def _script_tags(font: TTFont, table_tag: str) -> set[str]:
    tags: set[str] = set()
    if table_tag not in font:
        return tags
    table = font[table_tag].table
    if not hasattr(table, "ScriptList") or table.ScriptList is None:
        return tags
    for rec in table.ScriptList.ScriptRecord:
        tags.add(rec.ScriptTag)
    return tags


def verify(
    src: Path | str,
    dst: Path | str,
    mode: VerifyMode | str = VerifyMode.STRICT,
    *,
    max_err: float = 1.0,
    outline_converted: bool = False,
    direction: str | None = None,
) -> VerifyReport:
    """Compare source and converted fonts semantically.

    Parameters
    ----------
    src, dst:
        Paths to the original and converted fonts.
    mode:
        ``strict`` (wrapper) or ``tolerant`` (outline conversion).
    max_err:
        Geometry tolerance in em-units for outline-conversion mode.
    outline_converted:
        True when CFF<->glyf conversion was performed.
    direction:
        ``"cff_to_glyf"`` or ``"glyf_to_cff"`` when outline_converted.
    """
    if isinstance(mode, str):
        mode = VerifyMode(mode)

    src_path = Path(src)
    dst_path = Path(dst)
    issues: list[Issue] = []
    details: dict[str, Any] = {}

    try:
        src_font = _open(src_path)
    except Exception as exc:
        return VerifyReport(
            passed=False,
            mode=mode,
            issues=[_issue(Severity.ERROR, "src_unreadable", str(exc))],
        )
    try:
        dst_font = _open(dst_path)
    except Exception as exc:
        src_font.close()
        return VerifyReport(
            passed=False,
            mode=mode,
            issues=[_issue(Severity.ERROR, "dst_unreadable", str(exc))],
        )

    try:
        # --- 1. Glyph count & order ---
        src_order = list(src_font.getGlyphOrder())
        dst_order = list(dst_font.getGlyphOrder())
        details["glyph_count_src"] = len(src_order)
        details["glyph_count_dst"] = len(dst_order)

        if len(src_order) != len(dst_order):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "glyph_count",
                    f"Glyph count changed: {len(src_order)} -> {len(dst_order)}",
                )
            )
        if src_order != dst_order:
            issues.append(
                _issue(
                    Severity.ERROR,
                    "glyph_order",
                    "Glyph order or names differ between source and output",
                )
            )

        # --- 2. cmap equality ---
        src_cmaps = _cmap_subtables(src_font)
        dst_cmaps = _cmap_subtables(dst_font)
        if set(src_cmaps.keys()) != set(dst_cmaps.keys()):
            missing = set(src_cmaps) - set(dst_cmaps)
            added = set(dst_cmaps) - set(src_cmaps)
            issues.append(
                _issue(
                    Severity.ERROR,
                    "cmap_subtables",
                    f"cmap subtables differ; missing={missing}, added={added}",
                )
            )
        for key in set(src_cmaps) & set(dst_cmaps):
            if src_cmaps[key] != dst_cmaps[key]:
                # Find a few differing codepoints for the message.
                diffs = [
                    f"U+{cp:04X}"
                    for cp in sorted(set(src_cmaps[key]) | set(dst_cmaps[key]))
                    if src_cmaps[key].get(cp) != dst_cmaps[key].get(cp)
                ][:8]
                issues.append(
                    _issue(
                        Severity.ERROR,
                        "cmap_mapping",
                        f"cmap {key} mappings differ (e.g. {', '.join(diffs)})",
                    )
                )

        src_cps = _all_mapped_cps(src_font)
        dst_cps = _all_mapped_cps(dst_font)
        critical_present = [cp for cp in CRITICAL_CPS if cp in src_cps]
        for cp in critical_present:
            if cp not in dst_cps:
                issues.append(
                    _issue(
                        Severity.ERROR,
                        "critical_cp_missing",
                        f"Critical code point U+{cp:04X} missing from output cmap",
                    )
                )
            else:
                # Same glyph name across best mapping.
                src_name = next(
                    (m[cp] for m in src_cmaps.values() if cp in m),
                    None,
                )
                dst_name = next(
                    (m[cp] for m in dst_cmaps.values() if cp in m),
                    None,
                )
                if src_name != dst_name:
                    issues.append(
                        _issue(
                            Severity.ERROR,
                            "critical_cp_glyph",
                            f"U+{cp:04X} maps to '{src_name}' in source but '{dst_name}' in output",
                        )
                    )

        for label, rng in (
            ("arabic", ARABIC_RANGE),
            ("presentation_a", PRESENTATION_A),
            ("presentation_b", PRESENTATION_B),
        ):
            src_in = {cp for cp in src_cps if cp in rng}
            dst_in = {cp for cp in dst_cps if cp in rng}
            lost = src_in - dst_in
            if lost:
                sample = ", ".join(f"U+{c:04X}" for c in sorted(lost)[:6])
                issues.append(
                    _issue(
                        Severity.ERROR,
                        f"range_lost_{label}",
                        f"{len(lost)} code point(s) lost in {label} range (e.g. {sample})",
                    )
                )

        # --- 3. Table presence ---
        # Must use .keys() — iterating TTFont indexes tables by ordinal and breaks.
        src_tags = {t for t in src_font.keys() if not t.startswith("GlyphOrder")}  # noqa: SIM118
        dst_tags = {t for t in dst_font.keys() if not t.startswith("GlyphOrder")}  # noqa: SIM118
        expected_removed: set[str] = set()
        expected_added: set[str] = set()
        if outline_converted:
            if direction == "cff_to_glyf":
                expected_removed = set(OUTLINE_REMOVED_OTF_TO_TTF)
                expected_added = set(OUTLINE_ADDED_OTF_TO_TTF)
            elif direction == "glyf_to_cff":
                expected_removed = set(OUTLINE_REMOVED_TTF_TO_OTF)
                expected_added = set(OUTLINE_ADDED_TTF_TO_OTF)

        missing = (src_tags - expected_removed) - dst_tags
        added = (dst_tags - expected_added) - src_tags
        # Flavor tables aren't real sfnt tags.
        missing -= {"GlyphOrder"}
        if missing:
            sev = Severity.WARNING if mode == VerifyMode.TOLERANT else Severity.ERROR
            # In tolerant outline mode, missing hinting tables already expected.
            issues.append(
                _issue(sev, "tables_missing", f"Tables missing in output: {sorted(missing)}")
            )
        if added:
            issues.append(
                _issue(
                    Severity.WARNING,
                    "tables_added",
                    f"Tables added in output: {sorted(added)}",
                )
            )
        details["tables_src"] = sorted(src_tags)
        details["tables_dst"] = sorted(dst_tags)

        # --- 4. Metrics ---
        if (
            "head" in src_font
            and "head" in dst_font
            and src_font["head"].unitsPerEm != dst_font["head"].unitsPerEm
        ):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "units_per_em",
                    f"unitsPerEm {src_font['head'].unitsPerEm} -> {dst_font['head'].unitsPerEm}",
                )
            )

        if "hmtx" in src_font and "hmtx" in dst_font:
            src_h = src_font["hmtx"].metrics
            dst_h = dst_font["hmtx"].metrics
            if outline_converted:
                # Advance widths must match; LSB often changes with new bounds.
                width_diffs = [
                    g for g in src_order if g in src_h and g in dst_h and src_h[g][0] != dst_h[g][0]
                ]
                if width_diffs:
                    issues.append(
                        _issue(
                            Severity.ERROR,
                            "hmtx_width",
                            f"hmtx advance width differs for {len(width_diffs)} glyph(s) "
                            f"(e.g. {width_diffs[:5]})",
                        )
                    )
            else:
                hmtx_diffs = [
                    g for g in src_order if g in src_h and g in dst_h and src_h[g] != dst_h[g]
                ]
                if hmtx_diffs:
                    issues.append(
                        _issue(
                            Severity.ERROR,
                            "hmtx",
                            f"hmtx differs for {len(hmtx_diffs)} glyph(s) (e.g. {hmtx_diffs[:5]})",
                        )
                    )

        if "vmtx" in src_font:
            if "vmtx" not in dst_font:
                issues.append(_issue(Severity.ERROR, "vmtx_missing", "vmtx table lost"))
            else:
                src_v = src_font["vmtx"].metrics
                dst_v = dst_font["vmtx"].metrics
                if src_v != dst_v:
                    issues.append(_issue(Severity.ERROR, "vmtx", "vmtx metrics differ"))

        for tag, fields in (
            ("hhea", ("ascent", "descent", "lineGap", "advanceWidthMax")),
            (
                "OS/2",
                (
                    "usWeightClass",
                    "usWidthClass",
                    "fsSelection",
                    "sTypoAscender",
                    "sTypoDescender",
                    "sTypoLineGap",
                    "usWinAscent",
                    "usWinDescent",
                    "achVendID",
                ),
            ),
        ):
            if tag in src_font and tag in dst_font:
                for fld in fields:
                    if not hasattr(src_font[tag], fld):
                        continue
                    sv = getattr(src_font[tag], fld)
                    dv = getattr(dst_font[tag], fld)
                    if sv != dv:
                        issues.append(
                            _issue(
                                Severity.ERROR,
                                f"metric_{tag}_{fld}",
                                f"{tag}.{fld}: {sv!r} -> {dv!r}",
                            )
                        )

        # --- 5. Layout tables (semantic XML) ---
        for tag in LAYOUT_TABLES:
            if tag not in src_font:
                continue
            if tag not in dst_font:
                issues.append(_issue(Severity.ERROR, f"layout_missing_{tag}", f"{tag} table lost"))
                continue
            try:
                sx = _table_xml(src_font, tag)
                dx = _table_xml(dst_font, tag)
            except Exception as exc:
                issues.append(
                    _issue(
                        Severity.WARNING,
                        f"layout_compare_{tag}",
                        f"Could not XML-compare {tag}: {exc}",
                    )
                )
                continue
            if sx != dx:
                issues.append(
                    _issue(
                        Severity.ERROR,
                        f"layout_diff_{tag}",
                        f"{tag} table content differs after conversion",
                    )
                )

        for layout in ("GSUB", "GPOS"):
            src_scripts = _script_tags(src_font, layout)
            dst_scripts = _script_tags(dst_font, layout)
            if src_scripts and "arab" in src_scripts and "arab" not in dst_scripts:
                issues.append(
                    _issue(
                        Severity.ERROR,
                        f"script_arab_{layout}",
                        f"'arab' script missing from {layout} after conversion",
                    )
                )
            src_feats = _feature_tags(src_font, layout)
            dst_feats = _feature_tags(dst_font, layout)
            lost_feats = {f for f in ARABIC_FEATURES if f in src_feats and f not in dst_feats}
            if lost_feats:
                issues.append(
                    _issue(
                        Severity.ERROR,
                        f"features_lost_{layout}",
                        f"Features lost from {layout}: {sorted(lost_feats)}",
                    )
                )

        # --- 6. name table ---
        if "name" in src_font and "name" in dst_font:
            try:
                if _table_xml(src_font, "name") != _table_xml(dst_font, "name"):
                    issues.append(_issue(Severity.ERROR, "name_table", "name table records differ"))
            except Exception as exc:
                issues.append(
                    _issue(Severity.WARNING, "name_compare", f"name compare failed: {exc}")
                )
        elif "name" in src_font and "name" not in dst_font:
            issues.append(_issue(Severity.ERROR, "name_missing", "name table lost"))

        # --- 7. Outlines ---
        worst_glyph = None
        worst_dev = 0.0
        if not outline_converted:
            # Strict identity of outlines for every common glyph.
            for gname in src_order:
                if gname not in dst_order:
                    continue
                sr = _glyph_outline_record(src_font, gname)
                dr = _glyph_outline_record(dst_font, gname)
                if sr != dr:
                    issues.append(
                        _issue(
                            Severity.ERROR,
                            "outline_identity",
                            f"Outline of glyph '{gname}' is not identical",
                        )
                    )
                    # One sample is enough to fail; avoid flooding.
                    break
        else:
            # Tolerant geometry check: bbox delta within max_err * small factor.
            for gname in src_order:
                if gname not in dst_order:
                    continue
                sr = _glyph_outline_record(src_font, gname)
                dr = _glyph_outline_record(dst_font, gname)
                sb = _bbox_of_record(sr)
                db = _bbox_of_record(dr)
                if sb is None and db is None:
                    continue
                if sb is None or db is None:
                    issues.append(
                        _issue(
                            Severity.WARNING,
                            "outline_empty_mismatch",
                            f"Glyph '{gname}' empty on one side after outline conversion",
                        )
                    )
                    continue
                dev = max(abs(sb[i] - db[i]) for i in range(4))
                if dev > worst_dev:
                    worst_dev = dev
                    worst_glyph = gname
                # Allow some slack: cubic/quad approximation + reverse direction.
                tolerance = max(max_err * 4, 2.0)
                if dev > tolerance:
                    issues.append(
                        _issue(
                            Severity.WARNING,
                            "outline_deviation",
                            f"Glyph '{gname}' bbox deviation {dev:.2f} exceeds "
                            f"tolerance {tolerance:.2f}",
                        )
                    )
            details["worst_glyph"] = worst_glyph
            details["max_bbox_deviation"] = worst_dev

        # --- 8. Variable-font tables ---
        for tag in VARIATION_TABLES:
            if tag in src_font and tag not in expected_removed and tag not in dst_font:
                issues.append(
                    _issue(
                        Severity.ERROR,
                        f"var_missing_{tag}",
                        f"Variation table '{tag}' lost during conversion",
                    )
                )

        # Demote expected outline-conversion differences in tolerant mode.
        if mode == VerifyMode.TOLERANT and outline_converted:
            demoted: list[Issue] = []
            for iss in issues:
                if iss.code.startswith("layout_") or iss.code in {
                    "glyph_count",
                    "glyph_order",
                    "cmap_mapping",
                    "cmap_subtables",
                    "hmtx",
                    "name_table",
                }:
                    demoted.append(iss)  # keep as-is (must not change)
                elif iss.severity == Severity.ERROR and iss.code.startswith("tables_"):
                    demoted.append(Issue(Severity.WARNING, iss.code, iss.message))
                else:
                    demoted.append(iss)
            issues = demoted

    finally:
        src_font.close()
        dst_font.close()

    errors = [i for i in issues if i.severity == Severity.ERROR]
    passed = len(errors) == 0
    report = VerifyReport(passed=passed, mode=mode, issues=issues, details=details)
    logger.info(
        "Verify %s -> %s: passed=%s errors=%d warnings=%d",
        src_path,
        dst_path,
        passed,
        len(errors),
        len(report.warnings),
    )
    return report
