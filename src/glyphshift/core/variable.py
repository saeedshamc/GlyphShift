"""Variable-font axis inspection and instance-spec helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont

from glyphshift.core.errors import ConversionError, CorruptFontError


def list_axes(path: Path | str) -> list[dict[str, Any]]:
    """Return fvar axes for a font (empty list if not variable)."""
    path = Path(path)
    try:
        font = TTFont(str(path), recalcTimestamp=False, recalcBBoxes=False, lazy=True)
    except Exception as exc:  # noqa: BLE001
        raise CorruptFontError(f"Cannot open font {path}: {exc}") from exc
    try:
        if "fvar" not in font:
            return []
        axes = []
        for axis in font["fvar"].axes:
            axes.append(
                {
                    "tag": axis.axisTag,
                    "min": float(axis.minValue),
                    "default": float(axis.defaultValue),
                    "max": float(axis.maxValue),
                }
            )
        return axes
    finally:
        font.close()


def list_named_instances(path: Path | str) -> list[dict[str, Any]]:
    """Return named instances from fvar when present."""
    path = Path(path)
    try:
        font = TTFont(str(path), recalcTimestamp=False, recalcBBoxes=False, lazy=True)
    except Exception as exc:  # noqa: BLE001
        raise CorruptFontError(f"Cannot open font {path}: {exc}") from exc
    try:
        if "fvar" not in font:
            return []
        name_table = font["name"] if "name" in font else None
        out: list[dict[str, Any]] = []
        for inst in font["fvar"].instances:
            label = None
            if name_table is not None:
                for rec in name_table.names:
                    if rec.nameID == inst.subfamilyNameID:
                        try:
                            label = rec.toUnicode()
                            break
                        except Exception:  # noqa: BLE001
                            continue
            out.append(
                {
                    "name": label or f"instance-{len(out)}",
                    "coordinates": {k: float(v) for k, v in inst.coordinates.items()},
                }
            )
        return out
    finally:
        font.close()


def format_instance_spec(coordinates: dict[str, float]) -> str:
    """Serialize axis map to ``wght=400,wdth=100`` form."""
    parts = [f"{tag}={value:g}" for tag, value in coordinates.items()]
    return ",".join(parts)


def parse_instance_spec(spec: str) -> dict[str, float]:
    """Parse ``wght=400,wdth=100`` into a coordinate dict."""
    axis_limits: dict[str, float] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ConversionError(
                f"Invalid instance spec '{part}'; expected tag=value (e.g. wght=400)"
            )
        tag, val = part.split("=", 1)
        axis_limits[tag.strip()] = float(val.strip())
    if not axis_limits:
        raise ConversionError("Empty instance specification")
    return axis_limits


def clamp_to_axes(coordinates: dict[str, float], axes: list[dict[str, Any]]) -> dict[str, float]:
    """Clamp coordinates into declared axis ranges."""
    by_tag = {a["tag"]: a for a in axes}
    out: dict[str, float] = {}
    for tag, value in coordinates.items():
        if tag not in by_tag:
            raise ConversionError(f"Unknown axis '{tag}'")
        lo, hi = by_tag[tag]["min"], by_tag[tag]["max"]
        out[tag] = min(max(value, lo), hi)
    return out
