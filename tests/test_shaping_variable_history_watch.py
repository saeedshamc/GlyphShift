"""Shaping, variable helpers, history, and watch-folder tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from glyphshift.core.converter import convert_file
from glyphshift.core.formats import Format
from glyphshift.core.history import list_history, record_conversion, undo_entry
from glyphshift.core.models import ConversionOptions
from glyphshift.core.shaping import compare_shaping, harfbuzz_available, shape_samples
from glyphshift.core.variable import format_instance_spec, list_axes, parse_instance_spec
from glyphshift.core.watch import watch_folder


def test_shape_persian(persian_ttf: Path) -> None:
    report = shape_samples(persian_ttf)
    if not harfbuzz_available():
        assert not report.available
        pytest.skip("uharfbuzz not installed")
    assert report.available
    assert report.samples
    assert report.passed


def test_compare_shaping_woff2(persian_ttf: Path, tmp_out: Path) -> None:
    if not harfbuzz_available():
        pytest.skip("uharfbuzz not installed")
    r = convert_file(
        persian_ttf,
        tmp_out / "p.woff2",
        Format.WOFF2,
        ConversionOptions(overwrite=True, record_history=False),
    )
    assert r.success, r.error
    # Shape against unwrapped path: compare source to woff2 via fontTools load works.
    report = compare_shaping(persian_ttf, r.output_path)  # type: ignore[arg-type]
    assert report.passed, [i.to_dict() for i in report.issues]


def test_variable_axes(variable_ttf: Path) -> None:
    axes = list_axes(variable_ttf)
    assert any(a["tag"] == "wght" for a in axes)
    spec = format_instance_spec({"wght": 400})
    assert parse_instance_spec(spec)["wght"] == 400


def test_history_undo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, latin_ttf: Path) -> None:
    hist = tmp_path / "conversions.jsonl"
    monkeypatch.setattr("glyphshift.core.history.history_file", lambda: hist)
    out = tmp_path / "out.woff2"
    out.write_bytes(b"fake")
    entry = record_conversion(
        input_path=latin_ttf,
        output_path=out,
        target="woff2",
        success=True,
        lossless=True,
    )
    assert list_history()
    undone = undo_entry(entry.id, delete_output=True)
    assert undone.undone
    assert not out.exists()


def test_watch_folder_detects_new_file(
    latin_ttf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    watch_dir.mkdir()
    out_dir.mkdir()

    calls = {"n": 0}
    original_sleep = time.sleep

    def flaky_sleep(seconds: float) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            dest = watch_dir / latin_ttf.name
            dest.write_bytes(latin_ttf.read_bytes())
        original_sleep(0.05)

    monkeypatch.setattr(time, "sleep", flaky_sleep)
    results = watch_folder(
        watch_dir,
        out_dir,
        Format.WOFF2,
        ConversionOptions(overwrite=True, verify=True, record_history=False),
        interval=0.05,
        stop_after=0.4,
        recursive=False,
    )
    assert any(r.success for r in results), results
