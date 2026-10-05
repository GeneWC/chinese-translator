"""Compare detector resizing on the generated OCR regression fixtures."""
import json
from pathlib import Path
from PySide6.QtGui import QImage
from chinese_screen_dictionary.recognition import Recognizer, order_text

root = Path(__file__).resolve().parents[1]
reader = Recognizer(root / ".test-data")
reader.recognize(QImage(str(root / "artifacts/source-check/character.png")))
results = []
for kind, minimum in [("max",736), ("min",256), ("min",480)]:
    reader.engine.text_det.limit_type = kind
    reader.engine.text_det.limit_side_len = minimum
    cases = {}
    for name in ("character", "phrase", "sentence", "multiline", "traditional", "vertical", "speech_bubble"):
        boxes = reader.recognize(QImage(str(root / f"artifacts/source-check/{name}.png")))
        text, direction = order_text(boxes)
        cases[name] = dict(text=text, direction=direction, scores=[b.confidence for b in boxes])
    results.append(dict(kind=kind, minimum=minimum, cases=cases))
print(json.dumps(results, ensure_ascii=True, indent=2))
