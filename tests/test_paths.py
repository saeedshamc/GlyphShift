"""Path safety and Persian filename tests."""

from __future__ import annotations

from pathlib import Path

from glyphshift.core.converter import convert_file
from glyphshift.core.formats import Format, detect_format
from glyphshift.core.info import inspect_font
from glyphshift.core.models import ConversionOptions
from tests.conftest import file_sha256


def test_persian_filename_roundtrip(persian_named: Path, tmp_out: Path) -> None:
    assert persian_named.exists()
    d = detect_format(persian_named)
    assert d.format == Format.TTF
    dest = tmp_out / "خروجی.woff2"
    r = convert_file(persian_named, dest, Format.WOFF2, ConversionOptions())
    assert r.success, r.error
    assert dest.exists()
    info = inspect_font(dest)
    assert info.has_zwnj
    assert info.has_persian_digits


def test_output_preserves_stem(latin_ttf: Path, tmp_out: Path) -> None:
    r = convert_file(latin_ttf, tmp_out, Format.WOFF2, ConversionOptions())
    assert r.success
    assert r.output_path is not None
    assert r.output_path.name == f"{latin_ttf.stem}.woff2"


def test_failed_conversion_no_partial(latin_ttf: Path, tmp_out: Path) -> None:
    # Force failure: output exists, no overwrite
    dest = tmp_out / "exists.woff2"
    dest.write_bytes(b"placeholder")
    before_files = set(tmp_out.iterdir())
    r = convert_file(latin_ttf, dest, Format.WOFF2, ConversionOptions(overwrite=False))
    assert not r.success
    after = set(tmp_out.iterdir())
    # No new temp leftovers
    extras = [p for p in after - before_files if ".tmp" in p.name]
    assert extras == []


def test_source_hash_stable(persian_ttf: Path, tmp_out: Path) -> None:
    h = file_sha256(persian_ttf)
    convert_file(persian_ttf, tmp_out / "x.woff", Format.WOFF, ConversionOptions())
    convert_file(persian_ttf, tmp_out / "y.woff2", Format.WOFF2, ConversionOptions())
    assert file_sha256(persian_ttf) == h
