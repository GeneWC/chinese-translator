import json
import pytest

from chinese_screen_dictionary.storage import VocabularyStore
from chinese_screen_dictionary.types import Analysis, LookupSession


def saved(result):
    return [word.surface for word in result.words if word.save]


def test_sentence_saves_phrases_not_characters(analyzer):
    assert saved(analyzer.analyze("我喜欢学习中文")) == ["喜欢", "学习", "中文"]
    assert saved(analyzer.analyze("我")) == ["我"]
    assert saved(analyzer.analyze("我！")) == ["我"]
    assert saved(analyzer.analyze("我 A")) == []


def test_preserves_alternative_readings_and_phrase_definition(analyzer):
    result = analyzer.analyze("行")
    assert len(result.words[0].senses) == 2
    result = analyzer.analyze("马上")
    assert saved(result) == ["马上"]
    assert "immediately" in result.words[0].senses[0].definitions


def test_ocr_spaces_and_wrapped_words(analyzer):
    assert saved(analyzer.analyze("我 喜 欢 学\n习 中 文")) == ["喜欢", "学习", "中文"]


def test_counts_corrections_variants_and_restart(analyzer, tmp_path):
    path = tmp_path / "words.db"
    store = VocabularyStore(path)
    store.replace_lookup("one", analyzer.analyze("喜欢喜欢学习"))
    assert {r["simplified"]: r["count"] for r in store.list_entries()} == {"喜欢": 1, "学习": 1}
    store.replace_lookup("two", analyzer.analyze("喜歡"))
    assert store.list_entries()[0]["count"] == 2
    assert {c["surface"] for c in store.contexts(store.list_entries()[0]["key"])} == {"喜欢", "喜歡"}
    store.replace_lookup("one", analyzer.analyze("中文"))
    assert {r["simplified"]: r["count"] for r in store.list_entries()} == {"喜欢": 1, "中文": 1}
    store.replace_lookup("three", analyzer.analyze("我"))
    assert len(store.list_entries(characters=True)) == 1
    store.close()
    store = VocabularyStore(path)
    assert len(store.list_entries()) == 2
    assert store.list_entries(search="Chinese")[0]["simplified"] == "中文"
    assert store.list_entries(search="%") == []
    key = store.list_entries(search="中文")[0]["key"]
    store.delete_entry(key)
    assert not store.contexts(key)
    assert len(store.list_entries()) == 1
    store.close()


def test_correction_transaction_rolls_back_on_failure(analyzer, tmp_path):
    store = VocabularyStore(tmp_path / "words.db")
    store.replace_lookup("one", analyzer.analyze("喜欢"))
    broken = analyzer.analyze("学习")
    broken.words.append(object())
    with pytest.raises(AttributeError):
        store.replace_lookup("one", broken)
    assert store.list_entries()[0]["simplified"] == "喜欢"
    assert store.contexts(store.list_entries()[0]["key"])[0]["text"] == "喜欢"
    store.close()


def test_blank_correction_removes_only_original_contribution(analyzer, tmp_path):
    store = VocabularyStore(tmp_path / "words.db")
    store.replace_lookup("one", analyzer.analyze("喜欢"))
    store.replace_lookup("two", analyzer.analyze("喜欢"))
    store.replace_lookup("one", analyzer.analyze(""))
    assert store.list_entries()[0]["count"] == 1
    store.close()


def test_translation_failure_keeps_dictionary(analyzer):
    class BrokenTranslator:
        def translate(self, *_):
            raise RuntimeError("unavailable")
    analyzer.translator = BrokenTranslator()
    result = analyzer.analyze("我学习")
    assert saved(result) == ["学习"]
    assert result.warnings and not result.translation


def test_cancelled_and_superseded_work_cannot_commit():
    state = LookupSession()
    generation = state.begin("first")
    assert state.accepts(generation)
    revised = state.revise()
    assert not state.accepts(generation)
    assert state.accepts(revised)
    state.cancel()
    assert not state.accepts(revised)
    latest = state.begin("next")
    assert state.accepts(latest) and not state.accepts(generation)


def test_ambiguous_spellings_keep_all_readings_and_share_counts(analyzer, tmp_path):
    result = analyzer.analyze("发")
    assert {s.pinyin for s in result.words[0].senses} == {"fā", "fà"}
    assert analyzer.analyze("髮").words[0].senses[0].definitions == ("hair",)
    assert analyzer.analyze("乾").words[0].simplified == "乾"
    store = VocabularyStore(tmp_path / "words.db")
    store.replace_lookup("one", result)
    store.replace_lookup("two", analyzer.analyze("髮"))
    rows = store.list_entries(characters=True)
    assert len(rows) == 1 and rows[0]["count"] == 2
    assert {s["pinyin"] for s in json.loads(rows[0]["definitions"])} == {"fā", "fà"}
    store.replace_lookup("three", analyzer.analyze("里面裡面"))
    store.replace_lookup("four", analyzer.analyze("裏面"))
    rows = store.list_entries()
    assert len(rows) == 1 and rows[0]["count"] == 2
    assert "inside" in rows[0]["definitions"]
    store.close()


def test_old_variant_keys_migrate_without_double_counting(tmp_path):
    path = tmp_path / "words.db"
    store = VocabularyStore(path)
    with store.db:
        store.db.execute("INSERT INTO lookups VALUES ('one', '里面裡面', '', '2026-01-01')")
        store.db.execute("INSERT INTO lookups VALUES ('two', '裡面', '', '2026-01-02')")
        for traditional, meaning in (("裏面", "variant"), ("裡面", "inside")):
            key = f"cedict:里面|{traditional}"
            definitions = json.dumps([{"pinyin": "lǐ miàn", "definitions": [meaning]}])
            store.db.execute("INSERT INTO entries VALUES (?, '里面', ?, 'lǐ miàn', ?, 0)", (key, traditional, definitions))
            store.db.execute("INSERT INTO occurrences VALUES ('one', ?, ?)", (key, traditional))
        store.db.execute("INSERT INTO occurrences VALUES ('two', 'cedict:里面|裡面', '裡面')")
        store.db.execute("PRAGMA user_version=1")
    store.close()
    store = VocabularyStore(path)
    rows = store.list_entries()
    assert len(rows) == 1 and rows[0]["count"] == 2
    assert "inside" in rows[0]["definitions"] and "variant" in rows[0]["definitions"]
    assert len(store.contexts(rows[0]["key"])) == 2
    assert store.list_entries(search="裡面")[0]["count"] == 2
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2
    store.close()
