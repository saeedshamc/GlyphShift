"""Reusable GUI widgets: drop zone, file list, preview, report view."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from glyphshift.core.formats import detect_format
from glyphshift.core.info import inspect_font
from glyphshift.core.models import ConversionResult
from glyphshift.gui.i18n import Strings

logger = logging.getLogger(__name__)

FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc"}


def collect_font_paths(paths: list[Path], *, recursive: bool = True) -> list[Path]:
    found: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix.lower() in FONT_SUFFIXES:
            found.append(p)
        elif p.is_dir():
            globber = p.rglob if recursive else p.glob
            for pattern in ("*.ttf", "*.otf", "*.woff", "*.woff2", "*.ttc", "*.otc"):
                found.extend(globber(pattern))
    # unique
    seen: set[Path] = set()
    out: list[Path] = []
    for f in found:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            out.append(f)
    return out


class DropZone(QLabel):
    """Drag-and-drop / click-to-browse zone."""

    files_dropped = Signal(list)  # list[Path]
    browse_requested = Signal()

    def __init__(self, strings: Strings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(120)
        self.setWordWrap(True)
        self.apply_strings(strings)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #888; border-radius: 8px; padding: 16px; }"
        )

    def apply_strings(self, strings: Strings) -> None:
        self.setText(strings.drop_hint)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))
        if paths:
            self.files_dropped.emit(paths)


class FileListPanel(QWidget):
    """List of queued fonts with format / size / glyph count."""

    selection_changed = Signal(object)  # Path | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.currentRowChanged.connect(self._on_row)
        layout.addWidget(self.list)

    def _on_row(self, row: int) -> None:
        if 0 <= row < len(self._paths):
            self.selection_changed.emit(self._paths[row])
        else:
            self.selection_changed.emit(None)

    def add_paths(self, paths: list[Path]) -> None:
        for path in collect_font_paths(paths):
            if path in self._paths:
                continue
            try:
                info = inspect_font(path)
                det = detect_format(path, deep=False)
                size_kb = path.stat().st_size / 1024
                text = (
                    f"{path.name}  ·  {det.format.value.upper()}  ·  "
                    f"{size_kb:.1f} KiB  ·  {info.glyph_count} glyphs"
                )
            except Exception as exc:  # noqa: BLE001
                text = f"{path.name}  ·  error: {exc}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.addItem(item)
            self._paths.append(path)

    def clear(self) -> None:
        self.list.clear()
        self._paths.clear()
        self.selection_changed.emit(None)

    def paths(self) -> list[Path]:
        return list(self._paths)

    def set_status_icon(self, path: Path, ok: bool | None) -> None:
        for i, p in enumerate(self._paths):
            if p.resolve() == path.resolve():
                item = self.list.item(i)
                if item is None:
                    return
                base = item.text().lstrip("✓✗• ").strip()
                if ok is True:
                    item.setText(f"✓ {base}")
                elif ok is False:
                    item.setText(f"✗ {base}")
                else:
                    item.setText(f"• {base}")
                return


class ReportView(QWidget):
    """Per-file verification report."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("")
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        layout.addWidget(self.title)
        layout.addWidget(self.body)
        self._btn_row = QHBoxLayout()
        self.open_btn = QPushButton()
        self.css_btn = QPushButton()
        self._btn_row.addWidget(self.open_btn)
        self._btn_row.addWidget(self.css_btn)
        self._btn_row.addStretch()
        layout.addLayout(self._btn_row)
        self._last_result: ConversionResult | None = None

    def apply_strings(self, strings: Strings) -> None:
        self.open_btn.setText(strings.open_folder)
        self.css_btn.setText(strings.copy_css)

    def show_result(self, result: ConversionResult, strings: Strings) -> None:
        self._last_result = result
        if result.success and result.verify_report and result.verify_report.passed:
            self.title.setText(f"✓ {strings.verification_passed}")
            self.title.setStyleSheet("color: green; font-weight: bold;")
        elif result.success:
            self.title.setText(f"✓ {result.output_path}")
            self.title.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.title.setText(f"✗ {result.error or strings.verification_failed}")
            self.title.setStyleSheet("color: red; font-weight: bold;")

        lines: list[str] = []
        if result.output_path:
            lines.append(f"Output: {result.output_path}")
        lines.append(f"Lossless: {result.lossless}")
        for w in result.warnings:
            lines.append(f"WARNING: {w}")
        if result.verify_report:
            for iss in result.verify_report.issues:
                lines.append(f"[{iss.severity.value}] {iss.code}: {iss.message}")
            if not result.verify_report.issues:
                lines.append(strings.verification_passed)
        self.body.setPlainText("\n".join(lines))

    def last_result(self) -> ConversionResult | None:
        return self._last_result


