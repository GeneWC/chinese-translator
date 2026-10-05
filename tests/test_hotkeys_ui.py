import pytest
from PySide6.QtCore import QPoint, QRect

from chinese_screen_dictionary.hotkeys import Hotkeys, parse_hotkey
from chinese_screen_dictionary.ui import Note, result_html


class FakeWindows:
    def __init__(self):
        self.keys = {}
        self.conflict = None

    def RegisterHotKey(self, hwnd, key_id, mod, key):
        if (mod,key) == self.conflict:
            return False
        self.keys[key_id] = (mod,key)
        return True

    def UnregisterHotKey(self, hwnd, key_id):
        self.keys.pop(key_id, None)


def test_hotkey_conflict_preserves_old_bindings():
    api = FakeWindows()
    hotkeys = Hotkeys(lambda: None, lambda: None, api)
    hotkeys.configure("Ctrl+Alt+D", "Ctrl+Alt+L")
    previous = dict(api.keys)
    api.conflict = parse_hotkey("Ctrl+Alt+T")
    with pytest.raises(ValueError, match="already in use"):
        hotkeys.configure("Ctrl+Alt+S", "Ctrl+Alt+T")
    assert api.keys == previous
    hotkeys.close()
    assert not api.keys


@pytest.mark.parametrize("value", ["D", "Shift+D", "Ctrl+F12", "Win+D", "Ctrl+Ctrl+D", "Ctrl++"])
def test_hotkey_rejects_reserved_or_plain_keys(value):
    with pytest.raises(ValueError):
        parse_hotkey(value)


def test_note_renders_edits_and_clamps(qtbot, analyzer):
    note = Note()
    qtbot.addWidget(note)
    note.open_at(QPoint(790,590), QRect(0,0,800,600))
    assert note.geometry().right() < 800 and note.geometry().bottom() < 600
    result = analyzer.analyze("我喜欢学习中文")
    result.translation = "I like learning Chinese."
    note.show_result(result)
    text = note.browser.toPlainText()
    assert "我喜欢学习中文" in text and "I like learning Chinese." in text
    assert "Words" in text.title()
    note.toggle_editor()
    note.editor.setPlainText("中文")
    with qtbot.waitSignal(note.edited) as signal:
        note.apply_edit()
    assert signal.args == ["中文"]


def test_ocr_text_is_escaped_in_note(analyzer):
    result = analyzer.analyze("中文<script>bad</script>")
    markup = result_html(result)
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup


@pytest.mark.parametrize("previous_text", ["", "中文"])
def test_failed_lookup_still_allows_manual_correction(qtbot, analyzer, previous_text):
    note = Note()
    qtbot.addWidget(note)
    note.open_at(QPoint(10, 10), QRect(0, 0, 1000, 800))
    if previous_text:
        note.show_result(analyzer.analyze(previous_text))
        note.show_loading()
    note.show_error("Recognition failed")
    assert note.edit_button.isEnabled()
    note.toggle_editor()
    assert note.edit_panel.isVisible()
    assert note.editor.toPlainText() == previous_text
    note.editor.setPlainText("学习")
    with qtbot.waitSignal(note.edited) as signal:
        note.apply_edit()
    assert signal.args == ["学习"]
    note.show_loading()
    note.show_error("Correction failed")
    note.toggle_editor()
    assert note.editor.toPlainText() == "学习"


def test_library_refresh_clears_a_replaced_selection(qtbot, analyzer, tmp_path):
    from chinese_screen_dictionary.storage import VocabularyStore
    from chinese_screen_dictionary.ui import Library
    store = VocabularyStore(tmp_path / "words.db")
    store.replace_lookup("first", analyzer.analyze("学习"))
    store.replace_lookup("second", analyzer.analyze("中文"))
    library = Library(store)
    qtbot.addWidget(library)
    library.search.setText("学习")
    library.table.selectRow(0)
    assert "学习" in library.context.toPlainText()
    library.search.setText("中文")
    assert library.table.currentRow() == -1
    assert not library.table.selectedItems()
    store.close()
