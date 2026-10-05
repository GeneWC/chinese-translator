import math
import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QImage

from chinese_screen_dictionary.capture import crop_selection
from chinese_screen_dictionary.recognition import order_text
from chinese_screen_dictionary.types import TextBox
from chinese_screen_dictionary.ui import clamp_position


def box(text, x, y, w=30, h=30):
    return TextBox(text, .99, ((x,y), (x+w,y), (x+w,y+h), (x,y+h)))


def test_horizontal_order_joins_wrapped_text():
    text, direction = order_text([box("中文", 60, 60, 60), box("喜欢", 80, 0, 60), box("我", 10, 0), box("学习", 0, 60, 60)])
    assert text == "我喜欢\n学习中文"
    assert direction == "horizontal"


def test_vertical_column_order_and_override():
    boxes = [box("中文", 0, 0, 30, 70), box("学习", 60, 0, 30, 70)]
    assert order_text(boxes) == ("学习\n中文", "vertical")
    assert order_text(boxes, "horizontal") == ("中文学习", "horizontal")
    assert order_text([box("文", 0, 50), box("中", 0, 0), box("习", 70, 50), box("学", 70, 0)], "vertical")[0] == "学习\n中文"


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_rectangle_maps_logical_to_physical_pixels(scale):
    image = QImage(int(200*scale), int(100*scale), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    result = crop_selection(image, QSizeF(200,100), [QPointF(10,10), QPointF(90,50)], "rectangle")
    assert result.width() == math.ceil(90*scale)-math.floor(10*scale)+24
    assert result.height() == math.ceil(50*scale)-math.floor(10*scale)+24
    assert result.pixelColor(0,0) == QColor("white")
    assert result.pixelColor(20,20) == QColor("red")


def test_lasso_excludes_nearby_pixels():
    image = QImage(100,100,QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    result = crop_selection(image, QSizeF(100,100), [QPointF(10,10), QPointF(90,10), QPointF(10,90)], "lasso")
    assert result.pixelColor(20,20) == QColor("red")
    assert result.pixelColor(80,80) == QColor("white")
    assert crop_selection(image,QSizeF(100,100),[QPointF(1,1),QPointF(2,2)],"rectangle").isNull()


def test_popup_clamps_negative_origin_monitor():
    screen = QRect(-1920,0,1920,1080)
    assert clamp_position(QPoint(-2,1070), QSize(440,570), screen) == QPoint(-440,510)
    assert clamp_position(QPoint(-2200,-50), QSize(440,570), screen) == QPoint(-1920,0)
