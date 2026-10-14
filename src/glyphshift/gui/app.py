"""GlyphShift main window and application entry point."""

from __future__ import annotations

import contextlib
import logging
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtGui import QAction, QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from glyphshift import __version__
from glyphshift.core.css import font_face_bundle
from glyphshift.core.formats import Format, OutlineType, conversion_is_lossless, detect_format
from glyphshift.core.info import inspect_font
from glyphshift.core.models import ConversionOptions, ConversionResult
from glyphshift.core.profiles import apply_profile
from glyphshift.core.variable import format_instance_spec, list_axes
from glyphshift.gui.i18n import Language, Strings, get_strings
from glyphshift.gui.widgets import (
    CoveragePanel,
    DropZone,
    FileListPanel,
    PreviewPanel,
    ReportView,
)
from glyphshift.gui.worker import ConvertWorker

logger = logging.getLogger(__name__)


def _setup_file_logging() -> Path:
    try:
        from platformdirs import user_log_dir

        log_dir = Path(user_log_dir("GlyphShift", "GlyphShift"))
    except Exception:
        log_dir = Path.home() / ".glyphshift" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "glyphshift-gui.log"
    root = logging.getLogger()
    if not any(
        isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_file)
        for h in root.handlers
    ):
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(fh)
        root.setLevel(logging.INFO)
    return log_file


