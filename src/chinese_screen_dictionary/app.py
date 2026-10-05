import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PySide6.QtCore import QLockFile, QObject, QPoint, QThreadPool, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .capture import SelectionOverlay
from .config import Settings, data_dir
from .hotkeys import Hotkeys
from .resources import ensure_models, models_ready
from .service import ReadingService
from .storage import VocabularyStore
from .types import LookupSession
from .ui import Library, Note, SettingsDialog, SetupDialog
from .workers import Worker


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#f5d775"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#483a20"))
    painter.setFont(QFont("Microsoft YaHei UI", 35))
    painter.drawText(pixmap.rect(), 0x84, "中")
    painter.end()
    return QIcon(pixmap)


def set_startup(enabled: bool):
    if sys.platform != "win32":
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            if getattr(sys, "frozen", False):
                args = [sys.executable]
            else:
                executable = str(Path(sys.executable).with_name("pythonw.exe"))
                args = [executable, "-m", "chinese_screen_dictionary"]
            winreg.SetValueEx(key, "ChineseScreenDictionary", 0, winreg.REG_SZ, subprocess.list2cmdline(args))
        else:
            try:
                winreg.DeleteValue(key, "ChineseScreenDictionary")
            except FileNotFoundError:
                pass


class Controller(QObject):
    def __init__(self, application, root: Path):
        super().__init__()
        self.application = application
        self.root = root
        self.settings = Settings.load(root)
        self.store = VocabularyStore(root / "vocabulary.sqlite3")
        self.service = ReadingService(root)
        self.session = LookupSession()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.workers = set()
        self.overlays = []
        self.boxes = None
        self.setup_running = False
        self.quitting = False
        self.ready = models_ready(root)
        self.note = Note()
        self.note.dismissed.connect(self.dismiss)
        self.note.edited.connect(self.correct)
        self.note.direction_changed.connect(self.reorder)
        self.library = Library(self.store)
        self.setup = SetupDialog()
        self.setup.download_requested.connect(self.download_models)
        self.hotkeys = Hotkeys(self.toggle, self.show_library)
        application.installNativeEventFilter(self.hotkeys)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Chinese Screen Dictionary")
        menu = QMenu()
        for label, callback in (("Select Chinese text", self.toggle), ("Your dictionary", self.show_library),
                                ("Settings", self.show_settings), ("Download / repair models", self.show_setup),
                                ("About", self.about), ("Quit", self.quit)):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        try:
            self.hotkeys.configure(self.settings.capture_hotkey, self.settings.library_hotkey)
        except ValueError as exc:
            message = str(exc)
            QTimer.singleShot(0, lambda: self.hotkey_error(message))
        if not self.ready:
            QTimer.singleShot(0, self.show_setup)
        else:
            self.submit(("warmup", 0), lambda progress: self.service.prepare())

    def submit(self, tag, function):
        if tag[0] == "lookup":
            operation = function
            function = lambda progress: operation(progress) if self.session.accepts(tag[1]) else None
        worker = Worker(tag, function)
        self.workers.add(worker)
        worker.signals.finished.connect(self.worker_finished)
        worker.signals.failed.connect(self.worker_failed)
        worker.signals.progress.connect(self.setup.update_progress)
        self.pool.start(worker)

    def remove_worker(self, tag):
        for worker in list(self.workers):
            if worker.tag == tag:
                self.workers.discard(worker)

    def worker_finished(self, tag, value):
        self.remove_worker(tag)
        if self.quitting:
            return
        if tag[0] == "setup":
            self.setup_running = False
            self.ready = models_ready(self.root)
            self.service = ReadingService(self.root)
            self.setup.complete()
            self.submit(("warmup", 0), lambda progress: self.service.prepare())
        elif tag[0] == "lookup" and self.session.accepts(tag[1]):
            result, self.boxes = value
            error = ""
            try:
                # Blank corrections intentionally remove this lookup's old entries.
                self.store.replace_lookup(self.session.lookup_id, result)
            except Exception:
                logging.exception("Saving vocabulary failed")
                error = "Vocabulary could not be saved. Check free disk space."
            self.note.show_result(result, error)
            self.note.direction.setEnabled(bool(self.boxes))
            if self.library.isVisible():
                self.library.refresh()

    def worker_failed(self, tag, message):
        self.remove_worker(tag)
        if self.quitting:
            return
        if tag[0] == "setup":
            self.setup_running = False
            self.ready = models_ready(self.root)
            self.setup.failed(message)
        elif tag[0] == "lookup" and self.session.accepts(tag[1]):
            self.note.show_error("Could not read the selection: " + message)
        elif tag[0] == "warmup":
            self.tray.showMessage("Dictionary could not load", "Try Download / repair models from the tray.")

    def hotkey_error(self, message):
        QMessageBox.warning(None, "Shortcut unavailable", message + "\nYou can also select text from the tray menu.")
        self.show_settings()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_library()

    def toggle(self):
        if self.session.active:
            self.dismiss()
            return
        if not self.ready or self.setup_running:
            self.show_setup()
            return
        self.session.begin(str(uuid.uuid4()))
        self.boxes = None
        # Snapshot every monitor before putting an overlay on any of them.
        snapshots = [(screen, screen.grabWindow(0).toImage()) for screen in self.application.screens()]
        if any(image.isNull() for _, image in snapshots):
            self.dismiss()
            self.tray.showMessage("Capture unavailable", "Windows could not capture this screen. Try again outside protected content.")
            return
        current_screen = self.application.screenAt(QCursor.pos())
        for screen, image in snapshots:
            overlay = SelectionOverlay(screen, image, self.settings.selection_mode)
            overlay.selected.connect(self.selected)
            overlay.cancelled.connect(self.dismiss)
            overlay.mode_changed.connect(self.change_mode)
            overlay.started.connect(self.selection_started)
            self.overlays.append(overlay)
            overlay.show()
        for overlay in self.overlays:
            if overlay.target_screen == current_screen:
                overlay.activateWindow()
                overlay.setFocus()

    def selection_started(self, owner):
        for overlay in self.overlays:
            if overlay is not owner:
                overlay.blocked = True
                overlay.toolbar.hide()

    def change_mode(self, mode):
        self.settings.selection_mode = mode
        self.settings.save(self.root)
        for overlay in self.overlays:
            overlay.set_mode(mode, emit=False)

    def clear_overlays(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def selected(self, image, anchor, available):
        if not self.session.active:
            return
        self.clear_overlays()
        self.note.open_at(anchor, available)
        generation = self.session.generation
        service = self.service
        self.submit(("lookup", generation), lambda progress: service.lookup(image=image))

    def dismiss(self):
        self.session.cancel()
        self.clear_overlays()
        self.note.hide()
        self.note.result = None
        self.boxes = None

    def correct(self, text):
        if not self.session.active:
            return
        generation = self.session.revise()
        direction = self.note.direction.currentData()
        self.note.show_loading()
        service = self.service
        self.submit(("lookup", generation), lambda progress: service.lookup(text=text, direction=direction))

    def reorder(self, direction):
        if not self.session.active or self.boxes is None:
            return
        generation = self.session.revise()
        boxes = self.boxes
        self.note.show_loading("Updating reading direction…")
        service = self.service
        self.submit(("lookup", generation), lambda progress: service.lookup(boxes=boxes, direction=direction))

    def show_library(self):
        self.library.refresh()
        self.library.show()
        self.library.raise_()
        self.library.activateWindow()

    def show_settings(self):
        dialog = SettingsDialog(self.settings, self.save_settings)
        dialog.exec()

    def save_settings(self, candidate):
        old = self.settings
        self.hotkeys.configure(candidate.capture_hotkey, candidate.library_hotkey)
        try:
            if old.start_with_windows != candidate.start_with_windows:
                set_startup(candidate.start_with_windows)
            candidate.save(self.root)
        except Exception:
            self.hotkeys.configure(old.capture_hotkey, old.library_hotkey)
            if old.start_with_windows != candidate.start_with_windows:
                set_startup(old.start_with_windows)
            raise
        self.settings = candidate

    def show_setup(self):
        if not self.setup_running:
            self.setup.offer_download(repair=self.ready)
        self.setup.show()
        self.setup.raise_()
        self.setup.activateWindow()

    def download_models(self):
        if self.setup_running:
            return
        self.dismiss()
        self.setup_running = True
        self.setup.busy()
        self.submit(("setup", 0), lambda progress: ensure_models(self.root, progress))

    def about(self):
        QMessageBox.about(None, "Chinese Screen Dictionary", "<h3>Chinese Screen Dictionary 0.1</h3>"
            "<p>Free, local Chinese recognition, pinyin, and vocabulary.</p>"
            "<p>Dictionary: <a href='https://www.mdbg.net/chinese/dictionary?page=cedict'>CC-CEDICT / MDBG</a>, CC BY-SA 4.0. "
            "Recognition: RapidOCR / PaddleOCR. Translation: Argos Translate / CTranslate2.</p>"
            "<p>See THIRD_PARTY_NOTICES.md in the app folder for source and license details.</p>")

    def quit(self):
        self.quitting = True
        self.dismiss()
        self.hotkeys.close()
        self.application.removeNativeEventFilter(self.hotkeys)
        self.tray.hide()
        self.library.hide()
        self.setup.hide()
        # Active native model calls finish safely; never destroy their worker thread.
        self.pool.clear()
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.timeout.connect(self.finish_quit)
        self.shutdown_timer.start(100)
        self.finish_quit()

    def finish_quit(self):
        if self.pool.activeThreadCount() == 0:
            self.shutdown_timer.stop()
            self.store.close()
            self.application.quit()


def main():
    parser = argparse.ArgumentParser(description="Offline Chinese Screen Dictionary")
    parser.add_argument("--download-models", action="store_true")
    parser.add_argument("--self-test", type=Path, metavar="OUTPUT_DIR")
    args = parser.parse_args()
    root = data_dir()
    handler = RotatingFileHandler(root / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    if args.download_models:
        ensure_models(root, lambda message, percent: print(f"{percent}% {message}", flush=True))
        return
    if args.self_test:
        from .diagnostics import self_test
        self_test(root, args.self_test)
        return
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Chinese Screen Dictionary")
    app.setOrganizationName("ChineseScreenDictionary")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    lock = QLockFile(str(root / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Already running", "Chinese Screen Dictionary is already running. Look for the 中 icon in the system tray.")
        return
    controller = Controller(app, root)
    try:
        app.exec()
    finally:
        controller.hotkeys.close()
        controller.pool.waitForDone()
        lock.unlock()


if __name__ == "__main__":
    main()
