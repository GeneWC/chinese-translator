import statistics
from pathlib import Path

from .types import TextBox


def order_text(boxes: list[TextBox], direction="auto"):
    if not boxes:
        return "", "horizontal"
    if direction == "auto":
        tall = sum((b.bounds[3]-b.bounds[1]) > 1.4*(b.bounds[2]-b.bounds[0]) for b in boxes)
        wide = sum((b.bounds[2]-b.bounds[0]) > 1.4*(b.bounds[3]-b.bounds[1]) for b in boxes)
        if tall or wide:
            direction = "vertical" if tall > wide else "horizontal"
        else:
            # Individual-character detections: compare nearest center spacing.
            centers = [((b.bounds[0]+b.bounds[2])/2, (b.bounds[1]+b.bounds[3])/2) for b in boxes]
            votes = []
            for x, y in centers:
                others = [(abs(x-a), abs(y-b)) for a, b in centers if (x, y) != (a, b)]
                if others:
                    dx, dy = min(others, key=lambda d: d[0]**2+d[1]**2)
                    votes.append(dy > dx)
            direction = "vertical" if votes and sum(votes) > len(votes)/2 else "horizontal"
    vertical = direction == "vertical"
    size_axis = 0 if vertical else 1
    sizes = [b.bounds[size_axis+2]-b.bounds[size_axis] for b in boxes]
    tolerance = max(3, statistics.median(sizes) * .55)
    groups = []
    for box in sorted(boxes, key=lambda b: (b.bounds[size_axis]+b.bounds[size_axis+2])/2):
        center = (box.bounds[size_axis]+box.bounds[size_axis+2])/2
        group = next((g for g in groups if abs(g[0]-center) <= tolerance), None)
        if group is None:
            groups.append([center, [box]])
        else:
            group[1].append(box)
            group[0] = statistics.mean((b.bounds[size_axis]+b.bounds[size_axis+2])/2 for b in group[1])
    groups.sort(key=lambda g: g[0], reverse=vertical)
    lines = []
    for _, members in groups:
        members.sort(key=lambda b: b.bounds[1 if vertical else 0])
        lines.append("".join(b.text for b in members))
    return "\n".join(lines), direction


class Recognizer:
    def __init__(self, root: Path):
        self.root = root
        self.engine = None

    def recognize(self, image) -> list[TextBox]:
        import numpy as np
        from PySide6.QtGui import QImage
        if self.engine is None:
            from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
            models = self.root / "models"
            self.engine = RapidOCR(params={
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.lang_type": LangDet.CH,
                "Det.model_type": ModelType.MOBILE,
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_path": str(models / "ch_PP-OCRv5_det_mobile.onnx"),
                # Page-oriented defaults upscale a short speech bubble so far
                # that individual strokes can be detected as separate text.
                "Det.limit_type": "min",
                "Det.limit_side_len": 256,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.CH,
                "Rec.model_type": ModelType.SERVER,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_path": str(models / "ch_PP-OCRv5_rec_server.onnx"),
                "Cls.model_path": str(models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
                "Global.text_score": 0.35,
                "Global.log_level": "warning",
                "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            })
        rgb = image.convertToFormat(QImage.Format.Format_RGB888)
        arr = np.frombuffer(rgb.constBits(), dtype=np.uint8).reshape(rgb.height(), rgb.bytesPerLine())
        bgr = arr[:, :rgb.width()*3].reshape(rgb.height(), rgb.width(), 3)[:, :, ::-1].copy()
        result = self.engine(bgr)
        if result.txts is None or result.boxes is None:
            return []
        return [TextBox(str(text), float(score), tuple(tuple(float(v) for v in p) for p in box))
                for box, text, score in zip(result.boxes, result.txts, result.scores)]
