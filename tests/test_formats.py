"""Tests for magic-byte format detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphshift.core.errors import CorruptFontError, UnsupportedFormatError
from glyphshift.core.formats import Format, OutlineType, detect_format


def test_detect_ttf(latin_ttf: Path) -> None:
    d = detect_format(latin_ttf)
    assert d.format == Format.TTF
    assert d.outline == OutlineType.GLYF
    assert not d.is_collection
    assert not d.is_variable


def test_detect_otf(latin_otf: Path) -> None:
    d = detect_format(latin_otf)
    assert d.format == Format.OTF
    assert d.outline == OutlineType.CFF


def test_detect_wrong_extension(latin_ttf: Path, tmp_path: Path) -> None:
    wrong = tmp_path / "latin.woff2"
    wrong.write_bytes(latin_ttf.read_bytes())
    d = detect_format(wrong)
    assert d.format == Format.TTF
    assert d.extension_mismatch
    assert d.warnings


def test_detect_woff_woff2(latin_ttf: Path, tmp_path: Path) -> None:
    from glyphshift.core.converter import convert_file
    from glyphshift.core.models import ConversionOptions

    woff = tmp_path / "a.woff"
    woff2 = tmp_path / "a.woff2"
    r1 = convert_file(latin_ttf, woff, Format.WOFF, ConversionOptions(verify=True))
    r2 = convert_file(latin_ttf, woff2, Format.WOFF2, ConversionOptions(verify=True))
    assert r1.success and r2.success
    assert detect_format(woff).format == Format.WOFF
    assert detect_format(woff2).format == Format.WOFF2
    assert detect_format(woff).outline == OutlineType.GLYF


def test_detect_collection(collection_ttc: Path) -> None:
    d = detect_format(collection_ttc)
    assert d.is_collection
    assert d.format in (Format.TTC, Format.OTC)


def test_detect_variable(variable_ttf: Path) -> None:
    d = detect_format(variable_ttf)
    assert d.is_variable
    assert d.format == Format.TTF


def test_corrupt_truncated(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"\x00\x01")
    with pytest.raises(CorruptFontError):
        detect_format(bad)


def test_unsupported_signature(tmp_path: Path) -> None:
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"XXXX\x00\x00\x00\x00")
    with pytest.raises(UnsupportedFormatError):
        detect_format(bad)