def open_in_file_manager(path: Path) -> None:
    """Open a folder (or file's parent) in the OS file manager."""
    target = path if path.is_dir() else path.parent
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except Exception:
        logger.exception("Failed to open folder %s", target)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._log_file = _setup_file_logging()
        self.settings = QSettings("GlyphShift", "GlyphShift")
        lang_code = self.settings.value("language", Language.ENGLISH.value)
        self.strings: Strings = get_strings(str(lang_code))
        self.pool = QThreadPool.globalInstance()
        self._worker: ConvertWorker | None = None
        self._results: list[ConversionResult] = []

        self.setWindowTitle(f"{self.strings.app_title} {__version__}")
        self.resize(1100, 720)
        self._build_ui()
        self._load_settings()
        self._apply_language(self.strings.language)
        self._update_lossless_indicator()

    def _build_ui(self) -> None:
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", Language.ENGLISH.value)
        self.lang_combo.addItem("فارسی", Language.PERSIAN.value)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        toolbar.addWidget(QLabel("  "))
        self.lang_label = QLabel()
        toolbar.addWidget(self.lang_label)
        toolbar.addWidget(self.lang_combo)
        toolbar.addSeparator()
        self.info_action = QAction("Info", self)
        self.info_action.triggered.connect(self._show_font_info)
        toolbar.addAction(self.info_action)
        self.history_action = QAction("History", self)
        self.history_action.triggered.connect(self._show_history)
        toolbar.addAction(self.history_action)
        toolbar.addSeparator()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Auto", "auto")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.theme_label = QLabel()
        toolbar.addWidget(self.theme_label)
        toolbar.addWidget(self.theme_combo)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        left = QVBoxLayout()
        self.drop = DropZone(self.strings)
        self.drop.files_dropped.connect(self._on_files_dropped)
        self.drop.browse_requested.connect(self._browse_files)
        left.addWidget(self.drop)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton()
        self.clear_btn = QPushButton()
        self.add_btn.clicked.connect(self._browse_files)
        self.clear_btn.clicked.connect(self._clear_files)
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.clear_btn)
        left.addLayout(btn_row)

        self.file_list = FileListPanel()
        self.file_list.selection_changed.connect(self._on_selection)
        left.addWidget(self.file_list, stretch=1)

        form = QFormLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("—", "")
        self.profile_combo.addItem("web", "web")
        self.profile_combo.addItem("desktop", "desktop")
        self.profile_combo.addItem("lossless", "lossless")
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        form.addRow(QLabel(), self.profile_combo)
        self.profile_label = form.itemAt(0, QFormLayout.ItemRole.LabelRole).widget()

        self.target_combo = QComboBox()
        for fmt in (Format.TTF, Format.OTF, Format.WOFF, Format.WOFF2):
            self.target_combo.addItem(fmt.value.upper(), fmt.value)
        self.target_combo.currentIndexChanged.connect(self._update_lossless_indicator)
        form.addRow(QLabel(), self.target_combo)
        self.target_label = form.itemAt(1, QFormLayout.ItemRole.LabelRole).widget()

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("")
        self.out_browse = QPushButton()
        self.out_browse.clicked.connect(self._browse_out)
        out_row.addWidget(self.out_edit)
        out_row.addWidget(self.out_browse)
        form.addRow(QLabel(), out_row)
        self.out_label = form.itemAt(2, QFormLayout.ItemRole.LabelRole).widget()
        left.addLayout(form)

        self.lossless_label = QLabel()
        self.lossless_label.setWordWrap(True)
        left.addWidget(self.lossless_label)

        self.axes_box = QGroupBox()
        axes_outer = QVBoxLayout(self.axes_box)
        self.use_instance_cb = QCheckBox("Instantiate (lossy)")
        self.use_instance_cb.setChecked(False)
        axes_outer.addWidget(self.use_instance_cb)
        self.axes_form = QWidget()
        self.axes_layout = QFormLayout(self.axes_form)
        axes_outer.addWidget(self.axes_form)
        self._axis_sliders: dict[str, QSlider] = {}
        self.axes_box.setVisible(False)
        left.addWidget(self.axes_box)

        self.advanced = QGroupBox()
        self.advanced.setCheckable(True)
        self.advanced.setChecked(False)
        adv_form = QFormLayout(self.advanced)
        self.max_err = QDoubleSpinBox()
        self.max_err.setRange(0.1, 10.0)
        self.max_err.setSingleStep(0.1)
        self.max_err.setValue(1.0)
        self.reverse_dir = QCheckBox()
        self.reverse_dir.setChecked(True)
        self.verify_cb = QCheckBox()
        self.verify_cb.setChecked(True)
        self.overwrite_cb = QCheckBox()
        self.preserve_flavor_cb = QCheckBox()
        self.preserve_flavor_cb.setChecked(True)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(1)
        self.ttc_index = QSpinBox()
        self.ttc_index.setRange(-1, 64)
        self.ttc_index.setValue(-1)
        self.ttc_index.setSpecialValueText("all")
        adv_form.addRow(QLabel("max_err"), self.max_err)
        adv_form.addRow(self.reverse_dir)
        adv_form.addRow(self.verify_cb)
        adv_form.addRow(self.overwrite_cb)
        adv_form.addRow(self.preserve_flavor_cb)
        adv_form.addRow(QLabel("workers"), self.workers_spin)
        adv_form.addRow(QLabel("ttc"), self.ttc_index)
        self._adv_max_err_label = adv_form.itemAt(0, QFormLayout.ItemRole.LabelRole).widget()
        self._adv_workers_label = adv_form.itemAt(5, QFormLayout.ItemRole.LabelRole).widget()
        self._adv_ttc_label = adv_form.itemAt(6, QFormLayout.ItemRole.LabelRole).widget()
        left.addWidget(self.advanced)

        action_row = QHBoxLayout()
        self.convert_btn = QPushButton()
        self.cancel_btn = QPushButton()
        self.cancel_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self._start_convert)
        self.cancel_btn.clicked.connect(self._cancel_convert)
        action_row.addWidget(self.convert_btn)
        action_row.addWidget(self.cancel_btn)
        left.addLayout(action_row)

        self.progress = QProgressBar()
        self.status_label = QLabel()
        left.addWidget(self.progress)
        left.addWidget(self.status_label)

        right = QVBoxLayout()
        self.preview = PreviewPanel(self.strings)
        right.addWidget(self.preview, stretch=2)
        self.coverage = CoveragePanel()
        right.addWidget(self.coverage)
        self.report = ReportView()
        self.report.open_btn.clicked.connect(self._open_output_folder)
        self.report.css_btn.clicked.connect(self._copy_css)
        right.addWidget(self.report, stretch=1)

        root.addLayout(left, stretch=2)
        root.addLayout(right, stretch=3)

    def _apply_language(self, lang: Language) -> None:
        self.strings = get_strings(lang)
        rtl = self.strings.rtl
        direction = Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        self.setLayoutDirection(direction)
        QApplication.instance().setLayoutDirection(direction)  # type: ignore[union-attr]

        s = self.strings
        self.setWindowTitle(f"{s.app_title} {__version__}")
        self.drop.apply_strings(s)
        self.add_btn.setText(s.add_files)
        self.clear_btn.setText(s.clear_list)
        self.profile_label.setText(s.profile)
        self.target_label.setText(s.target_format)
        self.out_label.setText(s.output_dir)
        self.out_edit.setPlaceholderText(s.same_as_source)
        self.out_browse.setText(s.browse)
        self.advanced.setTitle(s.advanced)
        self.axes_box.setTitle(s.axes)
        self._adv_max_err_label.setText(s.max_err)
        self.reverse_dir.setText(s.reverse_direction)
        self.verify_cb.setText(s.verify)
        self.overwrite_cb.setText(s.overwrite)
        self.preserve_flavor_cb.setText(s.preserve_flavor)
        self._adv_workers_label.setText(s.workers)
        self._adv_ttc_label.setText(s.ttc_index)
        self.convert_btn.setText(s.convert)
        self.cancel_btn.setText(s.cancel)
        self.lang_label.setText(s.language_label)
        self.theme_label.setText(s.theme)
        self.info_action.setText(s.font_info)
        self.history_action.setText(s.history)
        self.preview.apply_strings(s)
        self.report.apply_strings(s)
        self.status_label.setText(s.status_ready)
        self._update_lossless_indicator()

        # Sync combo without re-entrancy
        idx = self.lang_combo.findData(lang.value)
        if idx >= 0 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)

    def _on_language_changed(self) -> None:
        code = self.lang_combo.currentData()
        self.settings.setValue("language", code)
        self._apply_language(Language(code))

    def _load_settings(self) -> None:
        self.out_edit.setText(str(self.settings.value("out_dir", "")))
        target = str(self.settings.value("target", "woff2"))
        idx = self.target_combo.findData(target)
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)
        profile = str(self.settings.value("profile", ""))
        pidx = self.profile_combo.findData(profile)
        if pidx >= 0:
            self.profile_combo.setCurrentIndex(pidx)
        self.max_err.setValue(float(self.settings.value("max_err", 1.0)))
        self.verify_cb.setChecked(self.settings.value("verify", True, type=bool))
        self.overwrite_cb.setChecked(self.settings.value("overwrite", False, type=bool))
        self.reverse_dir.setChecked(self.settings.value("reverse_direction", True, type=bool))
        self.preserve_flavor_cb.setChecked(self.settings.value("preserve_flavor", True, type=bool))
        self.workers_spin.setValue(int(self.settings.value("workers", 1)))
        theme = str(self.settings.value("theme", "auto"))
        tidx = self.theme_combo.findData(theme)
        if tidx >= 0:
            self.theme_combo.setCurrentIndex(tidx)
        self._apply_theme(theme)

    def _save_settings(self) -> None:
        self.settings.setValue("out_dir", self.out_edit.text())
        self.settings.setValue("target", self.target_combo.currentData())
        self.settings.setValue("profile", self.profile_combo.currentData())
        self.settings.setValue("max_err", self.max_err.value())
        self.settings.setValue("verify", self.verify_cb.isChecked())
        self.settings.setValue("overwrite", self.overwrite_cb.isChecked())
        self.settings.setValue("reverse_direction", self.reverse_dir.isChecked())
        self.settings.setValue("preserve_flavor", self.preserve_flavor_cb.isChecked())
        self.settings.setValue("workers", self.workers_spin.value())
        self.settings.setValue("language", self.lang_combo.currentData())
        self.settings.setValue("theme", self.theme_combo.currentData())

    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)

    def _on_files_dropped(self, paths: list) -> None:
        self.file_list.add_paths(paths)
        self._update_lossless_indicator()

    def _browse_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.strings.add_files,
            "",
            "Fonts (*.ttf *.otf *.woff *.woff2 *.ttc *.otc);;All (*.*)",
        )
        if files:
            self.file_list.add_paths([Path(f) for f in files])
            self._update_lossless_indicator()

    def _clear_files(self) -> None:
        self.file_list.clear()
        self._update_lossless_indicator()

    def _browse_out(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, self.strings.output_dir)
        if directory:
            self.out_edit.setText(directory)

    def _current_target(self) -> Format:
        return Format.from_string(str(self.target_combo.currentData()))

    def _update_lossless_indicator(self) -> None:
        paths = self.file_list.paths()
        target = self._current_target()
        if not paths:
            self.lossless_label.setText("")
            return
        # Use first file as representative
        try:
            det = detect_format(paths[0], deep=True)
            lossless = conversion_is_lossless(det.format, det.outline, target)
            if target == Format.TTF and det.outline in (OutlineType.CFF, OutlineType.CFF2):
                lossless = False
            if target == Format.OTF and det.outline == OutlineType.GLYF:
                lossless = False
        except Exception:
            lossless = True
        if lossless:
            self.lossless_label.setText(self.strings.lossless)
            self.lossless_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lossless_label.setText(f"{self.strings.lossy}\n{self.strings.lossy_warning}")
            self.lossless_label.setStyleSheet("color: #b86e00; font-weight: bold;")

    def _on_selection(self, path: object) -> None:
        p = path if isinstance(path, Path) else None
        self.preview.load_source(p)
        self.coverage.show_path(p, self.strings.coverage)
        self._rebuild_axis_sliders(p)
        # If we have a matching result, show converted preview
        if p is not None:
            for r in self._results:
                if r.input_path.resolve() == p.resolve() and r.output_path:
                    self.preview.load_converted(r.output_path)
                    self.report.show_result(r, self.strings)
                    return

    def _rebuild_axis_sliders(self, path: Path | None) -> None:
        while self.axes_layout.rowCount():
            self.axes_layout.removeRow(0)
        self._axis_sliders.clear()
        if path is None:
            self.axes_box.setVisible(False)
            return
        try:
            axes = list_axes(path)
        except Exception:
            axes = []
        if not axes:
            self.axes_box.setVisible(False)
            return
        self.axes_box.setVisible(True)
        for axis in axes:
            slider = QSlider(Qt.Orientation.Horizontal)
            lo = int(axis["min"])
            hi = int(axis["max"])
            default = int(axis["default"])
            slider.setMinimum(lo)
            slider.setMaximum(max(hi, lo + 1))
            slider.setValue(default)
            slider.setToolTip(f"{axis['tag']}: {lo}…{hi}")
            self.axes_layout.addRow(QLabel(axis["tag"]), slider)
            self._axis_sliders[axis["tag"]] = slider

    def _on_profile_changed(self) -> None:
        profile = self.profile_combo.currentData()
        if not profile:
            self._update_lossless_indicator()
            return
        fmt, _opts = apply_profile(str(profile), target=self._current_target())
        idx = self.target_combo.findData(fmt.value)
        if idx >= 0:
            self.target_combo.blockSignals(True)
            self.target_combo.setCurrentIndex(idx)
            self.target_combo.blockSignals(False)
        self._update_lossless_indicator()

    def _on_theme_changed(self) -> None:
        theme = str(self.theme_combo.currentData())
        self.settings.setValue("theme", theme)
        self._apply_theme(theme)

    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if theme == "dark":
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
            palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
            palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
            app.setPalette(palette)
        elif theme == "light":
            app.setPalette(app.style().standardPalette())  # type: ignore[union-attr]
        else:
            # Auto: restore style default (OS-influenced where available)
            app.setPalette(app.style().standardPalette())  # type: ignore[union-attr]

    def _options(self) -> ConversionOptions:
        idx = self.ttc_index.value()
        instance = None
        if self._axis_sliders:
            coords = {tag: float(sl.value()) for tag, sl in self._axis_sliders.items()}
            instance = format_instance_spec(coords)
        if not self.use_instance_cb.isChecked():
            instance = None
        opts = ConversionOptions(
            max_err=self.max_err.value(),
            reverse_direction=self.reverse_dir.isChecked(),
            overwrite=self.overwrite_cb.isChecked(),
            verify=self.verify_cb.isChecked(),
            keep_on_fail=False,
            ttc_index=None if idx < 0 else idx,
            instance=instance,
            workers=self.workers_spin.value(),
            preserve_flavor_data=self.preserve_flavor_cb.isChecked(),
            record_history=True,
        )
        profile = self.profile_combo.currentData()
        if profile:
            _fmt, opts = apply_profile(str(profile), opts, target=self._current_target())
        return opts

    def _start_convert(self) -> None:
        paths = self.file_list.paths()
        if not paths:
            QMessageBox.warning(self, self.strings.error_title, self.strings.no_files)
            return
        out_text = self.out_edit.text().strip()
        out_dir = Path(out_text) if out_text else paths[0].parent
        out_dir.mkdir(parents=True, exist_ok=True)

        self._save_settings()
        self._results = []
        self.progress.setValue(0)
        self.progress.setMaximum(max(len(paths), 1))
        self.status_label.setText(self.strings.status_working)
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        worker = ConvertWorker(paths, out_dir, self._current_target(), self._options())
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        self._worker = worker
        self.pool.start(worker)

    def _cancel_convert(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        self.status_label.setText(self.strings.status_cancelled)

    def _on_progress(self, done: int, total: int, current: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        if current:
            self.status_label.setText(f"{self.strings.status_working} {current}")

    def _on_finished(self, results: list) -> None:
        self._results = list(results)
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setValue(self.progress.maximum())
        self.status_label.setText(self.strings.status_done)
        for r in self._results:
            self.file_list.set_status_icon(r.input_path, r.success)
        if self._results:
            self.report.show_result(self._results[-1], self.strings)
            last = self._results[-1]
            if last.output_path:
                self.preview.load_converted(last.output_path)
                self.coverage.show_path(last.output_path, self.strings.coverage)

    def _on_error(self, message: str) -> None:
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        logger.error("Worker error: %s", message)
        QMessageBox.critical(self, self.strings.error_title, message)

    def _open_output_folder(self) -> None:
        result = self.report.last_result()
        if result and result.output_path:
            open_in_file_manager(result.output_path)

    def _copy_css(self) -> None:
        result = self.report.last_result()
        if not result or not result.output_path:
            return
        path = result.output_path
        try:
            css = font_face_bundle(path)
        except Exception as exc:
            QMessageBox.critical(self, self.strings.error_title, str(exc))
            return
        QGuiApplication.clipboard().setText(css)
        self.status_label.setText(self.strings.copied)

    def _show_font_info(self) -> None:
        paths = self.file_list.paths()
        row = self.file_list.list.currentRow()
        if not paths:
            QMessageBox.information(self, self.strings.font_info, self.strings.no_files)
            return
        path = paths[row] if 0 <= row < len(paths) else paths[0]
        try:
            info = inspect_font(path)
            text = "\n".join(f"{k}: {v}" for k, v in info.to_dict().items())
            QMessageBox.information(self, self.strings.font_info, text)
        except Exception as exc:
            logger.exception("Font info failed")
            QMessageBox.critical(self, self.strings.error_title, str(exc))

    def _show_history(self) -> None:
        from glyphshift.core.history import list_history, undo_entry

        entries = list_history(limit=30)
        dlg = QMessageBox(self)
        dlg.setWindowTitle(self.strings.history)
        if not entries:
            dlg.setText("No history.")
            dlg.exec()
            return
        lines = [
            f"{e.id[:8]}  {'OK' if e.success else 'FAIL'}  {e.input_path} → {e.output_path or '-'}"
            for e in entries
        ]
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(lines))
        box = QMessageBox(self)
        box.setWindowTitle(self.strings.history)
        box.setText(self.strings.history)
        box.setInformativeText("Latest conversions (undo via CLI: glyphshift history --undo ID)")
        layout = box.layout()
        if layout is not None:
            layout.addWidget(text, 1, 0, 1, layout.columnCount())
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Abort)
        box.button(QMessageBox.StandardButton.Abort).setText("Undo latest")
        result = box.exec()
        if result == QMessageBox.StandardButton.Abort and entries:
            try:
                undo_entry(entries[0].id, delete_output=True)
                self.status_label.setText(f"Undone {entries[0].id[:8]}")
            except Exception as exc:
                QMessageBox.critical(self, self.strings.error_title, str(exc))


def main() -> int:
    """Entry point for ``glyphshift-gui``."""
    # Offscreen-friendly; respects QT_QPA_PLATFORM.
    with contextlib.suppress(Exception):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setApplicationName("GlyphShift")
    app.setOrganizationName("GlyphShift")
    app.setApplicationVersion(__version__)

    # Follow OS light/dark via style; Fusion is predictable cross-platform.
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    try:
        return app.exec()
    except Exception:
        logging.getLogger(__name__).error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
