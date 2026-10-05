import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = [p.strip().upper() for p in value.split("+")]
    modifiers = {"CTRL": 0x0002, "ALT": 0x0001, "SHIFT": 0x0004}
    if len(parts) < 2 or len(parts) != len(set(parts)):
        raise ValueError("Use Ctrl or Alt plus a letter, number, or F1–F11.")
    mask = 0
    for part in parts[:-1]:
        if part not in modifiers:
            raise ValueError("Supported modifiers are Ctrl, Alt, and Shift.")
        mask |= modifiers[part]
    if not mask & 3:
        raise ValueError("Include Ctrl or Alt so normal typing is not intercepted.")
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("Choose a letter, number, or F1–F11.")
    return mask | 0x4000, vk


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, capture, library, api=None):
        super().__init__()
        self.api = api if api is not None else (ctypes.windll.user32 if sys.platform == "win32" else None)
        self.callbacks = [capture, library]
        self.registrations = {}
        self.next_id = 100

    def configure(self, capture: str, library: str):
        specs = [parse_hotkey(capture), parse_hotkey(library)]
        if specs[0] == specs[1]:
            raise ValueError("Capture and dictionary need different shortcuts.")
        if self.api is None:
            raise ValueError("Global shortcuts require Windows.")
        previous = dict(self.registrations)
        self.close()
        registered = {}
        try:
            for index, spec in enumerate(specs):
                self.next_id += 1
                key_id = self.next_id
                if not self.api.RegisterHotKey(None, key_id, *spec):
                    label = capture if index == 0 else library
                    raise ValueError(f"{label} is already in use. Choose another shortcut.")
                registered[key_id] = (index, spec)
        except Exception:
            for key_id in registered:
                self.api.UnregisterHotKey(None, key_id)
            for key_id, (index, spec) in previous.items():
                if self.api.RegisterHotKey(None, key_id, *spec):
                    self.registrations[key_id] = (index, spec)
            raise
        self.registrations = registered

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam in self.registrations:
            index, _ = self.registrations[msg.wParam]
            self.callbacks[index]()
            return True, 0
        return False, 0

    def close(self):
        for key_id in self.registrations:
            self.api.UnregisterHotKey(None, key_id)
        self.registrations = {}
