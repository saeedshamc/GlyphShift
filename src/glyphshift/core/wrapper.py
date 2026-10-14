"""Lossless container conversions between TTF/OTF and WOFF/WOFF2."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont

from glyphshift.core.errors import ConversionError, OutputExistsError
from glyphshift.core.formats import Format

logger = logging.getLogger(__name__)

_FLAVOR_MAP = {
    Format.TTF: None,
    Format.OTF: None,
    Format.WOFF: "woff",
    Format.WOFF2: "woff2",
}


def resolve_output_path(
    src: Path,
    dst: Path | None,
    target: Format,
    *,
    overwrite: bool,
    suffix_index: int | None = None,
) -> Path:
    """Compute the final output path; never returns the input path."""
    if dst is None:
        stem = src.stem
        if suffix_index is not None:
            stem = f"{stem}-{suffix_index}"
        out = src.with_name(f"{stem}{target.extension}")
    elif dst.is_dir() or (not dst.suffix and not dst.exists()):
        # Treat as directory when it exists as dir, or looks like one.
        directory = dst if dst.is_dir() or not dst.suffix else dst.parent
        directory.mkdir(parents=True, exist_ok=True)
        stem = src.stem
        if suffix_index is not None:
            stem = f"{stem}-{suffix_index}"
        out = directory / f"{stem}{target.extension}"
    else:
        out = dst

    if out.resolve() == src.resolve():
        raise ConversionError(
            f"Refusing to overwrite the input file in place: {src}"
        )

    if out.exists() and not overwrite:
        raise OutputExistsError(
            f"Output already exists (use --overwrite or choose another path): {out}"
        )

    return out


def unique_path(path: Path) -> Path:
    """Return path, or path with ' (N)' suffix if it already exists."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _atomic_save(font: TTFont, final_path: Path) -> None:
    """Write via a temp file in the same directory, then os.replace."""
    final_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{final_path.stem}.",
        suffix=f".tmp{final_path.suffix}",
        dir=str(final_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        font.save(str(tmp_path))
        os.replace(str(tmp_path), str(final_path))
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                logger.warning("Could not remove temp file %s", tmp_path)
        raise


def wrap_font(
    src: Path,
    dst: Path,
    target: Format,
    *,
    overwrite: bool = False,
) -> Path:
    """Convert only the container (flavor). Never subsets or drops tables.

    Parameters
    ----------
    src:
        Source font path (TTF, OTF, WOFF, or WOFF2).
    dst:
        Destination path (file).
    target:
        Desired Format (TTF/OTF keep flavor=None; WOFF/WOFF2 set flavor).
    overwrite:
        If False and dst exists, raise OutputExistsError.

    Returns
    -------
    Path
        The written output path.
    """
    out = resolve_output_path(src, dst, target, overwrite=overwrite)
    flavor = _FLAVOR_MAP[target]

    try:
        font = TTFont(
            str(src),
            recalcTimestamp=False,
            recalcBBoxes=False,
            lazy=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise ConversionError(f"Failed to open font {src}: {exc}") from exc

    try:
        # Preserve WOFF metadata / private data when present.
        # fontTools keeps flavorData on the TTFont; we only change flavor.
        previous_flavor = font.flavor
        previous_flavor_data = getattr(font, "flavorData", None)

        font.flavor = flavor

        # When going woff -> woff (or woff2 -> woff2), keep flavorData.
        # When decompressing to sfnt, clear flavorData (not applicable).
        # When compressing, keep existing flavorData if any (woff metadata).
        if flavor is None:
            font.flavorData = None
        elif previous_flavor_data is not None and previous_flavor in ("woff", "woff2"):
            font.flavorData = previous_flavor_data

        # Do not touch head.modified — recalcTimestamp=False already.
        try:
            _atomic_save(font, out)
        except Exception as exc:  # noqa: BLE001
            raise ConversionError(f"Failed to save converted font to {out}: {exc}") from exc
    finally:
        font.close()

    logger.info("Wrapped %s -> %s (flavor=%s)", src, out, flavor)
    return out
