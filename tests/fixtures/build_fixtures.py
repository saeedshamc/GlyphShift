#!/usr/bin/env python3
"""Generate small synthetic test fonts for GlyphShift tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.psCharStrings import T2CharString
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph as TTGlyph

ROOT = Path(__file__).resolve().parent
UPM = 1000


def _box_pen_tt(pen: TTGlyphPen, x0: int, y0: int, x1: int, y1: int) -> None:
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()


def _make_glyf_glyph() -> TTGlyph:
    pen = TTGlyphPen(None)
    _box_pen_tt(pen, 50, 0, 450, 700)
    return pen.glyph()


def _make_cff_charstring(width: int = 500) -> T2CharString:
    pen = T2CharStringPen(width, None)
    pen.moveTo((50, 0))
    pen.lineTo((450, 0))
    pen.lineTo((450, 700))
    pen.lineTo((50, 700))
    pen.closePath()
    return pen.getCharString()


def build_latin_glyf(path: Path) -> None:
    glyph_order = [".notdef", "space", "A", "B", "a"]
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({0x20: "space", 0x41: "A", 0x42: "B", 0x61: "a"})
    glyphs = {n: (_make_glyf_glyph() if n != ".notdef" else TTGlyph()) for n in glyph_order}
    glyphs["space"] = TTGlyph()
    fb.setupGlyf(glyphs)
    metrics = {n: (500, 50) for n in glyph_order}
    metrics[".notdef"] = (500, 0)
    metrics["space"] = (250, 0)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": "GlyphShiftLatin",
            "styleName": "Regular",
            "uniqueFontIdentifier": "GlyphShiftLatin-Regular",
            "fullName": "GlyphShift Latin Regular",
            "version": "Version 1.000",
            "psName": "GlyphShiftLatin-Regular",
        }
    )
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.save(str(path))


def build_latin_cff(path: Path) -> None:
    glyph_order = [".notdef", "space", "A", "B", "a"]
    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({0x20: "space", 0x41: "A", 0x42: "B", 0x61: "a"})
    charstrings = {
        ".notdef": _make_cff_charstring(500),
        "space": T2CharStringPen(250, None).getCharString(),
        "A": _make_cff_charstring(500),
        "B": _make_cff_charstring(500),
        "a": _make_cff_charstring(500),
    }
    metrics = {n: (500, 50) for n in glyph_order}
    metrics[".notdef"] = (500, 0)
    metrics["space"] = (250, 0)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": "GlyphShiftLatinCFF",
            "styleName": "Regular",
            "uniqueFontIdentifier": "GlyphShiftLatinCFF-Regular",
            "fullName": "GlyphShift Latin CFF Regular",
            "version": "Version 1.000",
            "psName": "GlyphShiftLatinCFF-Regular",
        }
    )
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupCFF(
        "GlyphShiftLatinCFF-Regular",
        {"FullName": "GlyphShift Latin CFF", "FamilyName": "GlyphShiftLatinCFF"},
        charstrings,
        {},
    )
    fb.setupPost()
    fb.save(str(path))


def build_persian_glyf(path: Path) -> None:
    """Synthetic Arabic/Persian TTF with critical codepoints and GSUB features."""
    from fontTools.ttLib import newTable
    from fontTools.ttLib.tables import otTables

    glyph_order = [
        ".notdef",
        "space",
        "zwnj",
        "zwj",
        "afii57400",  # Persian digit 0 U+06F0 placeholder names
        "uni06F0",
        "uni06F1",
        "uni06F2",
        "uni06F3",
        "uni06F4",
        "uni06F5",
        "uni06F6",
        "uni06F7",
        "uni06F8",
        "uni06F9",
        "uni0660",
        "uni0661",
        "uni0627",  # alef
        "uni0628",  # beh
        "uni0628.init",
        "uni0628.medi",
        "uni0628.fina",
        "uni0644",  # lam
        "uni0644.init",
        "uniFEE0",  # presentation form sample
    ]
    cmap = {
        0x20: "space",
        0x200C: "zwnj",
        0x200D: "zwj",
        0x06F0: "uni06F0",
        0x06F1: "uni06F1",
        0x06F2: "uni06F2",
        0x06F3: "uni06F3",
        0x06F4: "uni06F4",
        0x06F5: "uni06F5",
        0x06F6: "uni06F6",
        0x06F7: "uni06F7",
        0x06F8: "uni06F8",
        0x06F9: "uni06F9",
        0x0660: "uni0660",
        0x0661: "uni0661",
        0x0627: "uni0627",
        0x0628: "uni0628",
        0x0644: "uni0644",
        0xFEE0: "uniFEE0",
    }

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    glyphs = {}
    for n in glyph_order:
        if n in {".notdef", "space", "zwnj", "zwj"}:
            glyphs[n] = TTGlyph()
        else:
            glyphs[n] = _make_glyf_glyph()
    fb.setupGlyf(glyphs)
    metrics = {n: (500, 50) for n in glyph_order}
    metrics["space"] = (250, 0)
    metrics["zwnj"] = (0, 0)
    metrics["zwj"] = (0, 0)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": "GlyphShiftPersian",
            "styleName": "Regular",
            "uniqueFontIdentifier": "GlyphShiftPersian-Regular",
            "fullName": "GlyphShift Persian Regular",
            "version": "Version 1.000",
            "psName": "GlyphShiftPersian-Regular",
            "copyright": "Synthetic test font for GlyphShift",
        }
    )
    fb.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
        ulUnicodeRange1=(1 << 13),  # Arabic bit
    )
    fb.setupPost()

    # Minimal GSUB with arab script and init/medi/fina/isol/rlig features
    font = fb.font

    def _single_subst(mapping: dict[str, str]):
        sub = otTables.SingleSubst()
        sub.mapping = mapping
        lookup = otTables.Lookup()
        lookup.LookupType = 1
        lookup.LookupFlag = 0
        lookup.SubTable = [sub]
        lookup.SubTableCount = 1
        return lookup

    lookups = [
        _single_subst({"uni0628": "uni0628.init"}),
        _single_subst({"uni0628": "uni0628.medi"}),
        _single_subst({"uni0628": "uni0628.fina"}),
        _single_subst({"uni0628": "uni0628"}),  # isol identity-ish
        _single_subst({"uni0644": "uni0644.init"}),
    ]

    lookup_list = otTables.LookupList()
    lookup_list.Lookup = lookups
    lookup_list.LookupCount = len(lookups)

    features_tags = ["init", "medi", "fina", "isol", "rlig", "mark"]
    feature_records = []
    for i, tag in enumerate(features_tags):
        feat = otTables.Feature()
        feat.LookupListIndex = [min(i, len(lookups) - 1)]
        feat.LookupCount = 1
        rec = otTables.FeatureRecord()
        rec.FeatureTag = tag
        rec.Feature = feat
        feature_records.append(rec)

    feature_list = otTables.FeatureList()
    feature_list.FeatureRecord = feature_records
    feature_list.FeatureCount = len(feature_records)

    lang = otTables.LangSys()
    lang.ReqFeatureIndex = 0xFFFF
    lang.FeatureIndex = list(range(len(features_tags)))
    lang.FeatureCount = len(features_tags)

    script = otTables.Script()
    script.DefaultLangSys = lang
    script.LangSysRecord = []
    script.LangSysCount = 0

    script_rec = otTables.ScriptRecord()
    script_rec.ScriptTag = "arab"
    script_rec.Script = script

    script_list = otTables.ScriptList()
    script_list.ScriptRecord = [script_rec]
    script_list.ScriptCount = 1

    gsub = newTable("GSUB")
    gsub.table = otTables.GSUB()
    gsub.table.Version = 0x00010000
    gsub.table.ScriptList = script_list
    gsub.table.FeatureList = feature_list
    gsub.table.LookupList = lookup_list
    font["GSUB"] = gsub

    # Minimal empty GPOS so has_gpos / preservation checks have something
    gpos = newTable("GPOS")
    gpos.table = otTables.GPOS()
    gpos.table.Version = 0x00010000
    gpos.table.ScriptList = script_list  # reuse structure
    gpos.table.FeatureList = otTables.FeatureList()
    gpos.table.FeatureList.FeatureRecord = []
    gpos.table.FeatureList.FeatureCount = 0
    gpos.table.LookupList = otTables.LookupList()
    gpos.table.LookupList.Lookup = []
    gpos.table.LookupList.LookupCount = 0
    font["GPOS"] = gpos

    font.save(str(path))


def build_variable_glyf(path: Path) -> None:
    """Minimal variable font with fvar + gvar."""
    from fontTools.ttLib import newTable
    from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance

    glyph_order = [".notdef", "space", "A"]
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({0x20: "space", 0x41: "A"})
    glyphs = {
        ".notdef": TTGlyph(),
        "space": TTGlyph(),
        "A": _make_glyf_glyph(),
    }
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({".notdef": (500, 0), "space": (250, 0), "A": (500, 50)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": "GlyphShiftVar",
            "styleName": "Regular",
            "uniqueFontIdentifier": "GlyphShiftVar-Regular",
            "fullName": "GlyphShift Variable",
            "version": "Version 1.000",
            "psName": "GlyphShiftVar-Regular",
        }
    )
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()

    font = fb.font
    fvar = newTable("fvar")
    axis = Axis()
    axis.axisTag = "wght"
    axis.minValue = 100
    axis.defaultValue = 400
    axis.maxValue = 900
    axis.axisNameID = 256
    fvar.axes = [axis]
    inst = NamedInstance()
    inst.coordinates = {"wght": 400}
    inst.subfamilyNameID = 2
    fvar.instances = [inst]
    font["fvar"] = fvar

    # Minimal gvar (empty variations shared)
    gvar = newTable("gvar")
    gvar.version = 1
    gvar.reserved = 0
    gvar.variations = {n: [] for n in glyph_order}
    font["gvar"] = gvar

    # avar identity
    from fontTools.ttLib.tables._a_v_a_r import table__a_v_a_r

    avar = table__a_v_a_r()
    avar.segments = {"wght": {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0}}
    font["avar"] = avar

    font.save(str(path))


def build_collection(ttc_path: Path, face_a: Path, face_b: Path) -> None:
    fonts = [TTFont(str(face_a)), TTFont(str(face_b))]
    coll = TTCollection()
    coll.fonts = fonts
    coll.save(str(ttc_path))
    for f in fonts:
        f.close()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    latin = ROOT / "latin_glyf.ttf"
    cff = ROOT / "latin_cff.otf"
    persian = ROOT / "persian_glyf.ttf"
    variable = ROOT / "variable_glyf.ttf"
    ttc = ROOT / "collection.ttc"
    persian_name = ROOT / "وزیر-نمونه.ttf"

    print("Building latin_glyf.ttf …")
    build_latin_glyf(latin)
    print("Building latin_cff.otf …")
    build_latin_cff(cff)
    print("Building persian_glyf.ttf …")
    build_persian_glyf(persian)
    print("Building variable_glyf.ttf …")
    build_variable_glyf(variable)
    print("Building collection.ttc …")
    build_collection(ttc, latin, persian)
    print("Copying Persian filename …")
    shutil.copy2(persian, persian_name)
    print(f"Fixtures ready in {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
