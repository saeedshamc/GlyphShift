"""Verification layer tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from fontTools.ttLib import TTFont

from glyphshift.core.converter import convert_file
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions, VerifyMode
from glyphshift.core.verify import verify


def test_verify_passes_on_identical_copy(latin_ttf: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy.ttf"
    shutil.copy2(latin_ttf, copy)
    report = verify(latin_ttf, copy, VerifyMode.STRICT)
    assert report.passed


def test_verify_catches_removed_glyph(latin_ttf: Path, tmp_path: Path) -> None:
    damaged = tmp_path / "damaged.ttf"
    shutil.copy2(latin_ttf, damaged)
    font = TTFont(str(damaged))
    order = list(font.getGlyphOrder())
    # Remove a glyph from glyf and order
    victim = order[-1]
    del font["glyf"].glyphs[victim]
    font.setGlyphOrder(order[:-1])
    font["maxp"].numGlyphs = len(order) - 1
    # Fix hmtx
    if victim in font["hmtx"].metrics:
        del font["hmtx"].metrics[victim]
    font.save(str(damaged))
    font.close()
    report = verify(latin_ttf, damaged, VerifyMode.STRICT)
    assert not report.passed
    codes = {i.code for i in report.errors}
    assert "glyph_count" in codes or "glyph_order" in codes


def test_verify_catches_cmap_edit(persian_ttf: Path, tmp_path: Path) -> None:
    damaged = tmp_path / "cmap_edit.ttf"
    shutil.copy2(persian_ttf, damaged)
    font = TTFont(str(damaged))
    for table in font["cmap"].tables:
        if 0x200C in table.cmap:
            del table.cmap[0x200C]
    font.save(str(damaged))
    font.close()
    report = verify(persian_ttf, damaged, VerifyMode.STRICT)
    assert not report.passed
    assert any(
        i.code in {"critical_cp_missing", "cmap_mapping"} for i in report.errors
    )


def test_verify_catches_dropped_gsub(persian_ttf: Path, tmp_path: Path) -> None:
    damaged = tmp_path / "no_gsub.ttf"
    shutil.copy2(persian_ttf, damaged)
    font = TTFont(str(damaged))
    del font["GSUB"]
    font.save(str(damaged))
    font.close()
    report = verify(persian_ttf, damaged, VerifyMode.STRICT)
    assert not report.passed
    assert any("GSUB" in i.message or "gsub" in i.code.lower() for i in report.errors)


def test_persian_features_survive_woff2(persian_ttf: Path, tmp_out: Path) -> None:
    dest = tmp_out / "fa.woff2"
    r = convert_file(persian_ttf, dest, Format.WOFF2, ConversionOptions())
    assert r.success
    back = tmp_out / "fa.ttf"
    r2 = convert_file(dest, back, Format.TTF, ConversionOptions())
    assert r2.success
    report = verify(persian_ttf, back, VerifyMode.STRICT)
    assert report.passed, [i.to_dict() for i in report.errors]
    src = TTFont(str(persian_ttf))
    dst = TTFont(str(back))
    try:
        cmap_s = src.getBestCmap()
        cmap_d = dst.getBestCmap()
        for cp in range(0x06F0, 0x06FA):
            assert cmap_s.get(cp) == cmap_d.get(cp)
        assert cmap_s.get(0x200C) == cmap_d.get(0x200C)
        assert "GSUB" in dst
        scripts = [r.ScriptTag for r in dst["GSUB"].table.ScriptList.ScriptRecord]
        assert "arab" in scripts
        feats = [r.FeatureTag for r in dst["GSUB"].table.FeatureList.FeatureRecord]
        for tag in ("init", "medi", "fina", "isol", "rlig", "mark"):
            assert tag in feats
    finally:
        src.close()
        dst.close()
