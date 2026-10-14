"""CLI tests for new subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from glyphshift.cli import main


def test_profiles_and_css(persian_ttf: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["profiles", "--json"])
    assert r.exit_code == 0
    assert "web" in r.output
    r2 = runner.invoke(main, ["css", str(persian_ttf), "--preset", "persian"])
    assert r2.exit_code == 0
    assert "@font-face" in r2.output
    assert "unicode-range" in r2.output


def test_convert_profile_web(latin_ttf: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    r = runner.invoke(
        main,
        [
            "convert",
            str(latin_ttf),
            "--profile",
            "web",
            "--out",
            str(out),
            "--json",
            "--no-history",
        ],
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["converted"] == 1
    assert list(out.glob("*.woff2"))


def test_coverage_and_history(persian_ttf: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["coverage", str(persian_ttf)])
    assert r.exit_code == 0
    out = tmp_path / "o"
    out.mkdir()
    runner.invoke(
        main,
        ["convert", str(persian_ttf), "--to", "woff2", "--out", str(out)],
    )
    h = runner.invoke(main, ["history", "--json", "--limit", "5"])
    assert h.exit_code == 0
