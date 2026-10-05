from PySide6.QtCore import QPoint, QRect

import chinese_screen_dictionary.app as app_module
from chinese_screen_dictionary.hotkeys import Hotkeys
from tests.test_hotkeys_ui import FakeWindows


def test_controller_drops_late_results_and_replaces_corrections(qtbot, tmp_path, analyzer, monkeypatch):
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(app_module, "models_ready", lambda _: True)
    monkeypatch.setattr(app_module, "Hotkeys", lambda *callbacks: Hotkeys(*callbacks, api=FakeWindows()))
    tasks = []
    monkeypatch.setattr(app_module.Controller, "submit", lambda self, tag, function: tasks.append((tag, function)))
    controller = app_module.Controller(QApplication.instance(), tmp_path)
    qtbot.addWidget(controller.note)
    qtbot.addWidget(controller.library)
    qtbot.addWidget(controller.setup)
    generation = controller.session.begin("first")
    controller.note.open_at(QPoint(10,10), QRect(0,0,1000,800))
    controller.dismiss()
    controller.worker_finished(("lookup",generation), (analyzer.analyze("喜欢"), []))
    assert not controller.store.list_entries()
    assert not controller.note.isVisible()
    generation = controller.session.begin("second")
    controller.note.open_at(QPoint(10,10), QRect(0,0,1000,800))
    controller.worker_finished(("lookup",generation), (analyzer.analyze("喜欢"), []))
    assert controller.store.list_entries()[0]["count"] == 1
    controller.correct("学习")
    tag, _ = tasks[-1]
    controller.worker_finished(tag, (analyzer.analyze("学习"), None))
    assert controller.store.list_entries()[0]["simplified"] == "学习"
    assert controller.store.list_entries()[0]["count"] == 1
    assert not controller.note.direction.isEnabled()
    controller.dismiss()
    controller.tray.hide()
    controller.hotkeys.close()
    QApplication.instance().removeNativeEventFilter(controller.hotkeys)
    controller.store.close()
