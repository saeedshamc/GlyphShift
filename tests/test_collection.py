"""TTC/OTC collection handling tests."""

from __future__ import annotations

from pathlib import Path

from glyphshift.core.collection import extract_all, extract_face, list_faces
from glyphshift.core.converter import convert_file, convert_many
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions


def test_list_faces(collection_ttc: Path) -> None:
    faces = list_faces(collection_ttc)
    assert len(faces) >= 2
    assert faces[0]["index"] == 0
    assert "glyph_count" in faces[0]


def test_extract_face(collection_ttc: Path, tmp_out: Path) -> None:
    out, warnings = extract_face(collection_ttc, 0, tmp_out / "face0.ttf", overwrite=True)
    assert out.exists()
    assert warnings
    assert out.stat().st_size > 0


def test_extract_all(collection_ttc: Path, tmp_out: Path) -> None:
    results = extract_all(collection_ttc, tmp_out, overwrite=True)
    assert len(results) >= 2
    for path, _warns in results:
        assert path.exists()


def test_convert_collection_index(collection_ttc: Path, tmp_out: Path) -> None:
    r = convert_file(
        collection_ttc,
        tmp_out,
        Format.WOFF2,
        ConversionOptions(ttc_index=1, overwrite=True),
    )
    assert r.success, r.error
    assert r.output_path is not None
    assert r.output_path.exists()


def test_convert_many_expands_collection(collection_ttc: Path, tmp_out: Path) -> None:
    results = convert_many(
        [collection_ttc],
        tmp_out,
        Format.WOFF2,
        ConversionOptions(overwrite=True),
    )
    assert len(results) >= 2
    assert all(r.success for r in results), [r.error for r in results if not r.success]
