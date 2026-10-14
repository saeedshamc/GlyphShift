"""Background conversion workers for the GUI."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from glyphshift.core.converter import convert_many
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions, ConversionResult

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    progress = Signal(int, int, str)  # done, total, current_file
    finished = Signal(list)  # list[ConversionResult]
    error = Signal(str)


class ConvertWorker(QRunnable):
    """Run ``convert_many`` off the UI thread."""

    def __init__(
        self,
        sources: list[Path],
        out_dir: Path,
        target: Format,
        options: ConversionOptions,
    ) -> None:
        super().__init__()
        self.sources = sources
        self.out_dir = out_dir
        self.target = target
        self.options = options
        self.signals = WorkerSignals()
        self._cancel = threading.Event()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        try:

            def progress(done: int, total: int, current: str) -> None:
                self.signals.progress.emit(done, total, current)

            results: list[ConversionResult] = convert_many(
                self.sources,
                self.out_dir,
                self.target,
                self.options,
                progress_cb=progress,
                cancel_event=self._cancel,
            )
            self.signals.finished.emit(results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Conversion worker failed")
            self.signals.error.emit(str(exc))
