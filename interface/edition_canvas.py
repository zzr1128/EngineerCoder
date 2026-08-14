# -*- coding: utf-8 -*-

from dataclasses import dataclass
from math import ceil

from shiboken6 import getCppPointer
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QWidget, QTextEdit, QLineEdit, QLabel

from alias import *
from alias import Nullable
from core.component import IComponentInterface
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
        self.anchor_stack: IList[QPointF] = []
        self.width_occupy_stack: IList[float] = []
        self.painter: Nullable[QPainter] = null
        self.figures: IList[EditionCanvas.Paintable] = []
        self.widgets: IDictionary[int, tuple[QWidget, EditionCanvas.WidgetAnnotation]] = {}
        self.components: IList[IComponentInterface] = []

    def add_interface(self, component: IComponentInterface) -> void:
        self.components.append(component)

    def remove_interface(self, component: IComponentInterface) -> void:
        self.components.remove(component)

    def paintEvent(self, event: QPaintEvent, /) -> null:
        # When interface updates, remember to update in resizeEvent
        with QPainter(self) as self.painter:
            for figure in self.figures:
                figure.paint(self.painter)  # type: ignore (not null)

            for inter in self.components:
                inter.paint(self)

        self.painter = null

    # noinspection property-definition
    @property
    def _current_anchor(self) -> QPointF:
        if self.anchor_stack:
            return self.anchor_stack[-1]
        else:
            return QPointF()

    def push_anchor(self, anchor: QPoint | QPointF) -> void:  # Can only be called synchronously
        if isinstance(anchor, QPoint):
            anchor = QPointF(anchor)
        self.anchor_stack.append(self._absolute_point(anchor))

    def pop_anchor(self) -> void:  # Can only be called synchronously
        self.anchor_stack.pop()

    def move_anchor(self, dx: int | float, dy: int | float) -> void:  # Can only be called synchronously
        """
        Move the current anchor point by the specified offset.
        Assume there exists at least one anchor.
        """
        p = self.anchor_stack.pop()
        self.anchor_stack.append(QPointF(p.x() + dx, p.y() + dy))

    def external_anchor(self) -> QPointF:  # Can only be called synchronously
        """
        Get the accumulated anchor point except the current one.
        """
        if len(self.anchor_stack) >= 2:
            return QPointF(self.anchor_stack[-2].x(), self.anchor_stack[-2].y())
        return QPointF()

    def push_right_occupation(self, width: int | float) -> void:  # Can only be called synchronously
        """
        Push right occupation of the current anchor.
        See IComponentGraphics.push_right_occupation(width).
        """
        self.width_occupy_stack.append(float(width))

    def pop_occupation(self) -> void:  # Can only be called synchronously
        """
        Pop the last occupation pushed.
        See IComponentGraphics.pop_occupation().
        """
        self.width_occupy_stack.pop()

    @final
    def _absolute_point(self, point: QPoint | QPointF) -> QPointF:
        """
        Absolute position of a point relative to the anchor.
        """
        return QPointF((self._current_anchor.x() + point.x()), (self._current_anchor.y() + point.y()))

    @overload
    def _absolute_rect(self, rect: QRect | QRectF) -> QRectF:
        """
        Absolute position and size of a rectangle relative to the anchor.
        """
        ...

    @overload
    def _absolute_rect(self, rect: null) -> null:
        """
        Absolute position and size of a rectangle relative to the anchor.
        """
        ...

    @final
    def _absolute_rect(self, rect: Nullable[QRect | QRectF]) -> Nullable[QRectF]:
        """
        Absolute position and size of a rectangle relative to the anchor.
        """
        if rect is None:
            return null
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

    def disp_draw_rect(self, rect: QRectF, color: QColor, *, round_radius: int = IComponentGraphics.NotRounded) -> void:
        """
        Paint a disposable (one-off) filled rectangle.
        Once the canvas updated, the figure will be removed.
        See IComponentGraphics.disp_draw_rect(rect, color, *[, round_radius]).
        """
        EditionCanvas.Rectangle(self._absolute_rect(rect), color, round_radius).paint(self.painter)  # type: ignore (not null)

    def draw_frame(self, rect: QRect | QRectF, color: QColor, line_width: int = 2, *,
                   round_radius: int = IComponentGraphics.NotRounded, refresh: bool = False) -> void:
        """
        Paint a wireframe.
        See IComponentGraphics.draw_frame(rect, color[, line_width], *, [round_radius][, refresh]).
        """
        self.figures.append(EditionCanvas.RectangleFrame(self._absolute_rect(rect), color, round_radius, line_width))
        if refresh:
            self.update()

    def disp_draw_frame(self, rect: QRect | QRectF, color: QColor, line_width: int = 2, *,
                        round_radius: int = IComponentGraphics.NotRounded) -> void:
        """
        Paint a disposable (one-off) wireframe.
        Once the canvas updated, the figure will be removed.
        See IComponentGraphics.disp_draw_frame(rect, color[, line_width], *, [round_radius]).
        """
        EditionCanvas.RectangleFrame(self._absolute_rect(rect), color, round_radius, line_width).paint(self.painter)  # type: ignore (not null)

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

    def disp_draw_line(self, start: QPoint | QPointF, end: QPoint | QPointF, color: QColor, line_width: int = 2, *,
                       round_ends: bool = False) -> void:
        """
        Paint a disposable (one-off) line segment.
        Once graphics updated, the figure will be removed unless painting again.
        :param start: the starting point
        :param end: the ending point
        :param color: color of the line
        :param line_width: width of the line
        :param round_ends: when true, the ends are semicircles rather than square

        This method can be called only in painting context.
        """
        EditionCanvas.Line(self._absolute_point(start), self._absolute_point(end),
                           color, line_width, round_ends).paint(self.painter)  # type: ignore (not null)

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

    def disp_draw_triangle(self, p1: QPoint | QPointF, p2: QPoint | QPointF, p3: QPoint | QPointF, color: QColor, *,
                           refresh: bool = False) -> void:
        """
        Paint a disposable (one-off) filled triangle.
        Once graphics updated, the figure will be removed unless painting again.
        :param p1: the 1st vertex
        :param p2: the 2nd vertex
        :param p3: the 3rd vertex
        :param color: filling color
        :param refresh: when true, invalidate graphics and trigger updating later

        This method can be called only in painting context.
        """
        EditionCanvas.Triangle(self._absolute_point(p1), self._absolute_point(p2),
                               self._absolute_point(p3), color).paint(self.painter)  # type: ignore (not null)

    def draw_lines(self, points: IEnumerable[QPoint | QPointF], color: QColor, line_width: int = 2, *,
                   refresh: bool = False) -> void:
        """
        Paint a broken line.
        See IComponentGraphics.draw_lines(points, color, line_width, *, [refresh]).
        """
        self.figures.append(EditionCanvas.BrokenLine([self._absolute_point(p) for p in points], color, line_width))
        if refresh:
            self.update()

    def disp_draw_lines(self, points: IEnumerable[QPoint | QPointF], color: QColor, line_width: int = 2, *,
                        refresh: bool = False) -> void:
        """
        Paint a disposable (one-off) broken line.
        Once graphics updated, the figure will be removed unless painting again.
        :param points: vertexes of the broken line
        :param color: color of the line
        :param line_width: width of the line
        :param refresh: when true, invalidate graphics and trigger updating later

        This method can be called only in painting context.
        """
        EditionCanvas.BrokenLine([self._absolute_point(p) for p in points],
                                 color, line_width).paint(self.painter)  # type: ignore (not null)

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

    # noinspection method-overriding
    @overload
    def disp_draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                       color: QColor, font: QFont, width: int,
                       locate: IComponentGraphics.TextLocate = "baseline") -> void:
        """
        Paint a disposable (one-off) text at specified position of the text baseline.
        Once graphics updated, the figure will be removed unless painting again.
        :param text: text to paint
        :param pos: starting position of the text baseline
        :param color: color of the text
        :param font: font of the text
        :param width: width of the pen
        :param locate: location specification method ("baseline" or "topleft")

        This method can be called only in painting context.
        """
        ...

    # noinspection method-overriding
    @overload
    def disp_draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                       color: QColor, font: QFont, width: int, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
                       wrapping: WrapMode = WrapMode.Null, locate: IComponentGraphics.TextLocate = "baseline") -> void:
        """
        Paint a disposable (one-off) text in the specified rectangle.
        Once graphics updated, the figure will be removed unless painting again.
        :param text: text to paint
        :param pos: outer frame of the text
        :param color: color of the text
        :param font: font of the text
        :param width: width of the pen
        :param alignment: alignment of the text
        :param wrapping: wrapping mode of the text
        :param locate: location specification method ("baseline" or "topleft")

        This method can be called only in painting context.
        """
        ...

    def disp_draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                       color: QColor, font: QFont, width: int,
                       locate: IComponentGraphics.TextLocate = "baseline", **kwargs) -> void:
        if isinstance(pos, (QPoint, QPointF)):
            if locate == "topleft":
                pos = QPointF(pos.x(), pos.y() + TextMeasure(font, text).ascent)
            EditionCanvas.Text(self._absolute_point(pos), text, color, font, width,
                               Qt.AlignmentFlag.AlignLeft, WrapMode.Null).paint(self.painter)  # type: ignore (not null)
        else:
            alignment = kwargs.get('alignment', Qt.AlignmentFlag.AlignLeft)
            wrapping = kwargs.get('wrapping', WrapMode.Null)
            if locate == "topleft":
                pos = QRectF(pos.x(), pos.y() + TextMeasure(font, text).ascent, pos.width(), pos.height())
            EditionCanvas.Text(self._absolute_rect(pos), text, color, font, width,
                               alignment, wrapping).paint(self.painter)  # type: ignore (not null)

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
        edit.setFixedSize(r.size())
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
        edit.setFixedSize(r.size())
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
        edit.fitSize()
        return edit

    def create_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, font: QFont, /) -> QLabel:
        """
        See three overloads of the method IComponentGraphics.create_text(text, position) and
        IComponentGraphics.create(text, rect) in the super class.
        """
        if isinstance(pos, (QPoint, QPointF)):  # create_text(text, position, font)
            assert font is not None, "Font is required"
            if isinstance(pos, QPoint):
                pos = QPointF(pos)
            tm = TextMeasure(font, text)
            pos = QRectF(pos.x(), pos.y() + tm.ascent, tm.width, tm.height)
        assert font is not None, "Font is required"

        if isinstance(pos, QRect):
            pos = QRectF(pos)
        label = QLabel(text, self)
        label.setFont(font)
        pos: QRectF = self._absolute_rect(pos)  # type: ignore
        self._register_widget(label, EditionCanvas.WidgetAnnotation(pos))
        EditionCanvas.translate_rect(r := pos.__copy__(), self)
        if isinstance(r, QRectF):
            r = r.toRect()
        label.setGeometry(r)
        label.setFixedSize(r.size())
        return label

    def create_native_label(self, text: string, font: QFont) -> QLabel:
        """
        Create a native ``QLabel`` widget.
        See IComponentGraphics.create_native_label(text, font).
        """
        tm = TextMeasure(font, text)
        label = QLabel(text, self)
        label.setFont(font)
        label.setFixedSize(ceil(tm.width), ceil(tm.height))
        return label

    def label_metric_width(self, label: QLabel, *, modify: bool = False) -> int:
        """
        Get the metric width of the label text.
        See IComponentGraphics.label_metric_width()
        """
        tm = TextMeasure(label.font(), label.text())
        # Advance width matches QLabel rendering; also cover trailing ink overhang
        w = max(ceil(tm.width), ceil(tm.metrics.tightBoundingRect(label.text()).right()))
        if modify:
            label.setFixedWidth(w)
        return w

    def move_widget(self, widget: QWidget, dx: int, dy: int) -> void:
        """
        Move a widget for a specified delta coordination.
        See IComponentGraphics.move_widget(widget, dx, dy).
        """
        widget.move(widget.x() + dx, widget.y() + dy)
        if (key := EditionCanvas._widget_hash(widget)) in self.widgets:
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
        if (key := EditionCanvas._widget_hash(widget)) in self.widgets:
            w, a = self.widgets[key]
            a.rect.setX(x)
            a.rect.setY(y)
            self.widgets[key] = w, a

    def resize_widget(self, widget: QWidget, w: int, h: int) -> void:
        """
        Resize a widget to the specified size.
        See IComponentGraphics.resize_widget(widget, w, h).
        """
        widget.setFixedSize(w, h)
        widget.resize(w, h)

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
        idx = env.rt.get('theme.current_color', (0, 0))
        color = env.theme.colors.components[idx[0]][idx[1]]
        idx = (idx[0] + 1) % len(env.theme.colors.components), 0
        env.rt['theme.current_color'] = idx
        return color

    def next_color(self) -> QColor:
        """
        Acquire next color in the current level as theme color of a component.
        See IComponentGraphics.next_color().
        """
        env = Environment.instance()
        idx = env.rt.get('theme.current_color', (0, 0))
        idx = idx[0], (idx[1] + 1) % len(env.theme.colors.components[idx[0]])
        color = env.theme.colors.components[idx[0]][idx[1]]
        env.rt['theme.current_color'] = idx
        return color

    @property
    def _right_occupied(self) -> float:
        return self.width_occupy_stack[-1] if self.width_occupy_stack else 0.

    @property
    def client_rect(self) -> QRectF:
        """
        See property IComponentInterface.client_rect().
        """
        w = self.size().width() - self._current_anchor.x()
        h = self.size().height() - self._current_anchor.y()
        return QRectF(self._current_anchor.x(), self._current_anchor.y(), w - self._right_occupied, h)

    def delete_widget(self, widget: QWidget) -> void:
        """
        Delete a widget.
        See IComponentGraphics.delete_widget(widget).
        """
        del self.widgets[EditionCanvas._widget_hash(widget)]
        widget.deleteLater()

    def refresh(self) -> void:
        """
        Request the canvas to repaint the whole content as soon as possible.
        See IComponentGraphics.refresh().
        """
        self.update()

    def resizeEvent(self, event: QResizeEvent, /) -> void:
        for w, a in self.widgets.values():
            rect = a.rect.__copy__()
            EditionCanvas.translate_rect(rect, self)
            if rect != a.rect:  # Needs updating geometry
                w.setGeometry(rect.toRect())

        # for inter in self.components:
        #     inter.paint(self, False)
        self.update()
