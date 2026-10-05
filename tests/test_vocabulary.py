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
