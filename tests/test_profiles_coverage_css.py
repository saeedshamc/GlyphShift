"""Tests for profiles, coverage warnings, and CSS helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphshift.core.converter import convert_file
from glyphshift.core.coverage import coverage_warnings, format_coverage_summary
from glyphshift.core.css import font_face_bundle, font_face_css, suggest_unicode_ranges
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions
from glyphshift.core.profiles import Profile, apply_profile, list_profiles


def test_list_profiles() -> None:
    profiles = list_profiles()
    ids = {p["id"] for p in profiles}
    assert ids == {"web", "desktop", "lossless"}


def test_apply_web_profile() -> None:
    fmt, opts = apply_profile(Profile.WEB)
    assert fmt == Format.WOFF2
    assert opts.verify is True


def test_lossless_refuses_outline(latin_otf: Path, tmp_out: Path) -> None:
    _fmt, opts = apply_profile("lossless", ConversionOptions(overwrite=True))
    r = convert_file(latin_otf, tmp_out / "x.ttf", Format.TTF, opts)
    assert not r.success
    assert r.error and "lossless" in r.error.lower()


def test_lossless_allows_woff2(latin_ttf: Path, tmp_out: Path) -> None:
    _fmt, opts = apply_profile("lossless", ConversionOptions(overwrite=True))
    r = convert_file(latin_ttf, tmp_out / "x.woff2", Format.WOFF2, opts)
    assert r.success, r.error
    assert r.lossless


def test_coverage_persian(persian_ttf: Path) -> None:
    issues = coverage_warnings(persian_ttf)
    # Synthetic Persian fixture should be clean or only INFO-level.
    assert all(i.severity.value != "error" for i in issues)
    summary = format_coverage_summary(persian_ttf)
    assert "codepoints" in summary


def test_css_font_face(persian_ttf: Path) -> None:
    css = font_face_css(persian_ttf, unicode_range_preset="persian")
    assert "@font-face" in css
    assert "unicode-range" in css
    assert "U+06F0-06F9" in css
    bundle = font_face_bundle(persian_ttf)
    assert bundle.count("@font-face") >= 1
    assert "persian" in suggest_unicode_ranges(persian_ttf)


def test_css_unknown_preset(latin_ttf: Path) -> None:
    with pytest.raises(ValueError):
        font_face_css(latin_ttf, unicode_range_preset="nope")
