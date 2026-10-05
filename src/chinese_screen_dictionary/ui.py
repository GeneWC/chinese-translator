import html
import json
import unicodedata
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QTabBar, QTableWidget,
    QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from .config import Settings
from .types import Analysis

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 14px; color: #302d27; }
QDialog { background: #fbfaf5; }
QPushButton { background:#f8f3e5; border:1px solid #d4c9a6; border-radius:5px; padding:6px 12px; }
QPushButton:hover { background:#f4e7ba; }
QPushButton:disabled { color:#999; }
QLineEdit, QPlainTextEdit, QComboBox { background:#fffefa; border:1px solid #d4c9a6; border-radius:4px; padding:5px; }
QTextBrowser { border:0; background:transparent; }
QTableWidget { background:#fffefa; alternate-background-color:#f7f2e5; border:1px solid #e0d6b8; }
QHeaderView::section { background:#f4edd8; padding:7px; border:0; }
QTabBar::tab { padding:9px 18px; background:#eee7d5; }
QTabBar::tab:selected { background:#fff6ce; }
"""
COLORS = {1: "#c94338", 2: "#348047", 3: "#3066ac", 4: "#8551a3", 5: "#6f6b5d"}


def esc(text):
    return html.escape(str(text))


def colored_pinyin(text):
    marks = {"\u0304": 1, "\u0301": 2, "\u030c": 3, "\u0300": 4}
    spans = []
    for syllable in text.split():
        tone = next((marks[c] for c in unicodedata.normalize("NFD", syllable) if c in marks), 5)
        spans.append(f'<span style="color:{COLORS[tone]}">{esc(syllable)}</span>')
    return " ".join(spans)


def result_html(result: Analysis):
    parts = [f'<div style="font-family:Microsoft YaHei UI;font-size:25px">{esc(result.text).replace(chr(10), "<br>")}</div>',
             f'<p style="font-size:17px">{colored_pinyin(result.pinyin)}</p>']
    for warning in result.warnings:
        parts.append(f'<p style="color:#85561b">{esc(warning)}</p>')
    if result.translation:
        parts.append(f'<p style="color:#7e7359;font-size:11px">MACHINE TRANSLATION</p><p style="font-size:16px">{esc(result.translation)}</p>')
    if result.words:
        parts.append('<hr><p style="color:#7e7359;font-size:11px">WORDS &amp; PHRASES</p>')
    seen = set()
    for word in result.words:
        if word.key in seen:
            continue
        seen.add(word.key)
        alternate = word.traditional if word.surface == word.simplified else word.simplified
        alternate_html = f' <span style="color:#82765b;font-size:15px">{esc(alternate)}</span>' if alternate != word.surface else ""
        parts.append(f'<p><b style="font-family:Microsoft YaHei UI;font-size:21px">{esc(word.surface)}</b>{alternate_html}')
        if word.senses:
            for sense in word.senses:
                parts.append(f'<br><span style="font-size:15px">{colored_pinyin(sense.pinyin)}</span><br>{esc("; ".join(sense.definitions))}')
        else:
            parts.append(f'<br>{colored_pinyin(word.pinyin)}<br><i>No dictionary entry.</i>')
        parts.append('</p>')
    return "".join(parts)


def clamp_position(point: QPoint, size, available: QRect) -> QPoint:
    return QPoint(max(available.left(), min(point.x(), available.right()-size.width()+1)),
                  max(available.top(), min(point.y(), available.bottom()-size.height()+1)))


class DragLabel(QLabel):
    def mousePressEvent(self, event):
        self.offset = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            window = self.window()
            screen = QApplication.screenAt(event.globalPosition().toPoint()) or window.screen()
            window.move(clamp_position(event.globalPosition().toPoint()-self.offset, window.size(), screen.availableGeometry()))


class Note(QWidget):
    dismissed = Signal()
    edited = Signal(str)
    direction_changed = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("note")
        self.setWindowTitle("Chinese Screen Dictionary — lookup")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(STYLE + "QWidget#note { background:#fff7ce; border:1px solid #d6bf75; border-radius:8px; }")
        self.resize(440, 530)
        self.result = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        header = QHBoxLayout()
        title = DragLabel("中文  SCREEN DICTIONARY")
        title.setStyleSheet("font-size:11px; font-weight:600; color:#857343;")
        title.setCursor(Qt.CursorShape.SizeAllCursor)
        header.addWidget(title, 1)
        close = QPushButton("×")
        close.setToolTip("Dismiss (or press your capture shortcut)")
        close.setFixedWidth(32)
        close.clicked.connect(self.dismissed)
        header.addWidget(close)
        layout.addLayout(header)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.document().setDefaultFont(QFont("Segoe UI", 11))
        layout.addWidget(self.browser, 1)
        self.edit_panel = QWidget()
        edit_layout = QVBoxLayout(self.edit_panel)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        self.editor = QPlainTextEdit()
        self.editor.setMaximumHeight(95)
        edit_layout.addWidget(self.editor)
        apply_button = QPushButton("Apply correction")
        apply_button.clicked.connect(self.apply_edit)
        edit_layout.addWidget(apply_button)
        layout.addWidget(self.edit_panel)
        self.edit_panel.hide()
        controls = QHBoxLayout()
        self.edit_button = QPushButton("Edit text")
        self.edit_button.clicked.connect(self.toggle_editor)
        controls.addWidget(self.edit_button)
        self.direction = QComboBox()
        for label, value in (("Auto", "auto"), ("Horizontal", "horizontal"), ("Vertical", "vertical")):
            self.direction.addItem(label, value)
        self.direction.setToolTip("Reading direction — reorder the captured text")
        self.direction.currentIndexChanged.connect(lambda _: self.direction_changed.emit(self.direction.currentData()))
        controls.addWidget(self.direction)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy_result)
        controls.addWidget(self.copy_button)
        layout.addLayout(controls)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-size:11px;color:#82724b;")
        layout.addWidget(self.status)

    def open_at(self, anchor, available):
        self.resize(min(440, available.width()), min(570, available.height()))
        self.move(clamp_position(anchor + QPoint(14, 14), self.size(), available))
        self.direction.blockSignals(True)
        self.direction.setCurrentIndex(0)
        self.direction.blockSignals(False)
        self.result = None
        self.edit_panel.hide()
        self.show_loading("Reading selected text…")
        self.show()
        # Showing the widget can enlarge it to the layout's minimum size.
        self.move(clamp_position(anchor + QPoint(14, 14), self.size(), available))

    def show_loading(self, message="Updating lookup…"):
        self.browser.setHtml(f'<p style="font-size:18px">{esc(message)}</p><p>Press your capture shortcut to dismiss.</p>')
        self.status.setText("Processing on this computer")
        self.copy_button.setEnabled(False)
        self.edit_button.setEnabled(False)
        self.direction.setEnabled(False)

    def show_result(self, result: Analysis, save_error=""):
        self.result = result
        self.browser.setHtml(result_html(result))
        self.edit_button.setEnabled(True)
        self.copy_button.setEnabled(True)
        self.direction.setEnabled(True)
        count = len({w.key for w in result.words if w.save})
        self.status.setText(save_error or f"{count} vocabulary item{'s' if count != 1 else ''} saved · {result.direction} · {result.elapsed:.1f}s")

    def show_error(self, message):
        self.browser.setHtml(f'<p style="font-size:18px">{esc(message)}</p><p>Select again, or repair language models from the tray menu.</p>')
        self.status.setText("Nothing saved")
        self.direction.setEnabled(False)
        self.edit_button.setEnabled(False)

    def toggle_editor(self):
        if not self.result:
            return
        self.editor.setPlainText(self.result.text)
        self.edit_panel.setVisible(not self.edit_panel.isVisible())
        if self.edit_panel.isVisible():
            self.activateWindow()
            self.editor.setFocus()

    def apply_edit(self):
        text = self.editor.toPlainText().strip()
        self.edit_panel.hide()
        self.edited.emit(text)

    def copy_result(self):
        if self.result:
            QApplication.clipboard().setText(f"{self.result.text}\n{self.result.pinyin}\n{self.result.translation}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit()

    def closeEvent(self, event):
        self.dismissed.emit()
        event.accept()


class Library(QDialog):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.rows = []
        self.setWindowTitle("Your Chinese dictionary")
        self.setStyleSheet(STYLE)
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        title = QLabel("Your Chinese dictionary")
        title.setStyleSheet("font-size:25px;font-weight:600;padding:8px 0;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Words you look up most often appear first. Each selection counts once."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Chinese, pinyin, or English…")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.tabs = QTabBar()
        self.tabs.addTab("Words && phrases")
        self.tabs.addTab("Single characters")
        self.tabs.currentChanged.connect(self.refresh)
        layout.addWidget(self.tabs)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Chinese", "Pinyin", "English", "Lookups"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(3, 70)
        self.table.itemSelectionChanged.connect(self.show_context)
        layout.addWidget(self.table, 3)
        self.context = QTextBrowser()
        self.context.setMaximumHeight(200)
        layout.addWidget(self.context, 1)
        bottom = QHBoxLayout()
        self.counter = QLabel()
        bottom.addWidget(self.counter, 1)
        delete = QPushButton("Delete selected entry")
        delete.clicked.connect(self.delete_selected)
        bottom.addWidget(delete)
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self, *_):
        self.rows = self.store.list_entries(self.tabs.currentIndex() == 1, self.search.text())
        self.table.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            senses = json.loads(row["definitions"])
            meaning = "; ".join(d for sense in senses for d in sense["definitions"]) or "No dictionary entry"
            chinese = row["simplified"] if row["simplified"] == row["traditional"] else f'{row["simplified"]} / {row["traditional"]}'
            for j, value in enumerate((chinese, row["pinyin"], meaning, str(row["count"]))):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(i, j, item)
        self.counter.setText(f"{len(self.rows)} entries")
        self.context.setHtml("<p>Select a word to see where you encountered it.</p>" if self.rows else
            "<p>Your saved vocabulary will appear here after a lookup.</p>")

    def show_context(self):
        index = self.table.currentRow()
        if not 0 <= index < len(self.rows):
            return
        contexts = self.store.contexts(self.rows[index]["key"])
        self.context.setHtml("".join(f'<p><b>{esc(c["surface"])}</b> · {esc(c["created_at"][:10])}<br>{esc(c["text"])}<br>{esc(c["translation"])}</p>' for c in contexts))

    def delete_selected(self):
        index = self.table.currentRow()
        if 0 <= index < len(self.rows):
            word = self.rows[index]
            if QMessageBox.question(self, "Delete entry", f'Delete {word["simplified"]} and its lookup count?') == QMessageBox.StandardButton.Yes:
                self.store.delete_entry(word["key"])
                self.refresh()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, save_callback):
        super().__init__()
        self.settings = settings
        self.save_callback = save_callback
        self.setWindowTitle("Chinese Screen Dictionary — Settings")
        self.setStyleSheet(STYLE)
        self.resize(450, 240)
        form = QFormLayout(self)
        self.capture = QLineEdit(settings.capture_hotkey)
        self.library = QLineEdit(settings.library_hotkey)
        form.addRow("Capture / dismiss", self.capture)
        form.addRow("Open dictionary", self.library)
        hint = QLabel("Use Ctrl or Alt with a letter, number, or F1–F11.")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.startup = QCheckBox("Start quietly when I sign in to Windows")
        self.startup.setChecked(settings.start_with_windows)
        form.addRow(self.startup)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#a23a29;")
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        candidate = Settings(self.capture.text().strip(), self.library.text().strip(),
                             self.settings.selection_mode, self.startup.isChecked())
        try:
            self.save_callback(candidate)
        except Exception as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class SetupDialog(QDialog):
    download_requested = Signal()

    def __init__(self):
        super().__init__()
        self.done = False
        self.setWindowTitle("Set up Chinese Screen Dictionary")
        self.setStyleSheet(STYLE)
        self.resize(490, 260)
        layout = QVBoxLayout(self)
        title = QLabel("Read Chinese anywhere on your screen")
        title.setStyleSheet("font-size:21px;font-weight:600;")
        title.setWordWrap(True)
        layout.addWidget(title)
        info = QLabel("Download the free recognition and translation models once. After setup, selections are processed entirely on your computer. No account or API key is needed.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.label = QLabel("Ready to download language models.")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.button = QPushButton("Download models")
        self.button.clicked.connect(self.clicked)
        layout.addWidget(self.button)

    def clicked(self):
        if self.done:
            self.accept()
        else:
            self.download_requested.emit()

    def offer_download(self, repair=False):
        self.done = False
        self.button.setEnabled(True)
        self.button.setText("Verify / repair models" if repair else "Download models")
        self.label.setText("Verify existing models and repair missing or damaged files." if repair else
                           "One-time download: 228 MiB. About 400 MiB of disk space is needed.")

    def busy(self):
        self.button.setEnabled(False)
        self.label.setText("Checking language models…")

    def update_progress(self, message, percent):
        self.label.setText(message)
        self.progress.setValue(percent)

    def failed(self, message):
        self.label.setText("Download could not finish: " + message)
        self.button.setText("Retry download")
        self.button.setEnabled(True)

    def complete(self):
        self.done = True
        self.progress.setValue(100)
        self.label.setText("Ready. Use your capture shortcut to select Chinese text, or open the dictionary from the tray.")
        self.button.setEnabled(True)
        self.button.setText("Start reading")
