import gzip
import logging
import re
from collections import defaultdict
from pathlib import Path

from .types import Analysis, Sense, Vocabulary

HAN = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f"
HAN_RE = re.compile(f"[{HAN}]")
CHUNK_RE = re.compile(f"[{HAN}]+")
ENTRY_RE = re.compile(r"^(\S+) (\S+) \[([^]]+)\] /(.+)/$")


def has_chinese(text):
    return bool(HAN_RE.search(text))


def tone_pinyin(numbered: str) -> str:
    from pypinyin.contrib.tone_convert import to_tone
    return " ".join(to_tone(syllable.replace("u:", "v")) for syllable in numbered.split())


class ChineseDictionary:
    def __init__(self, path: Path):
        self.entries = defaultdict(list)
        self.pairs = {}
        self.traditional_only = set()
        self.max_word = 1
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                match = ENTRY_RE.match(line.strip())
                if not match:
                    continue
                traditional, simplified, numbered, meanings = match.groups()
                sense = Sense(tone_pinyin(numbered), tuple(meanings.split("/")))
                pair = (simplified, traditional)
                for form in {traditional, simplified}:
                    if (pair, sense) not in self.entries[form]:
                        self.entries[form].append((pair, sense))
                    self.pairs.setdefault(form, pair)
                self.max_word = max(self.max_word, len(traditional), len(simplified))
                for t, s in zip(traditional, simplified):
                    if t != s:
                        self.traditional_only.add(t)

    def lookup(self, surface):
        values = self.entries.get(surface, [])
        if not values:
            return None
        # Prefer the spelling's first explicit pair. Never collapse unrelated
        # simplified/traditional variants via a general script conversion.
        pair = self.pairs[surface]
        senses = list(dict.fromkeys(sense for p, sense in values if p == pair))
        return pair, senses


class LanguageAnalyzer:
    def __init__(self, dictionary: ChineseDictionary, translator=None, cache_dir: Path | None = None):
        import jieba
        self.dictionary = dictionary
        self.translator = translator
        jieba.setLogLevel(logging.WARNING)
        self.segmenter = jieba.Tokenizer()
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.segmenter.tmp_dir = str(cache_dir)
        self.segmenter.initialize()
        for word in dictionary.entries:
            if len(word) > 1 and CHUNK_RE.fullmatch(word):
                # Modest frequency lets normal segmentation win ambiguous cases.
                self.segmenter.add_word(word, freq=max(self.segmenter.FREQ.get(word, 0), 10))

    def segment(self, chunk):
        tokens = list(self.segmenter.cut(chunk, HMM=False))
        # Merge adjacent segments when a longer dictionary phrase/idiom spans
        # them; never also save the constituent tokens.
        index = 0
        while index < len(tokens):
            combined = tokens[index]
            best, best_end = combined, index + 1
            for end in range(index + 1, len(tokens)):
                combined += tokens[end]
                if len(combined) > self.dictionary.max_word:
                    break
                if combined in self.dictionary.entries:
                    best, best_end = combined, end + 1
            yield best
            index = best_end

    def analyze(self, text: str, *, translate=True) -> Analysis:
        from pypinyin import Style, lazy_pinyin
        # OCR often inserts spaces between Han characters. Preserve Latin words.
        text = re.sub(f"(?<=[{HAN}])\\s+(?=[{HAN}])", "", text.strip())
        if not has_chinese(text):
            return Analysis(text, "", "", warnings=["No Chinese text found."])
        syllables = lazy_pinyin(text, style=Style.TONE, neutral_tone_with_five=False)
        result = Analysis(text, " ".join(syllables), "")
        single = len(HAN_RE.findall(text)) == 1 and not re.search(r"[A-Za-z0-9]", text)
        for match in CHUNK_RE.finditer(text):
            offset = match.start()
            for token in self.segment(match.group()):
                found = self.dictionary.lookup(token)
                if found:
                    (simplified, traditional), senses = found
                    pinyin = senses[0].pinyin
                    key = f"cedict:{simplified}|{traditional}"
                else:
                    simplified = traditional = token
                    senses = []
                    pinyin = " ".join(lazy_pinyin(token, style=Style.TONE))
                    key = f"unknown:{token}"
                result.words.append(Vocabulary(key, token, simplified, traditional,
                    pinyin, senses, offset, offset+len(token), len(token) > 1 or single))
                offset += len(token)
        # Exact dictionary lookups already have reliable English meanings.
        # Neural translation of an isolated character can invent a sentence.
        if translate and self.translator and not self.dictionary.lookup(text):
            try:
                traditional = any(c in self.dictionary.traditional_only for c in text)
                result.translation = self.translator.translate(text, "zt" if traditional else "zh")
            except Exception:
                logging.exception("Offline translation failed")
                result.warnings.append("Sentence translation is unavailable. Dictionary definitions are still shown; retry or repair models from the tray.")
        return result
