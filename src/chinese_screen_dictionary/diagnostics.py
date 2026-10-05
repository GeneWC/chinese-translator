"""Repeatable end-to-end checks using generated images, never user screenshots."""
import json
from pathlib import Path
import socket
import time

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

from .resources import models_ready
from .service import ReadingService
from .storage import VocabularyStore
from .ui import Library, Note


def fixture(text, *, vertical=False, stylized=False):
    lines = text.split("\n")
    if vertical:
        width, height = 80+len(lines)*65, 65+max(map(len, lines))*60
    else:
        width, height = 70+max(map(len,lines))*49, 55+len(lines)*65
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont("Microsoft YaHei", 28)
    font.setBold(stylized)
    painter.setFont(font)
    painter.setPen(QColor("#161616"))
    if stylized:
        painter.setBrush(QColor("#fff8e4"))
        painter.setPen(QPen(QColor("#3f342c"), 2))
        painter.drawRoundedRect(QRect(5,5,width-10,height-10), 30,30)
        path = QPainterPath()
        path.addText(30, 65, font, lines[0])
        painter.setPen(QPen(Qt.GlobalColor.black, 1.2))
        painter.setBrush(Qt.GlobalColor.black)
        painter.drawPath(path)
    elif vertical:
        for column, line in enumerate(lines):
            x = width-70-column*65
            for row, character in enumerate(line):
                painter.drawText(x, 55+row*60, character)
    else:
        for row, line in enumerate(lines):
            painter.drawText(30, 60+row*65, line)
    painter.end()
    return image


def self_test(root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    if not models_ready(root):
        raise RuntimeError("Install models before running --self-test.")
    app = QApplication.instance() or QApplication([])
    service = ReadingService(root)
    calls = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection

    def deny(*args, **kwargs):
        calls.append("network connection attempted")
        raise RuntimeError("Network is disabled for this offline test")

    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    cases = [
        ("character", "我", {}),
        ("phrase", "马上", {}),
        ("sentence", "我喜欢学习中文", {}),
        ("multiline", "我喜欢\n学习中文", {}),
        ("traditional", "我喜歡學習中文", {}),
        ("vertical", "學習\n中文", {"vertical": True}),
        ("speech_bubble", "你在做什么", {"stylized": True}),
    ]
    results = []
    try:
        for name, text, options in cases:
            image = fixture(text, **options)
            image.save(str(output / f"{name}.png"))
            result, boxes = service.lookup(image=image)
            expected = text.replace("\n", "")
            actual = result.text.replace("\n", "")
            record = {"name": name, "expected": expected, "actual": actual,
                "exact": expected == actual, "translation": result.translation,
                "seconds": round(result.elapsed, 3), "direction": result.direction,
                "saved_words": [w.surface for w in result.words if w.save], "warnings": result.warnings,
                "has_definitions": any(w.senses for w in result.words),
                "boxes": [{"text": b.text, "confidence": b.confidence, "points": b.points} for b in boxes]}
            results.append(record)
            if name == "sentence":
                note = Note()
                note.open_at(QPoint(30,30), QRect(0,0,1200,900))
                note.show_result(result)
                app.processEvents()
                note.grab().save(str(output / "popup.png"))
                store = VocabularyStore(output / "diagnostic-vocabulary.sqlite3")
                store.replace_lookup("diagnostic", result)
                library = Library(store)
                library.show()
                app.processEvents()
                library.grab().save(str(output / "dictionary.png"))
                library.hide()
                note.hide()
                store.close()
        blank = QImage(200,100,QImage.Format.Format_RGB32)
        blank.fill(Qt.GlobalColor.white)
        result, _ = service.lookup(image=blank)
        results.append({"name": "blank", "exact": not result.text and not result.words, "warnings": result.warnings})
        # A warm repeated capture confirms engines are reused.
        result, _ = service.lookup(image=fixture("我喜欢学习中文"))
        results.append({"name": "warm_repeat", "seconds": round(result.elapsed,3), "exact": result.text == "我喜欢学习中文"})
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create
        report = {"network_attempts": calls, "cases": results,
                  "passed": len(results) == len(cases)+2 and all(c["exact"] for c in results) and not calls
                    and all(c.get("translation", "ok") or c.get("has_definitions") for c in results)}
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["passed"]:
        raise RuntimeError(f"Some diagnostic checks failed; see {output / 'report.json'}")
