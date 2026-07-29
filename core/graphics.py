# -*- coding: utf-8 -*-

import enum

from PySide6.QtCore import QPoint, QRect, Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF
from PySide6.QtWidgets import QWidget, QLineEdit, QTextEdit

from alias import *


@final
class WrapMode(enum.IntEnum):
    Null = 0
    Word = Qt.TextFlag.TextWordWrap
    Anywhere = Qt.TextFlag.TextWrapAnywhere


@final
class TextMeasure:
    @overload
    def __init__(self, metrics: QFontMetrics | QFontMetricsF, text: string): ...

    @overload
    def __init__(self, font: QFont, text: string): ...

    def __init__(self, ft: QFontMetrics | QFontMetricsF | QFont, text: string):
        if isinstance(ft, QFont):
            self.metrics = QFontMetricsF(ft)
        else:
            self.metrics = ft
        self.text = text

    @property
    def width(self) -> int | float:
        return self.metrics.horizontalAdvance(self.text)

    @property
    def height(self) -> int | float:
        return self.metrics.height()

    @property
    def ascent(self) -> int | float:
        """
        :return: height from text top to baseline
        """
        return self.metrics.ascent()

    @property
    def descent(self) -> int | float:
        """
        :return: height from baseline to text bottom
        """
        return self.metrics.descent()

    def limit_width(self, width: int | float, wrapping: WrapMode = WrapMode.Word) -> QRect | QRectF:
        """
        Compute the bounding rectangle that tightly encloses the text with specified maximum width.
        :param width: maximum width of the text bounding rectangle
        :param wrapping: wrapping mode of multiline text
        :return: bounding rectangle of the box
        """
        if isinstance(self.metrics, QFontMetrics):
            box = QRect(0, 0, width, 2147483647)
        else:
            box = QRectF(0, 0, width, 1.797693134862315E+308)
        return self.metrics.boundingRect(box, wrapping, self.text)


class IComponentGraphics:
    FillWidth = -1
    FillHeight = -1
    NotRounded: int = 0

    @pure_virtual
    def push_anchor(self, anchor: QPointF) -> void:
        raise NotImplementedError

    @pure_virtual
    def pop_anchor(self) -> void:
        raise NotImplementedError

    @pure_virtual
    def move_anchor(self, dx: int | float, dy: int | float) -> void:
        raise NotImplementedError

    @pure_virtual
    def external_anchor(self) -> QPointF:
        raise NotImplementedError

    @pure_virtual
    def draw_rect(self, rect: QRectF, color: QColor, *,
                  round_radius: int = NotRounded, refresh: bool = False) -> void:
        """
        Paint a filled rectangle.
        :param rect: position and size of the rectangle
        :param color: filling color
        :param round_radius: radius of the rounded angles; NotRound if square
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        raise NotImplementedError

    @pure_virtual
    def draw_frame(self, rect: QRect | QRectF, color: QColor, line_width: int = 2, *,
                   round_radius: int = NotRounded, refresh: bool = False) -> void:
        """
        Paint a wireframe.
        :param rect: the outer frame rectangle
        :param color: filling color
        :param line_width: width of wireframe lines
        :param round_radius: radius of the rounded angles; NotRound if square
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        raise NotImplementedError

    @pure_virtual
    def draw_line(self, start: QPoint | QPointF, end: QPoint | QPointF, color: QColor, line_width: int = 2, *,
                  round_ends: bool = False, refresh: bool = False) -> void:
        """
        Paint a line segment.
        :param start: the starting point
        :param end: the ending point
        :param color: color of the line
        :param line_width: width of the line
        :param round_ends: when true, the ends are semicircles rather than square
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        raise NotImplementedError

    @pure_virtual
    def draw_triangle(self, p1: QPoint | QPointF, p2: QPoint | QPointF, p3: QPoint | QPointF, color: QColor, *,
                      refresh: bool = False) -> void:
        """
        Paint a filled triangle.
        :param p1: the 1st vertex
        :param p2: the 2nd vertex
        :param p3: the 3rd vertex
        :param color: filling color
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        raise NotImplementedError

    @pure_virtual
    def draw_lines(self, points: IEnumerable[QPoint | QPointF], color: QColor, line_width: int = 2, *,
                   refresh: bool = False) -> void:
        """
        Paint a broken line.
        :param points: vertexes of the broken line
        :param color: color of the line
        :param line_width: width of the line
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        raise NotImplementedError

    @overload
    @pure_virtual
    def draw_text(self, text: string, position: QPoint | QPointF, *,
                  color: QColor, font: QFont, width: int, refresh: bool = False) -> void:
        """
        Paint a text at specified position of the text baseline.
        :param text: text to paint
        :param position: starting position of the text baseline
        :param color: color of the text
        :param font: font of the text
        :param width: width of the pen
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        ...

    @overload
    @pure_virtual
    def draw_text(self, text: string, rect: QRect | QRectF, *,
                  color: QColor, font: QFont, width: int, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
                  wrapping: WrapMode = WrapMode.Null, refresh: bool = False) -> void:
        """
        Paint a text in the specified rectangle.
        :param text: text to paint
        :param rect: outer frame of the text
        :param color: color of the text
        :param font: font of the text
        :param width: width of the pen
        :param alignment: alignment of the text
        :param wrapping: wrapping mode of the text
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        ...

    @pure_virtual
    def draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, *,
                  color: QColor, font: QFont, width: int, **kwargs):
        raise NotImplementedError

    @pure_virtual
    def create_lineedit(self, rect: QRect | QRectF) -> QLineEdit:
        """
        Create a single-line edit control at the specified offset relative to the anchor point.
        :param rect: offset position and size
        """
        raise NotImplementedError

    @pure_virtual
    def create_textedit(self, rect: QRect | QRectF) -> QTextEdit:
        """
        Create a multi-line edit control at the specified offset relative to the anchor point.
        :param rect: offset position and size
        """
        raise NotImplementedError

    @pure_virtual
    def create_hypertext_edit(self, rect: QRect | QRectF) -> 'hyper_text_edit.HyperTextEdit':
        """
        Create a hyper-text edit control at the specified offset relative to the anchor point.
        :param rect: offset position and size
        """
        raise NotImplementedError

    @pure_virtual
    def move_widget(self, widget: QWidget, dx: int, dy: int) -> void:
        """
        Move a widget for a specified delta coordination.
        :param widget: the widget to move
        :param dx: horizonal delta
        :param dy: vertical delta
        """
        raise NotImplementedError
