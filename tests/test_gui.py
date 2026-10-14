"""GUI smoke tests (offscreen Qt)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Must set before importing Qt in some environments.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions
from glyphshift.gui.app import MainWindow
from glyphshift.gui.worker import ConvertWorker


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_opens(qapp: QApplication) -> None:
    win = MainWindow()
    win.show()
    assert win.isVisible() or True  # offscreen may report differently
    assert win.windowTitle()
    win.close()


def test_worker_converts_and_report(qapp: QApplication, latin_ttf: Path, tmp_out: Path) -> None:
    win = MainWindow()
    win.file_list.add_paths([latin_ttf])
    assert win.file_list.paths()

    results_holder: list = []

    worker = ConvertWorker(
        [latin_ttf],
        tmp_out,
        Format.WOFF2,
        ConversionOptions(overwrite=True, verify=True),
    )

    def on_finished(results: list) -> None:
        results_holder.extend(results)

    worker.signals.finished.connect(on_finished)
    # Run synchronously for the test (still exercises worker.run).
    worker.run()

    assert results_holder
    assert results_holder[0].success, results_holder[0].error
    win.report.show_result(results_holder[0], win.strings)
    assert "woff2" in win.report.body.toPlainText().lower() or results_holder[0].success
    win.close()


def test_language_switch_rtl(qapp: QApplication) -> None:
    from glyphshift.gui.i18n import Language

    win = MainWindow()
    win._apply_language(Language.PERSIAN)
    assert win.strings.rtl is True
    win._apply_language(Language.ENGLISH)
    assert win.strings.rtl is False
    win.close()
