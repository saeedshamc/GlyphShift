"""Conversion history and safe undo (delete recorded outputs only)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _history_dir() -> Path:
    try:
        from platformdirs import user_data_dir

        base = Path(user_data_dir("GlyphShift", "GlyphShift"))
    except Exception:
        base = Path.home() / ".glyphshift"
    path = base / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_file() -> Path:
    return _history_dir() / "conversions.jsonl"


@dataclass
class HistoryEntry:
    id: str
    timestamp: float
    input_path: str
    output_path: str | None
    target: str
    success: bool
    lossless: bool
    error: str | None = None
    undone: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            id=str(data["id"]),
            timestamp=float(data["timestamp"]),
            input_path=str(data["input_path"]),
            output_path=data.get("output_path"),
            target=str(data.get("target", "")),
            success=bool(data.get("success")),
            lossless=bool(data.get("lossless", True)),
            error=data.get("error"),
            undone=bool(data.get("undone", False)),
            meta=dict(data.get("meta") or {}),
        )


def record_conversion(
    *,
    input_path: Path | str,
    output_path: Path | str | None,
    target: str,
    success: bool,
    lossless: bool,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> HistoryEntry:
    """Append one conversion to the JSONL history log."""
    entry = HistoryEntry(
        id=uuid.uuid4().hex,
        timestamp=time.time(),
        input_path=str(input_path),
        output_path=str(output_path) if output_path else None,
        target=target,
        success=success,
        lossless=lossless,
        error=error,
        meta=meta or {},
    )
    path = history_file()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    return entry


def list_history(*, limit: int = 100, include_undone: bool = False) -> list[HistoryEntry]:
    path = history_file()
    if not path.exists():
        return []
    entries: list[HistoryEntry] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(HistoryEntry.from_dict(json.loads(line)))
            except Exception:
                logger.warning("Skipping corrupt history line")
    if not include_undone:
        entries = [e for e in entries if not e.undone]
    return list(reversed(entries[-limit:]))


def _rewrite_all(entries: list[HistoryEntry]) -> None:
    path = history_file()
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


def undo_entry(entry_id: str, *, delete_output: bool = True) -> HistoryEntry:
    """Mark an entry undone and optionally delete its output file.

    Never deletes the original input. Only removes the recorded output path
    when it still exists and ``delete_output`` is True.
    """
    path = history_file()
    if not path.exists():
        raise FileNotFoundError("No conversion history")

    raw: list[HistoryEntry] = []
    found: HistoryEntry | None = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = HistoryEntry.from_dict(json.loads(line))
            if entry.id == entry_id:
                found = entry
            raw.append(entry)

    if found is None:
        raise KeyError(f"History entry not found: {entry_id}")
    if found.undone:
        return found

    if delete_output and found.output_path and found.success:
        out = Path(found.output_path)
        # Safety: never delete if path equals input.
        if out.resolve() != Path(found.input_path).resolve() and out.is_file():
            try:
                out.unlink()
            except OSError as exc:
                logger.warning("Could not delete output %s: %s", out, exc)

    found.undone = True
    for i, entry in enumerate(raw):
        if entry.id == entry_id:
            raw[i] = found
            break
    _rewrite_all(raw)
    return found


def clear_history() -> None:
    path = history_file()
    if path.exists():
        path.write_text("", encoding="utf-8")
