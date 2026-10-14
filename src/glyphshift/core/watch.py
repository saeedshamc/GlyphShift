"""Watch a folder and convert new/changed font files (polling, no extra deps)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from glyphshift.core.converter import convert_file
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions, ConversionResult

logger = logging.getLogger(__name__)

FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc"}


def _scan(folder: Path, *, recursive: bool) -> dict[Path, float]:
    globber = folder.rglob if recursive else folder.glob
    found: dict[Path, float] = {}
    for pattern in ("*.ttf", "*.otf", "*.woff", "*.woff2", "*.ttc", "*.otc"):
        for path in globber(pattern):
            if path.is_file() and path.suffix.lower() in FONT_SUFFIXES:
                try:
                    found[path.resolve()] = path.stat().st_mtime
                except OSError:
                    continue
    return found


def watch_folder(
    folder: Path | str,
    out_dir: Path | str,
    target: Format | str,
    options: ConversionOptions | None = None,
    *,
    interval: float = 2.0,
    recursive: bool = True,
    stop_after: float | None = None,
    on_result: Callable[[ConversionResult], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[ConversionResult]:
    """Poll ``folder`` and convert newly seen or modified fonts.

    Parameters
    ----------
    stop_after:
        Optional max runtime in seconds (useful for tests).
    should_stop:
        Optional callback; when it returns True the loop exits.
    """
    options = options or ConversionOptions()
    folder = Path(folder)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(target, str):
        target = Format.from_string(target)

    seen = _scan(folder, recursive=recursive)
    # Do not convert the initial snapshot unless empty watch — only new/changed.
    results: list[ConversionResult] = []
    started = time.time()
    logger.info("Watching %s -> %s (%s)", folder, out_dir, target.value)

    while True:
        if should_stop is not None and should_stop():
            break
        if stop_after is not None and (time.time() - started) >= stop_after:
            break

        current = _scan(folder, recursive=recursive)
        for path, mtime in current.items():
            prev = seen.get(path)
            if prev is not None and mtime <= prev:
                continue
            # New or updated file
            logger.info("Watch triggered for %s", path)
            result = convert_file(path, out_dir, target, options)
            results.append(result)
            if on_result is not None:
                on_result(result)
            seen[path] = mtime

        # Drop deleted paths from seen
        for gone in list(seen):
            if gone not in current:
                del seen[gone]

        time.sleep(max(0.2, interval))

    return results
