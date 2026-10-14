"""TTC/OTC collection listing and face extraction."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from glyphshift.core.errors import ConversionError, CorruptFontError
from glyphshift.core.formats import Format, OutlineType, detect_format

logger = logging.getLogger(__name__)


def list_faces(path: Path | str) -> list[dict]:
    """Return a summary of each face in a TTC/OTC collection."""
    path = Path(path)
    detected = detect_format(path, deep=False)
    if not detected.is_collection:
        raise ConversionError(f"Not a font collection: {path}")

    try:
        coll = TTCollection(str(path))
    except Exception as exc:  # noqa: BLE001
        raise CorruptFontError(f"Cannot open collection {path}: {exc}") from exc

    faces: list[dict] = []
    try:
        for i, font in enumerate(coll.fonts):
            family = None
            if "name" in font:
                for rec in font["name"].names:
                    if rec.nameID == 1:
                        try:
                            family = rec.toUnicode()
                            break
                        except Exception:  # noqa: BLE001
                            continue
            tags = set(font.keys())
            if "CFF2" in tags:
                outline = OutlineType.CFF2.value
            elif "CFF " in tags:
                outline = OutlineType.CFF.value
            elif "glyf" in tags:
                outline = OutlineType.GLYF.value
            else:
                outline = OutlineType.UNKNOWN.value
            faces.append(
                {
                    "index": i,
                    "family": family,
                    "glyph_count": font["maxp"].numGlyphs if "maxp" in font else 0,
                    "outline": outline,
                    "is_variable": "fvar" in tags,
                }
            )
    finally:
        coll.close()
    return faces


def extract_face(
    path: Path | str,
    index: int,
    dst: Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, list[str]]:
    """Extract a single face from a TTC/OTC into a standalone sfnt file.

    Extraction duplicates any tables that were shared between faces in the
    collection — that is expected and produces a self-contained font.
    """
    path = Path(path)
    warnings: list[str] = [
        "Extracting a face from a collection duplicates any shared tables; "
        "this is expected and produces a self-contained font."
    ]

    try:
        coll = TTCollection(str(path))
    except Exception as exc:  # noqa: BLE001
        raise CorruptFontError(f"Cannot open collection {path}: {exc}") from exc

    try:
        if index < 0 or index >= len(coll.fonts):
            raise ConversionError(
                f"Face index {index} out of range (0..{len(coll.fonts) - 1})"
            )
        font: TTFont = coll.fonts[index]
        tags = set(font.keys())
        if "CFF " in tags or "CFF2" in tags:
            target = Format.OTF
        else:
            target = Format.TTF

        out = Path(dst)
        if out.is_dir():
            out = out / f"{path.stem}-{index}{target.extension}"
        if out.exists() and not overwrite:
            from glyphshift.core.errors import OutputExistsError

            raise OutputExistsError(f"Output already exists: {out}")

        out.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{out.stem}.",
            suffix=f".tmp{out.suffix}",
            dir=str(out.parent),
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            font.save(str(tmp_path))
            os.replace(str(tmp_path), str(out))
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise
    finally:
        coll.close()

    logger.info("Extracted face %d from %s -> %s", index, path, out)
    return out, warnings


def extract_all(
    path: Path | str,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> list[tuple[Path, list[str]]]:
    """Extract every face from a collection into ``out_dir``."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    faces = list_faces(path)
    results: list[tuple[Path, list[str]]] = []
    for face in faces:
        idx = face["index"]
        dest = out_dir / f"{path.stem}-{idx}.ttf"
        # extract_face will pick .otf if CFF
        results.append(extract_face(path, idx, dest, overwrite=overwrite))
    return results
