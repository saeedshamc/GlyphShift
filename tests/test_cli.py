"""CLI tests via click.testing.CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from glyphshift.cli import main


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_formats() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["formats"])
    assert result.exit_code == 0
    assert "LOSSLESS" in result.output


def test_info_json(latin_ttf: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["info", str(latin_ttf), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["glyph_count"] > 0
    assert data["format"] == "ttf"


def test_convert_woff2(latin_ttf: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    result = runner.invoke(
        main,
        ["convert", str(latin_ttf), "--to", "woff2", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert list(out.glob("*.woff2"))


def test_convert_batch_dir(latin_ttf: Path, latin_otf: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    src = tmp_path / "fonts"
    src.mkdir()
    (src / latin_ttf.name).write_bytes(latin_ttf.read_bytes())
    (src / latin_otf.name).write_bytes(latin_otf.read_bytes())
    out = tmp_path / "out"
    out.mkdir()
    result = runner.invoke(
        main,
        ["convert", str(src), "--to", "woff", "--out", str(out), "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["converted"] >= 2
    assert data["failed"] == 0


def test_convert_persian_filename(persian_named: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    result = runner.invoke(
        main,
        ["convert", str(persian_named), "--to", "woff2", "--out", str(out), "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["converted"] == 1


def test_verify_command(latin_ttf: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    conv = runner.invoke(
        main,
        ["convert", str(latin_ttf), "--to", "woff2", "--out", str(out)],
    )
    assert conv.exit_code == 0
    woff2 = next(out.glob("*.woff2"))
    result = runner.invoke(main, ["verify", str(latin_ttf), str(woff2), "--strict", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["passed"] is True


def test_overwrite_exit_code(latin_ttf: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    args = ["convert", str(latin_ttf), "--to", "woff2", "--out", str(out), "--json"]
    r1 = runner.invoke(main, args)
    assert r1.exit_code == 0
    r2 = runner.invoke(main, args)
    assert r2.exit_code == 1
    data = json.loads(r2.output)
    assert data["failed"] == 1
