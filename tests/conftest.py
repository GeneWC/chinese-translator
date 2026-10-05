from pathlib import Path

import pytest

from chinese_screen_dictionary.language import ChineseDictionary, LanguageAnalyzer

CEDICT = """我 我 [wo3] /I/me/
喜歡 喜欢 [xi3 huan5] /to like/to be fond of/
學習 学习 [xue2 xi2] /to learn/to study/
中文 中文 [Zhong1 wen2] /Chinese language/
中 中 [zhong1] /middle/
文 文 [wen2] /writing/
馬上 马上 [ma3 shang4] /at once/immediately/
銀行 银行 [yin2 hang2] /bank/
行 行 [xing2] /to walk/
行 行 [hang2] /row/profession/
你好 你好 [ni3 hao3] /hello/
謝謝 谢谢 [xie4 xie5] /thanks/
"""


@pytest.fixture
def analyzer(tmp_path):
    path = tmp_path / "cedict.txt"
    path.write_text(CEDICT, encoding="utf-8")
    return LanguageAnalyzer(ChineseDictionary(path), cache_dir=tmp_path)
