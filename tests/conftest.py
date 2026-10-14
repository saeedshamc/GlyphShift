"""Shared pytest fixtures for GlyphShift tests."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _ensure_fixtures() -> None:
    required = [
        "latin_glyf.ttf",
        "latin_cff.otf",
        "persian_glyf.ttf",
        "variable_glyf.ttf",
        "collection.ttc",
        "وزیر-نمونه.ttf",
    ]
    if all((FIXTURES / name).is_file() for name in required):
        return
    script = FIXTURES / "build_fixtures.py"
    subprocess.run([sys.executable, str(script)], check=True, cwd=str(FIXTURES.parent.parent))


_ensure_fixtures()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def latin_ttf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "latin_glyf.ttf"


@pytest.fixture
def latin_otf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "latin_cff.otf"


@pytest.fixture
def persian_ttf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "persian_glyf.ttf"


@pytest.fixture
def persian_named(fixtures_dir: Path) -> Path:
    return fixtures_dir / "وزیر-نمونه.ttf"


@pytest.fixture
def variable_ttf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "variable_glyf.ttf"


@pytest.fixture
def collection_ttc(fixtures_dir: Path) -> Path:
    return fixtures_dir / "collection.ttc"


@pytest.fixture
def tmp_out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
