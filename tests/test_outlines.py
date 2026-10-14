"""Outline conversion tests (intentionally lossy for hints)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from glyphshift.core.converter import convert_file
from glyphshift.core.errors import ConversionError
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions, VerifyMode
from glyphshift.core.outlines import cff_to_glyf, glyf_to_cff
from glyphshift.core.verify import verify


def test_otf_to_ttf_preserves_cmap_and_order(latin_otf: Path, tmp_out: Path) -> None:
    dest = tmp_out / "from_cff.ttf"
    out, warnings, _err = cff_to_glyf(latin_otf, dest, overwrite=True)
    assert out.exists()
    assert any("hint" in w.lower() or "approx" in w.lower() for w in warnings)
    src = TTFont(str(latin_otf))
    dst = TTFont(str(out))
    try:
        assert src.getGlyphOrder() == dst.getGlyphOrder()
        assert src.getBestCmap() == dst.getBestCmap()
        assert "glyf" in dst
        assert "CFF " not in dst
        assert dst.sfntVersion == "\x00\x01\x00\x00"
    finally:
        src.close()
        dst.close()
    report = verify(
        latin_otf, out, VerifyMode.TOLERANT, outline_converted=True, direction="cff_to_glyf"
    )
    assert report.passed or not report.errors


def test_ttf_to_otf_preserves_layout(persian_ttf: Path, tmp_out: Path) -> None:
    dest = tmp_out / "from_glyf.otf"
    out, warnings = glyf_to_cff(persian_ttf, dest, overwrite=True)
    assert out.exists()
    assert any("hint" in w.lower() for w in warnings)
    src = TTFont(str(persian_ttf))
    dst = TTFont(str(out))
    try:
        assert src.getGlyphOrder() == dst.getGlyphOrder()
        assert src.getBestCmap() == dst.getBestCmap()
        assert "CFF " in dst
        assert "glyf" not in dst
        assert dst.sfntVersion == "OTTO"
        assert "GSUB" in dst
        feats = [r.FeatureTag for r in dst["GSUB"].table.FeatureList.FeatureRecord]
        for tag in ("init", "medi", "fina", "rlig"):
            assert tag in feats
    finally:
        src.close()
        dst.close()


def test_variable_outline_refused(variable_ttf: Path, tmp_out: Path) -> None:
    with pytest.raises(ConversionError, match="variable"):
        glyf_to_cff(variable_ttf, tmp_out / "x.otf", overwrite=True)

    # Via public API targeting OTF from variable glyf
    r = convert_file(
        variable_ttf,
        tmp_out / "v.otf",
        Format.OTF,
        ConversionOptions(verify=False),
    )
    assert not r.success
    assert r.error and "variable" in r.error.lower()


def test_variable_wrapper_preserves_fvar(variable_ttf: Path, tmp_out: Path) -> None:
    dest = tmp_out / "v.woff2"
    r = convert_file(variable_ttf, dest, Format.WOFF2, ConversionOptions())
    assert r.success, r.error
    back = tmp_out / "v.ttf"
    r2 = convert_file(dest, back, Format.TTF, ConversionOptions())
    assert r2.success, r2.error
    src = TTFont(str(variable_ttf))
    dst = TTFont(str(back))
    try:
        for tag in ("fvar", "gvar", "avar"):
            assert tag in src
            assert tag in dst
    finally:
        src.close()
        dst.close()


def test_converter_otf_to_ttf_lossy_flag(latin_otf: Path, tmp_out: Path) -> None:
    r = convert_file(
        latin_otf,
        tmp_out / "lossy.ttf",
        Format.TTF,
        ConversionOptions(verify=True, keep_on_fail=True),
    )
    assert r.success, r.error
    assert not r.lossless
    assert r.warnings
