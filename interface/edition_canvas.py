# -*- coding: utf-8 -*-

from dataclasses import dataclass

from shiboken6 import getCppPointer
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QWidget, QTextEdit, QLineEdit

from alias import *
from core.environment import Environment
from core.graphics import IComponentGraphics, WrapMode
from core.hyper_text_edit import HyperTextEdit
from graphics import TextMeasure


class EditionCanvas(QWidget, IComponentGraphics):
    class Paintable(Protocol):
        def paint(self, painter: QPainter) -> void: ...

    @overload
    @staticmethod
    def translate_rect(rect: QRectF, painter: QPainter, /) -> void: ...

    @overload
    @staticmethod
    def translate_rect(rect: QRectF, device: QWidget, /) -> void: ...

    @staticmethod
    def translate_rect(rect: QRectF, painting: QPainter | QWidget) -> void:
        if isinstance(painting, QPainter):
            device = painting.device()
        else:
            device = painting
        if rect.width() <= 0:
            rect.setWidth(device.width() - rect.x() + rect.width())
        if rect.height() <= 0:
            rect.setHeight(device.height() - rect.y() + rect.height())

    @overload
    @staticmethod
    def translate_point(point: QPointF, painter: QPainter, /) -> void: ...

    @overload
    @staticmethod
    def translate_point(point: QPointF, device: QWidget, /) -> void: ...

    @staticmethod
    def translate_point(point: QPointF, painting: QPainter | QWidget) -> void:
        if isinstance(painting, QPainter):
            device = painting.device()
        else:
            device = painting
        if point.x() <= 0:
            point.setX(device.width() - point.x())
        if point.y() <= 0:
            point.setY(device.height() - point.y())

    @staticmethod
    def set_pen_color(painter: QPainter, color: QColor) -> void:
        pen: QPen = QPen(color)
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)

    @staticmethod
    def set_brush_color(painter: QPainter, color: QColor) -> void:
        brush: QBrush = QBrush(color, Qt.BrushStyle.SolidPattern)
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
            EditionCanvas.translate_rect(rect := self.rect.__copy__(), painter)

            if self.round_radius == IComponentGraphics.NotRounded:
                painter.drawRect(rect)
            else:
                painter.drawRoundedRect(rect, self.round_radius, self.round_radius)

    @dataclass
    class RectangleFrame:
        rect: QRectF
        color: QColor
        round_radius: int
        line_width: int

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen(painter, self.color, self.line_width)
            EditionCanvas.translate_rect(rect := self.rect.__copy__(), painter)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if self.round_radius == IComponentGraphics.NotRounded:
                painter.drawRect(rect)
            else:
                painter.drawRoundedRect(rect, self.round_radius, self.round_radius)

    @dataclass
    class Line:
        start: QPointF
        end: QPointF
        color: QColor
        line_width: int
        round_ends: bool

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen(painter, self.color, self.line_width)
            EditionCanvas.translate_point(start := self.start.__copy__(), painter)
            EditionCanvas.translate_point(end := self.end.__copy__(), painter)

            painter.drawLine(start, end)

            if self.round_ends:
                painter.drawPoint(start)
                painter.drawPoint(end)

    @dataclass
    class Triangle:
        p1: QPointF
        p2: QPointF
        p3: QPointF
        color: QColor

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen_color(painter, self.color)
            EditionCanvas.set_brush_color(painter, self.color)
            EditionCanvas.translate_point(p1 := self.p1.__copy__(), painter)
            EditionCanvas.translate_point(p2 := self.p2.__copy__(), painter)
            EditionCanvas.translate_point(p3 := self.p3.__copy__(), painter)

            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
            painter.drawLine(p3, p1)

            path = QPainterPath()
            path.moveTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
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
                if isinstance(p := pt.__copy__(), QPoint):
                    p = QPointF(p)
                EditionCanvas.translate_point(p, painter)
                if last is null:
                    last = p
                    continue
                # noinspection bad-argument-type
                lines.append(QLineF(last, p))
                last = p

            EditionCanvas.set_pen(painter, self.color, self.line_width)
            painter.drawLines(lines)

    @dataclass
    class Text:
        position: QPointF | QRectF
        text: string
        color: QColor
        font: QFont
        pen_width: int
        alignment: Qt.AlignmentFlag
        wrapping: WrapMode

        def paint(self, painter: QPainter) -> void:
            EditionCanvas.set_pen(painter, self.color, self.pen_width)
            painter.setFont(self.font)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if isinstance(self.position, QPointF):
                EditionCanvas.translate_point(position := self.position.__copy__(), painter)
                painter.drawText(position, self.text)
            else:
                EditionCanvas.translate_rect(position := self.position.__copy__(), painter)
                painter.drawText(position, self.alignment | self.wrapping, self.text)

    @dataclass
    class WidgetAnnotation:
        rect: QRectF

    def __init__(self, parent):
        super(EditionCanvas, self).__init__(parent)
        self.stack: IList[QPointF] = []
        self.painter: Nullable[QPainter] = null
        self.figures: IList[EditionCanvas.Paintable] = []
        self.widgets: IDictionary[int, tuple[QWidget, EditionCanvas.WidgetAnnotation]] = {}

    def paintEvent(self, event: QPaintEvent, /) -> null:
        with QPainter(self) as self.painter:
            for figure in self.figures:
                figure.paint(self.painter)  # type: ignore (not null)
        self.painter = null

    # noinspection property-definition
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
        return QPointF((self._current_anchor.x() + point.x()), (self._current_anchor.y() + point.y()))

    @final
    def _absolute_rect(self, rect: QRect | QRectF) -> QRectF:
        """
        Absolute position and size of a rectangle relative to the anchor.
        """
        if isinstance(rect, QRect):
            rect = QRectF(rect)
        return QRectF(self._absolute_point(rect.topLeft()), rect.size())

    def draw_rect(self, rect: QRectF, color: QColor, *,
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
        self.figures.append(EditionCanvas.RectangleFrame(self._absolute_rect(rect), color, round_radius, line_width))
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

    # noinspection method-overriding
    @overload
    def draw_text(self, text: string, position: QPoint | QPointF, /, *, color: QColor, font: QFont, width: int,
                  locate: IComponentGraphics.TextLocate = "baseline", refresh: bool = False) -> void:
        """
        Paint a text at specified position of the text baseline.
        See IComponentGraphics.draw_text(text, position, *, color, font, width[, locate][, refresh]).
        """
        ...

    # noinspection method-overriding
    @overload
    def draw_text(self, text: string, rect: QRect | QRectF, /, *,
                  color: QColor, font: QFont, width: int, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
                  wrapping: WrapMode = WrapMode.Null, locate: IComponentGraphics.TextLocate = "baseline",
                  refresh: bool = False) -> void:
        """
        Paint a text in the specified rectangle.
        See IComponentGraphics.draw_text(text, rect, *, color, font, width[, alignment][, wrapping][, refresh]).
        """
        ...

    def draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *, color: QColor, font: QFont,
                  width: int, refresh: bool = False, locate: IComponentGraphics.TextLocate = "baseline", **kwargs):

        if isinstance(pos, (QPoint, QPointF)):  # draw_text(text, position, *, color, font, width[, locate][, refresh])
            if locate == "topleft":
                pos = QPointF(pos.x(), pos.y() + TextMeasure(font, text).ascent)
            self.figures.append(EditionCanvas.Text(self._absolute_point(pos), text, color, font, width, Qt.AlignmentFlag.AlignLeft, WrapMode.Null))
        else:  # draw_text(text, rect, *, color, font, width[, alignment][, wrapping][, locate][, refresh])
            alignment = kwargs.get('alignment', Qt.AlignmentFlag.AlignLeft)
            wrapping = kwargs.get('wrapping', WrapMode.Null)
            if locate == "topleft":
                pos = QRectF(pos.x(), pos.y() + TextMeasure(font, text).ascent, pos.width(), pos.height())
            self.figures.append(EditionCanvas.Text(self._absolute_rect(pos), text, color, font, width, alignment, wrapping))
        if refresh:
            self.update()

    @staticmethod
    def _widget_hash(widget: QWidget) -> int:
        return getCppPointer(widget)[0]

    def _register_widget(self, widget: QWidget, annotation: WidgetAnnotation) -> void:
        self.widgets[EditionCanvas._widget_hash(widget)] = widget, annotation

    def create_lineedit(self, rect: QRect | QRectF) -> QLineEdit:
        """
        Create a single-line edit control at the specified offset relative to the anchor point.
        See IComponentGraphics.create_lineedit(rect).
        """
        edit = QLineEdit(self)
        rect = self._absolute_rect(rect)
        self._register_widget(edit, EditionCanvas.WidgetAnnotation(rect))
        EditionCanvas.translate_rect(r := rect.__copy__(), self)
        if isinstance(r, QRectF):
            r = r.toRect()
        edit.setGeometry(r)
        return edit

    def create_textedit(self, rect: QRect | QRectF) -> QTextEdit:
        """
        Create a multi-line edit control at the specified offset relative to the anchor point.
        See IComponentGraphics.create_textedit(rect).
        """
        edit = QTextEdit(self)
        rect = self._absolute_rect(rect)
        self._register_widget(edit, EditionCanvas.WidgetAnnotation(rect))
        EditionCanvas.translate_rect(r := rect.__copy__(), self)
        if isinstance(r, QRectF):
            r = r.toRect()
        edit.setGeometry(r)
        return edit

    def create_hypertext_edit(self, rect: QRect | QRectF) -> HyperTextEdit:
        """
        Create a hyper-text edit control at the specified offset relative to the anchor point.
        See IComponentGraphics.create_hypertext_edit(rect).
        """
        edit = HyperTextEdit(self)
        rect = self._absolute_rect(rect)
        self._register_widget(edit, EditionCanvas.WidgetAnnotation(rect))
        EditionCanvas.translate_rect(r := rect.__copy__(), self)
        if isinstance(r, QRectF):
            r = r.toRect()
        edit.setGeometry(r)
        return edit

    def move_widget(self, widget: QWidget, dx: int, dy: int) -> void:
        """
        Move a widget for a specified delta coordination.
        See IComponentGraphics.move_widget(widget, dx, dy).
        """
        widget.move(widget.x() + dx, widget.y() + dy)
        if key := EditionCanvas._widget_hash(widget) in self.widgets:
            w, a = self.widgets[key]
            a.rect.setX(a.rect.x() + dx)
            a.rect.setY(a.rect.y() + dy)
            self.widgets[key] = w, a

    def relocate_widget(self, widget: QWidget, x: int, y: int) -> void:
        """
        Relocate a widget to a specified coordination.
        See IComponentGraphics.relocate_widget(widget, x, y).
        """
        target = self._absolute_point(QPoint(x, y)).toPoint()
        if target != widget.pos():
            widget.move(target)
        if key := EditionCanvas._widget_hash(widget) in self.widgets:
            w, a = self.widgets[key]
            a.rect.setX(x)
            a.rect.setY(y)
            self.widgets[key] = w, a

    def clear(self, *, refresh: bool = False) -> void:
        """
        Clear all figures on the canvas, do not clear widgets.
        :param refresh: if true, update the graphics
        """
        self.figures.clear()
        if refresh:
            self.update()

    def alloc_color(self) -> QColor:
        """
        Allocate a color to be used as theme color of a component.
        See IComponentGraphics.alloc_color().
        """
        env = Environment.instance()
        idx = env.rt.get('theme.current_color', 0)
        color = env.theme.colors.components[idx]
        idx = (idx + 1) % len(env.theme.colors.components)
        env.rt['theme.current_color'] = idx
        return color

    def delete_widget(self, widget: QWidget) -> void:
        """
        Delete a widget.
        See IComponentGraphics.delete_widget(widget).
        """
        del self.widgets[EditionCanvas._widget_hash(widget)]
        widget.deleteLater()

    def resizeEvent(self, event: QResizeEvent, /) -> void:
        for w, a in self.widgets.values():
            rect = a.rect.__copy__()
            EditionCanvas.translate_rect(rect, self)
            if rect != a.rect:  # Needs updating geometry
                w.setGeometry(rect.toRect())
