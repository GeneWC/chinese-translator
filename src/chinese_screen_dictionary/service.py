from pathlib import Path
from time import perf_counter

from .language import ChineseDictionary, LanguageAnalyzer
from .recognition import Recognizer, order_text
from .resources import ASSETS
from .translation import OfflineTranslator


class ReadingService:
    """All calls run serially on the model worker, never on the UI thread."""

    def __init__(self, root: Path):
        self.root = root
        self.recognizer = Recognizer(root)
        self.analyzer = None

    def prepare(self):
        if self.analyzer is None:
            dictionary = ChineseDictionary(ASSETS / "cedict.txt.gz")
            self.analyzer = LanguageAnalyzer(dictionary, OfflineTranslator(self.root), self.root / "cache")

    def lookup(self, image=None, boxes=None, direction="auto", text=None):
        started = perf_counter()
        self.prepare()
        if text is None:
            if boxes is None:
                boxes = self.recognizer.recognize(image)
            text, chosen = order_text(boxes, direction)
        else:
            boxes = None  # Manual text is already ordered; don't reorder stale OCR.
            chosen = "horizontal" if direction == "auto" else direction
        result = self.analyzer.analyze(text)
        result.direction = chosen
        if text and boxes and any(b.confidence < .8 for b in boxes):
            result.warnings.insert(0, "Some characters may have been misread. Use Edit text to correct them.")
        result.elapsed = perf_counter()-started
        return result, boxes
