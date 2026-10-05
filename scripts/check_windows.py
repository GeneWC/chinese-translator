"""Check actual Windows global-hotkey registration and Qt message delivery."""
import ctypes
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from chinese_screen_dictionary.hotkeys import Hotkeys, parse_hotkey

app = QApplication([])
api = ctypes.windll.user32
received = []
hotkeys = Hotkeys(lambda: received.append("capture"), lambda: received.append("library"))
app.installNativeEventFilter(hotkeys)
hotkeys.configure("Ctrl+Alt+Shift+F10", "Ctrl+Alt+Shift+F11")
# Another registration with an existing chord must fail, without unregistering it.
conflict = not bool(api.RegisterHotKey(None, 1999, *parse_hotkey("Ctrl+Alt+Shift+F10")))
if not conflict:
    api.UnregisterHotKey(None,1999)
thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
for key_id in hotkeys.registrations:
    if not api.PostThreadMessageW(thread_id, 0x0312, key_id, 0):
        raise RuntimeError("Could not post test hotkey event")
QTimer.singleShot(200, app.quit)
app.exec()
hotkeys.close()
app.removeNativeEventFilter(hotkeys)
report = {"callbacks": received, "conflict_handled": conflict,
    "screens": [{"name":s.name(), "scale":s.devicePixelRatio(), "geometry":list(s.geometry().getRect()),
                 "capture_pixels": [s.grabWindow(0).width(), s.grabWindow(0).height()]} for s in app.screens()]}
root = Path(__file__).resolve().parents[1]
(root / "artifacts/windows-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
assert received == ["capture", "library"] and conflict
