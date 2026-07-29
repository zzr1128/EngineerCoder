# -*- coding: utf-8 -*-

from dataclasses import dataclass

from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import QWidget, QTextEdit, QLineEdit

from alias import *
from alias import Nullable
from core.graphics import IComponentGraphics
from graphics import WrapMode
from hyper_text_edit import HyperTextEdit


class EditionCanvas(QWidget, IComponentGraphics):
    class Paintable(Protocol):
        def paint(self, painter: QPainter) -> void: ...

    @staticmethod
    def set_pen_color(painter: QPainter, color: QColor) -> void:
        pen: QPen = painter.pen()
        pen.setColor(color)
        painter.setPen(pen)

    @staticmethod
    def set_brush_color(painter: QPainter, color: QColor) -> void:
        brush: QBrush = painter.brush()
        brush.setColor(color)
        painter.setBrush(brush)

    @staticmethod
    def set_color(painter: QPainter, color: QColor) -> void:
        EditionCanvas.set_pen_color(painter, color)
        EditionCanvas.set_brush_color(painter, color)

    @staticmethod
    def set_pen(painter: QPainter, color: QColor, line_width: int) -> void:
        pen: QPen = painter.pen()
        pen.setColor(color)
        pen.setWidth(line_width)
        painter.setPen(pen)

    @dataclass
    class Rectangle:
        rect: QRectF
        color: QColor
        round_radius: int

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_color(painter, self.color)

            if self.round_radius == IComponentGraphics.NotRounded:
                painter.drawRect(self.rect)
            else:
                painter.drawRoundedRect(self.rect, self.round_radius, self.round_radius)

    @dataclass
    class RectangleFrame:
        rect: QRectF
        color: QColor
        round_radius: int
        line_width: int

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen(painter, self.color, self.line_width)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if self.round_radius == IComponentGraphics.NotRounded:
                painter.drawRect(self.rect)
            else:
                painter.drawRoundedRect(self.rect, self.round_radius, self.round_radius)

    @dataclass
    class Line:
        start: QPointF
        end: QPointF
        color: QColor
        line_width: int
        round_ends: bool

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen(painter, self.color, self.line_width)

            painter.drawLine(self.start, self.end)

            if self.round_ends:
                painter.drawPoint(self.start)
                painter.drawPoint(self.end)

    @dataclass
    class Triangle:
        p1: QPointF
        p2: QPointF
        p3: QPointF
        color: QColor

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen_color(painter, self.color)
            EditionCanvas.set_brush_color(painter, self.color)

            painter.drawLine(self.p1, self.p2)
            painter.drawLine(self.p2, self.p3)
            painter.drawLine(self.p3, self.p1)

            path = QPainterPath()
            path.moveTo(self.p1)
            path.lineTo(self.p2)
            path.lineTo(self.p3)
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillPath(path, painter.brush())

    @dataclass
    class BrokenLine:
        points: IEnumerable[QPoint | QPointF]
        color: QColor
        line_width: int

        def paint(self, painter: QPainter) -> void:
            lines: IList[QLineF] = []
            last: Nullable[QPointF] = null
            for pt in self.points:
                if isinstance(pt, QPoint):
                    pt = QPointF(pt)
                if last is null:
                    last = pt
                    continue
                lines.append(QLineF(last, pt))
                last = pt

            EditionCanvas.set_pen(painter, self.color, self.line_width)
            painter.drawLines(lines)

    @dataclass
    class Text:
        position: QPointF | QRectF
        text: string
        color: QColor
        font: QFont
        pen_width: int
        alignment: Nullable[Qt.AlignmentFlag]
        wrapping: Nullable[WrapMode]

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen(painter, self.color, self.pen_width)
            painter.setFont(self.font)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if isinstance(self.position, QPointF):
                painter.drawText(self.position, self.text)
            else:
                painter.drawText(self.position, self.alignment | self.wrapping, self.text)

    def __init__(self, parent):
        super(EditionCanvas, self).__init__(parent)
        self.stack: IList[QPointF] = []
        self.painter: Nullable[QPainter] = null
        self.figures: IList[EditionCanvas.Paintable] = []

    @property
    def _current_anchor(self) -> QPointF:
        if self.stack:
            return self.stack[-1]
        else:
            return QPointF()

    def push_anchor(self, anchor: QPoint | QPointF) -> void:  # Can only be called synchronously
        if isinstance(anchor, QPoint):
            anchor = QPointF(anchor)
        self.stack.append(self._absolute_point(anchor))

    def pop_anchor(self) -> void:  # Can only be called synchronously
        self.stack.pop()

    def move_anchor(self, dx: int | float, dy: int | float) -> void:  # Can only be called synchronously
        """
        Move the current anchor point.
        Assume there exists at least one anchor.
        """
        p = self.stack.pop()
        self.stack.append(QPointF(p.x() + dx, p.y() + dy))

    def external_anchor(self) -> QPointF:  # Can only be called synchronously
        """
        The accumulated anchor point except the current one.
        """
        if len(self.stack) >= 2:
            return QPointF(self.stack[-2].x(), self.stack[-2].y())
        return QPointF()

    @final
    def _absolute_point(self, point: QPoint | QPointF) -> QPointF:
        """
        Absolute position of a point relative to the anchor.
        """
        return QPointF(float(self._current_anchor.x() + point.x()), float(self._current_anchor.y() + point.y()))

    @final
    def _absolute_rect(self, rect: QRect | QRectF) -> QRectF:
        """
        Absolute position and size of a rectangle relative to the anchor.
        """
        if isinstance(rect, QRect):
            rect = QRectF(rect)
        return QRectF(self._absolute_point(rect.topLeft()), rect.size())

    def draw_rect(self, rect: QRect, color: QColor, *,
                  round_radius: int = IComponentGraphics.NotRounded, refresh: bool = False) -> void:
        """
        Paint a filled rectangle.
        See IComponentGraphics.draw_rect(rect, color, *[, round_radius][, refresh]).
        """
        self.figures.append(EditionCanvas.Rectangle(self._absolute_rect(rect), color, round_radius))
        if refresh:
            self.update()

    def draw_frame(self, rect: QRect | QRectF, color: QColor, line_width: int = 2, *,
                   round_radius: int = IComponentGraphics.NotRounded, refresh: bool = False) -> void:
        """
        Paint a wireframe.
        See IComponentGraphics.draw_frame(rect, color[, line_width], *, [round_radius][, refresh]).
        """
        self.figures.append(EditionCanvas.Rectangle(self._absolute_rect(rect), color, round_radius))
        if refresh:
            self.update()

    def draw_line(self, start: QPoint | QPointF, end: QPoint | QPointF, color: QColor, line_width: int = 2, *,
                  round_ends: bool = False, refresh: bool = False) -> void:
        """
        Paint a line segment.
        See IComponentGraphics.draw_line(start, end, color[, line_width], *, [round_ends][, refresh]).
        """
        self.figures.append(EditionCanvas.Line(self._absolute_point(start), self._absolute_point(end),
                                               color, line_width, round_ends))
        if refresh:
            self.update()

    def draw_triangle(self, p1: QPoint | QPointF, p2: QPoint | QPointF, p3: QPoint | QPointF, color: QColor, *,
                      refresh: bool = False) -> void:
        """
        Paint a filled triangle.
        See IComponentGraphics.draw_triangle(p1, p2, p3, color, *, [refresh]).
        """
        self.figures.append(EditionCanvas.Triangle(self._absolute_point(p1), self._absolute_point(p2),
                                                   self._absolute_point(p3), color))
        if refresh:
            self.update()

    def draw_lines(self, points: IEnumerable[QPoint | QPointF], color: QColor, line_width: int = 2, *,
                   refresh: bool = False) -> void:
        """
        Paint a broken line.
        See IComponentGraphics.draw_lines(points, color, line_width, *, [refresh]).
        """
        self.figures.append(EditionCanvas.BrokenLine(points, color, line_width))
        if refresh:
            self.update()

    @overload
    def draw_text(self, text: string, position: QPoint | QPointF, *,
                  color: QColor, font: QFont, width: int, refresh: bool = False) -> void:
        """
        Paint a text at specified position of the text baseline.
        See IComponentGraphics.draw_text(text, position, *, color, font, width[, refresh]).
        """
        ...

    @overload
    def draw_text(self, text: string, rect: QRect | QRectF, *,
                  color: QColor, font: QFont, width: int, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
                  wrapping: WrapMode = WrapMode.Null, refresh: bool = False) -> void:
        """
        Paint a text in the specified rectangle.
        See IComponentGraphics.draw_text(text, rect, *, color, font, width[, alignment][, wrapping][, refresh]).
        """
        ...

    def draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, *, color: QColor, font: QFont, width: int,
                  refresh: bool = False, **kwargs):
        if isinstance(pos, (QPoint, QPointF)):  # draw_text(text, position, *, color, font, width[, refresh])
            self.figures.append(EditionCanvas.Text(self._absolute_point(pos), text, color, font, width, null, null))
        else:  # draw_text(text, rect, *, color, font, width[, alignment][, wrapping][, refresh])
            alignment = kwargs.get('alignment', Qt.AlignmentFlag.AlignLeft)
            wrapping = kwargs.get('wrapping', WrapMode.Null)
            self.figures.append(EditionCanvas.Text(self._absolute_rect(pos), text, color, font, width, alignment, wrapping))
        if refresh:
            self.update()

    def create_lineedit(self, rect: QRect | QRectF) -> QLineEdit:
        """
        Create a single-line edit control at the specified offset relative to the anchor point.
        See IComponentGraphics.create_lineedit(rect).
        """
        edit = QLineEdit(self)
        rect = self._absolute_rect(rect)
        if isinstance(rect, QRectF):
            rect = rect.toRect()
        edit.setGeometry(rect)
        return edit

    def create_textedit(self, rect: QRect | QRectF) -> QTextEdit:
        """
        Create a multi-line edit control at the specified offset relative to the anchor point.
        See IComponentGraphics.create_textedit(rect).
        """
        edit = QTextEdit(self)
        rect = self._absolute_rect(rect)
        if isinstance(rect, QRectF):
            rect = rect.toRect()
        edit.setGeometry(rect)
        return edit

    def create_hypertext_edit(self, rect: QRect | QRectF) -> HyperTextEdit:
        """
        Create a hyper-text edit control at the specified offset relative to the anchor point.
        See IComponentGraphics.create_hypertext_edit(rect).
        """
        edit = HyperTextEdit(self)
        rect = self._absolute_rect(rect)
        if isinstance(rect, QRectF):
            rect = rect.toRect()
        edit.setGeometry(rect)
        return edit

    def move_widget(self, widget: QWidget, dx: int, dy: int) -> void:
        """
        Move a widget for a specified delta coordination.
        See IComponentGraphics.move_widget(widget, dx, dy).
        """
        widget.move(widget.x() + dx, widget.y() + dy)

    def clear(self, *, refresh: bool = False) -> void:
        """
        Clear all figures on the canvas.
        :param refresh: if true, update the graphics
        """
        self.figures.clear()
        if refresh:
            self.update()
