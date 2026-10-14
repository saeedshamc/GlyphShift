"""Lossless wrapper conversion tests."""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions
from glyphshift.core.converter import convert_file
from glyphshift.core.verify import verify
from glyphshift.core.models import VerifyMode
from tests.conftest import file_sha256


def _roundtrip(src: Path, tmp_out: Path, *formats: Format) -> Path:
    current = src
    opts = ConversionOptions(overwrite=True, verify=True)
    for i, fmt in enumerate(formats):
        dest = tmp_out / f"step{i}{fmt.extension}"
        result = convert_file(current, dest, fmt, opts)
        assert result.success, result.error
        assert result.lossless
        assert result.verify_report is not None
        assert result.verify_report.passed
        current = result.output_path  # type: ignore[assignment]
    return current


def test_ttf_woff_woff2_ttf(latin_ttf: Path, tmp_out: Path) -> None:
    final = _roundtrip(latin_ttf, tmp_out, Format.WOFF, Format.WOFF2, Format.TTF)
    report = verify(latin_ttf, final, VerifyMode.STRICT)
    assert report.passed, [i.message for i in report.errors]


def test_otf_woff2_otf(latin_otf: Path, tmp_out: Path) -> None:
    final = _roundtrip(latin_otf, tmp_out, Format.WOFF2, Format.OTF)
    report = verify(latin_otf, final, VerifyMode.STRICT)
    assert report.passed, [i.message for i in report.errors]


def test_all_wrapper_directions(latin_ttf: Path, latin_otf: Path, tmp_out: Path) -> None:
    pairs = [
        (latin_ttf, Format.WOFF),
        (latin_ttf, Format.WOFF2),
        (latin_otf, Format.WOFF),
        (latin_otf, Format.WOFF2),
    ]
    opts = ConversionOptions(overwrite=True)
    for src, fmt in pairs:
        dest = tmp_out / f"{src.stem}{fmt.extension}"
        result = convert_file(src, dest, fmt, opts)
        assert result.success, result.error
        assert result.lossless
        back = Format.TTF if src.suffix.lower() == ".ttf" else Format.OTF
        back_path = tmp_out / f"{src.stem}.back{back.extension}"
        result2 = convert_file(dest, back_path, back, opts)
        assert result2.success, result2.error
        report = verify(src, back_path, VerifyMode.STRICT)
        assert report.passed, [i.message for i in report.errors]


def test_source_never_modified(latin_ttf: Path, tmp_out: Path) -> None:
    before = file_sha256(latin_ttf)
    convert_file(latin_ttf, tmp_out / "x.woff2", Format.WOFF2, ConversionOptions())
    assert file_sha256(latin_ttf) == before


def test_no_overwrite_by_default(latin_ttf: Path, tmp_out: Path) -> None:
    dest = tmp_out / "latin_glyf.woff2"
    r1 = convert_file(latin_ttf, dest, Format.WOFF2, ConversionOptions())
    assert r1.success
    r2 = convert_file(latin_ttf, dest, Format.WOFF2, ConversionOptions(overwrite=False))
    assert not r2.success
    assert "exists" in (r2.error or "").lower()


def test_glyph_order_and_cmap_preserved(persian_ttf: Path, tmp_out: Path) -> None:
    dest = tmp_out / "p.woff2"
    r = convert_file(persian_ttf, dest, Format.WOFF2, ConversionOptions())
    assert r.success
    back = tmp_out / "p.ttf"
    r2 = convert_file(dest, back, Format.TTF, ConversionOptions())
    assert r2.success
    src = TTFont(str(persian_ttf))
    dst = TTFont(str(back))
    try:
        assert src.getGlyphOrder() == dst.getGlyphOrder()
        assert src.getBestCmap() == dst.getBestCmap()
    finally:
        src.close()
        dst.close()
