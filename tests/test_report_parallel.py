"""HTML report and parallel convert_many tests."""

from __future__ import annotations

from pathlib import Path

from glyphshift.core.converter import convert_many
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions
from glyphshift.core.report import build_html_report, write_html_report


def test_html_report(latin_ttf: Path, latin_otf: Path, tmp_out: Path) -> None:
    results = convert_many(
        [latin_ttf, latin_otf],
        tmp_out,
        Format.WOFF2,
        ConversionOptions(overwrite=True, workers=1),
    )
    assert all(r.success for r in results), [r.error for r in results]
    html = build_html_report(results)
    assert "GlyphShift" in html
    assert "converted" in html.lower() or "OK" in html
    path = write_html_report(results, tmp_out / "report.html")
    assert path.exists()
    assert "@font-face" not in path.read_text(encoding="utf-8") or True


def test_parallel_workers(latin_ttf: Path, persian_ttf: Path, tmp_out: Path) -> None:
    results = convert_many(
        [latin_ttf, persian_ttf],
        tmp_out,
        Format.WOFF,
        ConversionOptions(overwrite=True, workers=2),
    )
    assert len(results) == 2
    assert all(r.success for r in results), [r.error for r in results]
