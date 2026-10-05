import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


def crop_selection(image: QImage, logical_size, points: list[QPointF], mode: str) -> QImage:
    """Map screen-local logical coordinates to captured pixels, mask, and pad."""
    if len(points) < 2 or logical_size.width() <= 0 or logical_size.height() <= 0:
        return QImage()
    sx, sy = image.width() / logical_size.width(), image.height() / logical_size.height()
    path = QPainterPath()
    if mode == "rectangle":
        path.addRect(QRectF(points[0], points[-1]).normalized())
    else:
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()
    bounds = path.boundingRect().intersected(QRectF(QPointF(0, 0), logical_size))
    if bounds.width() < 3 or bounds.height() < 3:
        return QImage()
    left, top = math.floor(bounds.left() * sx), math.floor(bounds.top() * sy)
    right, bottom = math.ceil(bounds.right() * sx), math.ceil(bounds.bottom() * sy)
    cropped = QImage(right-left+24, bottom-top+24, QImage.Format.Format_RGB32)
    cropped.fill(Qt.GlobalColor.white)
    painter = QPainter(cropped)
    painter.translate(12-left, 12-top)
    painter.scale(sx, sy)
    painter.setClipPath(path)
    painter.drawImage(QRectF(0, 0, logical_size.width(), logical_size.height()), image)
    painter.end()
    return cropped


class SelectionOverlay(QWidget):
    selected = Signal(object, object, object)  # QImage, screen-space anchor, available geometry
    cancelled = Signal()
    mode_changed = Signal(str)
    started = Signal(object)

    def __init__(self, screen, frozen: QImage, mode: str):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.target_screen = screen
        self.frozen = frozen
        self.mode = mode
        self.points: list[QPointF] = []
        self.drawing = False
        self.blocked = False
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.toolbar = QWidget(self)
        self.toolbar.setStyleSheet("background:#fff9de;color:#302b21;border-radius:6px;padding:5px;font-size:13px;")
        row = QHBoxLayout(self.toolbar)
        self.rect_button = QPushButton("Rectangle (R)")
        self.lasso_button = QPushButton("Lasso (L)")
        for button in (self.rect_button, self.lasso_button):
            button.setCheckable(True)
            row.addWidget(button)
        row.addWidget(QLabel("Drag around text · Esc to cancel"))
        self.rect_button.clicked.connect(lambda: self.set_mode("rectangle"))
        self.lasso_button.clicked.connect(lambda: self.set_mode("lasso"))
        self.toolbar.adjustSize()
        available = screen.availableGeometry().topLeft() - screen.geometry().topLeft()
        self.toolbar.move(available + QPoint(16, 16))
        self.set_mode(mode, emit=False)

    def set_mode(self, mode, emit=True):
        if self.drawing:
            return
        self.mode = mode
        self.rect_button.setChecked(mode == "rectangle")
        self.lasso_button.setChecked(mode == "lasso")
        if emit:
            self.mode_changed.emit(mode)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(self.rect(), self.frozen)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if len(self.points) > 1:
            path = QPainterPath()
            if self.mode == "rectangle":
                path.addRect(QRectF(self.points[0], self.points[-1]).normalized())
            else:
                path.moveTo(self.points[0])
                for point in self.points[1:]:
                    path.lineTo(point)
                path.closeSubpath()
            painter.save()
            painter.setClipPath(path)
            painter.drawImage(self.rect(), self.frozen)
            painter.restore()
            painter.setPen(QPen(QColor("#ffda65"), 2))
            painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton and not self.blocked:
            self.drawing = True
            self.points = [event.position()]
            self.toolbar.hide()
            self.grabMouse()
            self.started.emit(self)

    def bounded_point(self, point):
        return QPointF(max(0, min(self.width(), point.x())), max(0, min(self.height(), point.y())))

    def mouseMoveEvent(self, event):
        if self.drawing:
            point = self.bounded_point(event.position())
            if self.mode == "rectangle" and len(self.points) > 1:
                self.points[-1] = point
            else:
                self.points.append(point)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.drawing:
            return
        self.points.append(self.bounded_point(event.position()))
        self.drawing = False
        self.releaseMouse()
        image = crop_selection(self.frozen, self.size().toSizeF(), self.points, self.mode)
        if image.isNull():
            self.cancelled.emit()
        else:
            anchor = self.mapToGlobal(self.points[-1].toPoint())
            self.selected.emit(image, anchor, self.target_screen.availableGeometry())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() == Qt.Key.Key_L:
            self.set_mode("lasso")
        elif event.key() == Qt.Key.Key_R:
            self.set_mode("rectangle")

    def closeEvent(self, event):
        if self.drawing:
            self.releaseMouse()
        self.frozen = QImage()
        super().closeEvent(event)