class PreviewPanel(QWidget):
    """Side-by-side source / converted text preview."""

    def __init__(self, strings: Strings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._strings = strings
        self._src_font_id = -1
        self._dst_font_id = -1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sample_btns = QHBoxLayout()
        self.btn_latin = QPushButton("Latin")
        self.btn_persian = QPushButton("فارسی")
        self.btn_digits = QPushButton("۰۱۲۳")
        self.btn_zwnj = QPushButton("ZWNJ")
        self.btn_arabic = QPushButton("عربي")
        for b in (
            self.btn_latin,
            self.btn_persian,
            self.btn_digits,
            self.btn_zwnj,
            self.btn_arabic,
        ):
            self.sample_btns.addWidget(b)
        layout.addLayout(self.sample_btns)

        self.note = QLabel("")
        layout.addWidget(self.note)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.src_edit = QPlainTextEdit()
        self.dst_edit = QPlainTextEdit()
        self.src_label = QLabel(strings.preview_source)
        self.dst_label = QLabel(strings.preview_converted)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(self.src_label)
        left_l.addWidget(self.src_edit)
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.addWidget(self.dst_label)
        right_l.addWidget(self.dst_edit)
        split.addWidget(left)
        split.addWidget(right)
        layout.addWidget(split)

        self.btn_latin.clicked.connect(lambda: self.set_sample(strings.sample_latin, rtl=False))
        self.btn_persian.clicked.connect(
            lambda: self.set_sample(strings.sample_persian, rtl=True)
        )
        self.btn_digits.clicked.connect(
            lambda: self.set_sample(strings.sample_digits, rtl=True)
        )
        self.btn_zwnj.clicked.connect(lambda: self.set_sample(strings.sample_zwnj, rtl=True))
        self.btn_arabic.clicked.connect(
            lambda: self.set_sample(strings.sample_arabic, rtl=True)
        )
        self.set_sample(strings.sample_persian, rtl=True)

    def apply_strings(self, strings: Strings) -> None:
        self._strings = strings
        self.src_label.setText(strings.preview_source)
        self.dst_label.setText(strings.preview_converted)

    def set_sample(self, text: str, *, rtl: bool) -> None:
        direction = Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        for edit in (self.src_edit, self.dst_edit):
            edit.setPlainText(text)
            edit.setLayoutDirection(direction)

    def _load_font_data(self, data: bytes) -> tuple[int, str | None]:
        font_id = QFontDatabase.addApplicationFontFromData(data)
        if font_id < 0:
            return -1, None
        families = QFontDatabase.applicationFontFamilies(font_id)
        return font_id, families[0] if families else None

    def load_source(self, path: Path | None) -> None:
        if self._src_font_id >= 0:
            QFontDatabase.removeApplicationFont(self._src_font_id)
            self._src_font_id = -1
        if path is None or not path.is_file():
            return
        try:
            data = path.read_bytes()
            # Qt often cannot load WOFF2 — unwrap for preview.
            if path.suffix.lower() == ".woff2" or data[:4] == b"wOF2":
                data = self._unwrap_for_preview(path)
                self.note.setText(self._strings.preview_woff2_note)
            else:
                self.note.setText("")
            font_id, family = self._load_font_data(data)
            self._src_font_id = font_id
            if family:
                font = QFont(family, 18)
                self.src_edit.setFont(font)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Preview source failed: %s", exc)
            self.note.setText(str(exc))

    def load_converted(self, path: Path | None) -> None:
        if self._dst_font_id >= 0:
            QFontDatabase.removeApplicationFont(self._dst_font_id)
            self._dst_font_id = -1
        if path is None or not path.is_file():
            return
        try:
            data = path.read_bytes()
            if path.suffix.lower() == ".woff2" or data[:4] == b"wOF2":
                data = self._unwrap_for_preview(path)
                self.note.setText(self._strings.preview_woff2_note)
            font_id, family = self._load_font_data(data)
            self._dst_font_id = font_id
            if family:
                font = QFont(family, 18)
                self.dst_edit.setFont(font)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Preview converted failed: %s", exc)

    @staticmethod
    def _unwrap_for_preview(path: Path) -> bytes:
        """Return sfnt bytes for Qt preview (WOFF/WOFF2 → raw)."""
        from fontTools.ttLib import TTFont
        import io

        font = TTFont(str(path), recalcTimestamp=False, recalcBBoxes=False)
        try:
            font.flavor = None
            buf = io.BytesIO()
            font.save(buf)
            return buf.getvalue()
        finally:
            font.close()


class CoveragePanel(QWidget):
    """Show mapped codepoint count and notable Unicode blocks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def show_path(self, path: Path | None, title: str = "Coverage") -> None:
        if path is None or not path.is_file():
            self.label.setText("")
            return
        try:
            info = inspect_font(path)
            flags = []
            if info.has_arabic:
                flags.append("Arabic")
            if info.has_persian_digits:
                flags.append("Persian digits")
            if info.has_zwnj:
                flags.append("ZWNJ")
            if info.has_gsub:
                flags.append("GSUB")
            if info.has_gpos:
                flags.append("GPOS")
            blocks = ", ".join(info.unicode_blocks) or "—"
            self.label.setText(
                f"{title}: {info.mapped_codepoints} codepoints · "
                f"scripts={', '.join(info.scripts) or '—'} · "
                f"blocks={blocks} · flags={', '.join(flags) or '—'}"
            )
        except Exception as exc:  # noqa: BLE001
            self.label.setText(str(exc))
