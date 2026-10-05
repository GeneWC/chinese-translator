"""Exercise capture/selection/OCR/note/dismissal on actual Windows monitors.

Only generated text is submitted to OCR. Screen snapshots stay in memory.
Uses the downloaded development models and an isolated temporary vocabulary.
"""
import json
import ctypes
from pathlib import Path
import tempfile
import time
from threading import Event

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

import chinese_screen_dictionary.app as app_module
from chinese_screen_dictionary.service import ReadingService


root = Path(__file__).resolve().parents[1]
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
original_ready = app_module.models_ready
app_module.models_ready = lambda _: True
original_service = app_module.ReadingService
app_module.ReadingService = lambda _: ReadingService(root / ".test-data")
checks = []
with tempfile.TemporaryDirectory(prefix="capture-check-", dir=root / ".test-data") as temporary:
    controller = app_module.Controller(app, Path(temporary))
    print("Warming up dictionary", flush=True)
    # Let the real dictionary warmup finish before the timed capture checks.
    controller.pool.waitForDone()
    app.processEvents()
    print("Dictionary ready", flush=True)
    capture_id = next(key for key, (index, _) in controller.hotkeys.registrations.items() if index == 0)

    def toggle():
        previous = controller.session.active
        assert ctypes.windll.user32.PostThreadMessageW(ctypes.windll.kernel32.GetCurrentThreadId(), 0x0312, capture_id, 0)
        deadline = time.monotonic()+2
        while controller.session.active == previous and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert controller.session.active != previous

    fixture = QLabel("我喜欢学习中文")
    fixture.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    fixture.setStyleSheet("background:white;color:black;font-family:'Microsoft YaHei';font-size:36px;")
    fixture.setAlignment(Qt.AlignmentFlag.AlignCenter)
    try:
        for index, screen in enumerate(app.screens()):
            print(f"Checking monitor {index + 1}", flush=True)
            mode = "rectangle" if index % 2 == 0 else "lasso"
            fixture.setGeometry(screen.geometry().x()+120, screen.geometry().y()+220, 480, 160)
            fixture.show()
            fixture.raise_()
            QTest.qWait(350)
            controller.change_mode(mode)
            toggle()
            print("Selection overlay open", flush=True)
            QTest.qWait(150)
            overlay = next(o for o in controller.overlays if o.target_screen == screen)
            assert overlay.geometry() == screen.geometry(), (overlay.geometry(), screen.geometry())
            start = fixture.geometry().topLeft() - screen.geometry().topLeft()
            end = start + QPoint(fixture.width()-1, fixture.height()-1)
            QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=start)
            if mode == "lasso":
                for point in (QPoint(end.x(), start.y()), end, QPoint(start.x(), end.y())):
                    QTest.mouseMove(overlay, point, delay=20)
                QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=start)
            else:
                QTest.mouseMove(overlay, end, delay=20)
                QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=end)
            deadline = time.monotonic()+45
            while controller.note.result is None and time.monotonic() < deadline:
                app.processEvents()
                # Release Python's GIL so background imports/dictionary parsing
                # behave as they do under QApplication.exec().
                time.sleep(.01)
            result = controller.note.result
            print("Lookup finished", flush=True)
            assert result is not None, controller.note.browser.toPlainText()
            assert result.text == fixture.text(), (screen.name(), result.text)
            assert screen.availableGeometry().contains(controller.note.geometry())
            checks.append({"screen": screen.name(), "scale": screen.devicePixelRatio(),
                           "mode": mode, "text": result.text, "seconds": round(result.elapsed, 3),
                           "popup_in_bounds": True})
            toggle()
            assert not controller.session.active and not controller.note.isVisible()
            toggle()
            QTest.keyClick(controller.overlays[0], Qt.Key.Key_Escape)
            assert not controller.overlays and not controller.session.active
        assert all(row["count"] == len(checks) for row in controller.store.list_entries())
        started, release = Event(), Event()
        generation = controller.session.begin("cancel-during-processing")
        controller.note.open_at(QPoint(200, 400), app.primaryScreen().availableGeometry())

        def delayed_lookup(progress):
            started.set()
            assert release.wait(5)
            return result, None

        controller.submit(("lookup", generation), delayed_lookup)
        assert started.wait(5)
        toggle()
        release.set()
        controller.pool.waitForDone()
        app.processEvents()
        assert not controller.note.isVisible()
        assert all(row["count"] == len(checks) for row in controller.store.list_entries())
        report = {"passed": True, "checks": checks, "dismissal_and_escape": True,
                  "shortcut_during_processing": True, "late_result_not_saved": True}
        output = root / "artifacts" / "capture-flow-check.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True))
    finally:
        fixture.close()
        controller.dismiss()
        controller.pool.waitForDone()
        app.processEvents()
        controller.tray.hide()
        controller.hotkeys.close()
        app.removeNativeEventFilter(controller.hotkeys)
        controller.store.close()
        app_module.models_ready = original_ready
        app_module.ReadingService = original_service
