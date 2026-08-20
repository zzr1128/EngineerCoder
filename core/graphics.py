# -*- coding: utf-8 -*-

import enum
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF
from PySide6.QtWidgets import QWidget, QLineEdit, QTextEdit, QLabel, QCheckBox, QComboBox

from alias import *

if TYPE_CHECKING:
    from core.component import IComponentInterface
    from core.hyper_text_edit import HyperTextEdit
    from interface.visual_code_edit import VisualCodeEdit


@final
class WrapMode(enum.IntEnum):
    Null = 0
    Word = Qt.TextFlag.TextWordWrap
    Anywhere = Qt.TextFlag.TextWrapAnywhere


@final
class TextMeasure:
    @overload
    def __init__(self, metrics: QFontMetrics | QFontMetricsF, text: string, /): ...

    @overload
    def __init__(self, font: QFont, text: string, /): ...

    def __init__(self, ft: QFontMetrics | QFontMetricsF | QFont, text: string, /):
        if isinstance(ft, QFont):
            self.metrics = QFontMetricsF(ft)
        else:
            self.metrics = ft if isinstance(ft, QFontMetricsF) else QFontMetricsF(ft)
        self.text = text

    # noinspection property-definition
    @property
    def width(self) -> int | float:
        return self.metrics.horizontalAdvance(self.text)

    # noinspection property-definition
    @property
    def height(self) -> int | float:
        return self.metrics.height()

    # noinspection property-definition
    @property
    def ascent(self) -> int | float:
        """
        :return: height from text top to baseline
        """
        return self.metrics.ascent()

    # noinspection property-definition
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
            box = QRect(0, 0, int(width), 2147483647)
        else:
            box = QRectF(0, 0, width, 1.797693134862315E+308)
        return self.metrics.boundingRect(box, wrapping, self.text)


class IComponentGraphics:
    FillWidth = -1
    FillHeight = -1
    NotRounded: int = 0

    @pure_virtual
    def push_anchor(self, anchor: QPointF) -> void:
        """
        Push an anchor point into the anchor_stack.

        The position of the anchor is relative to that of the previous one (or topleft of the
        client area if anchor_stack is empty).
        When locating a position or figure, the anchor is taken as the origin.

        :param anchor: the anchor point to be pushed
        """
        raise NotImplementedError

    @pure_virtual
    def pop_anchor(self) -> void:
        """
        Pop the last anchor point from the anchor_stack.
        """
        raise NotImplementedError

    @pure_virtual
    def move_anchor(self, dx: int | float, dy: int | float) -> void:
        """
        Move the current anchor point by the specified offset.
        :param dx: horizontal offset
        :param dy: vertical offset
        """
        raise NotImplementedError

    @pure_virtual
    def external_anchor(self) -> QPointF:
        """
        Get the accumulated anchor point except the current one.
        """
        raise NotImplementedError

    @pure_virtual
    def push_right_occupation(self, width: int | float) -> void:
        """
        Push right occupation of the current anchor.
        When acquiring the client rectangle, the pushed occupation is not contained.
        :param width: occupied width
        """
        raise NotImplementedError

    @pure_virtual
    def pop_occupation(self) -> void:
        """
        Pop the last occupation pushed.
        """
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
    def disp_draw_rect(self, rect: QRectF, color: QColor, *,
                       round_radius: int = NotRounded) -> void:
        """
        Paint a disposable (one-off) filled rectangle.
        Once graphics updated, the figure will be removed unless painting again.
        :param rect: position and size of the rectangle
        :param color: filling color
        :param round_radius: radius of the rounded angles; NotRound if square

        This method can be called only in painting context.
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
    def disp_draw_frame(self, rect: QRect | QRectF, color: QColor, line_width: int = 2, *,
                        round_radius: int = NotRounded) -> void:
        """
        Paint a disposable (one-off) wireframe.
        Once graphics updated, the figure will be removed unless painting again.
        :param rect: the outer frame rectangle
        :param color: filling color
        :param line_width: width of wireframe lines
        :param round_radius: radius of the rounded angles; NotRound if square

        This method can be called only in painting context.
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

    @pure_virtual
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
        raise NotImplementedError

    type TextLocate = Literal["baseline", "topleft"]

    @overload
    @pure_virtual
    # pyrefly: ignore [inconsistent-overload]
    def draw_text(self, text: string, position: QPoint | QPointF, /, *,
                  color: QColor, font: QFont, width: int, locate: TextLocate = "baseline", refresh: bool = False) -> void:
        """
        Paint a text at specified position of the text baseline.
        :param text: text to paint
        :param position: starting position of the text baseline
        :param color: color of the text
        :param font: font of the text
        :param width: width of the pen
        :param locate: location specification method ("baseline" or "topleft")
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        ...

    @overload
    @pure_virtual
    # pyrefly: ignore [inconsistent-overload]
    def draw_text(self, text: string, rect: QRect | QRectF, /, *,
                  color: QColor, font: QFont, width: int, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
                  wrapping: WrapMode = WrapMode.Null, locate: TextLocate = "baseline", refresh: bool = False) -> void:
        """
        Paint a text in the specified rectangle.
        :param text: text to paint
        :param rect: outer frame of the text
        :param color: color of the text
        :param font: font of the text
        :param width: width of the pen
        :param alignment: alignment of the text
        :param wrapping: wrapping mode of the text
        :param locate: location specification method ("baseline" or "topleft")
        :param refresh: when true, invalidate graphics and trigger updating later
        """
        ...

    # Implementation of overloads
    @pure_virtual
    def draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                  color: QColor, font: QFont, width: int, **kwargs) -> void:
        raise NotImplementedError

    @overload
    @pure_virtual
    def disp_draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                       color: QColor, font: QFont, width: int, locate: TextLocate = "baseline") -> void:
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

    @overload
    @pure_virtual
    def disp_draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                       color: QColor, font: QFont, width: int, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
                       wrapping: WrapMode = WrapMode.Null, locate: TextLocate = "baseline") -> void:
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

    @pure_virtual
    def disp_draw_text(self, text: string, pos: QPoint | QPointF | QRect | QRectF, /, *,
                  color: QColor, font: QFont, width: int, **kwargs) -> void:
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
    def create_hypertext_edit(self, rect: QRect | QRectF) -> 'HyperTextEdit':
        """
        Create a hyper-text edit control at the specified offset relative to the anchor point.
        :param rect: offset position and size
        """
        raise NotImplementedError

    @pure_virtual
    def create_visual_code_edit(self, rect: QRect | QRectF) -> 'VisualCodeEdit':
        """
        Create a visual-code edit control at the specified offset relative to the anchor point.
        :param rect: offset position and size
        """
        raise NotImplementedError

    @overload
    @pure_virtual
    def create_text(self, text: string, rect: QRect | QRectF, font: QFont, /) -> QLabel:
        """
        Create a text control within the specified rectangle.
        :param text: text to show
        :param rect: rectangle that restricts the text area
        :param font: font of the text
        """
        ...

    @overload
    @pure_virtual
    def create_text(self, text: string, position: QPoint | QPointF, font: QFont, /) -> QLabel:
        """
        Create a text control at the specified position.
        :param text: text to show
        :param position: position where the topleft of the control locates
        :param font: font of the text
        """
        ...

    # Implementation of overloads
    @pure_virtual
    def create_text(self, text: string, pos_or_font: QPoint | QPointF | QRect | QRectF, font: QFont, /) -> QLabel:
        raise NotImplementedError

    @pure_virtual
    def create_native_label(self, text: string, font: QFont) -> QLabel:
        """
        Create a native ``QLabel`` widget.
        :param text: text of the label
        :param font: font of the label

        This method will automatically compute the size of the label.
        """
        raise NotImplementedError

    @pure_virtual
    def create_checkbox(self, text: string, font: QFont) -> QCheckBox:
        """
        Create a check box control.
        :param text: text of the check box
        :param font: font of the check box

        This method will automatically compute the size of the check box.
        """
        raise NotImplementedError

    @pure_virtual
    def create_combobox(self, rect: QRect | QRectF) -> QComboBox:
        """
        Create a drop-down selection control at the specified offset relative to the anchor point.
        :param rect: offset position and size
        """
        raise NotImplementedError

    @pure_virtual
    def label_metric_width(self, label: QLabel, *, modify: bool = False) -> int:
        """
        Get the metric width of the label text.
        :param label: the label widget that contains text
        :param modify: when ``True``, modify the label text to be the metric width
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

    @pure_virtual
    def relocate_widget(self, widget: QWidget, x: int, y: int) -> void:
        """
        Relocate a widget to a specified coordination.
        :param widget: the widget to relocate
        :param x: horizonal coordination
        :param y: vertical coordination
        """
        raise NotImplementedError

    @pure_virtual
    def resize_widget(self, widget: QWidget, w: int, h: int) -> void:
        """
        Resize a widget to the specified size.
        :param widget: the widget to resize
        :param w: width
        :param h: height
        """
        raise NotImplementedError

    @property
    @pure_virtual
    def client_rect(self) -> QRectF:
        """
        :return: the client rectangle relative to the current anchor point.
        """
        raise NotImplementedError

    @pure_virtual
    def alloc_color(self) -> QColor:
        """
        Allocate a color to be used as theme color of a component.
        :return: theme color available
        """
        raise NotImplementedError

    @pure_virtual
    def next_color(self) -> QColor:
        """
        Acquire next color in the current level as theme color of a component.
        :return: theme color available
        """
        raise NotImplementedError

    @pure_virtual
    def delete_widget(self, widget: QWidget) -> void:
        """
        Delete a widget.
        :param widget: the widget to delete
        """
        raise NotImplementedError

    @pure_virtual
    def refresh(self) -> void:
        """
        Request the canvas to repaint the whole content as soon as possible.
        Use this when the visual content becomes stale without any widget geometry change
        covering the dirty region (e.g. layout space of a component changed).
        """
        raise NotImplementedError

    @pure_virtual
    def add_interface(self, component: 'IComponentInterface', right_occupation: int | float = 0.) -> void:
        """
        Register a component interface so that it will be painted on the graphics canvas.
        :param component: the component interface to add
        :param right_occupation: right occupation of the client area of the interface; while the
            interface is painted, the client rectangle it acquires is narrowed by this width.
            This is used when the interface is placed inline inside another widget (e.g. a
            visual code edit) whose column does not extend to the right edge of the canvas.
        """
        raise NotImplementedError

    @pure_virtual
    def remove_interface(self, component: 'IComponentInterface') -> void:
        """
        Unregister a component interface so that it will no longer be painted.
        :param component: the component interface to remove
        """
        raise NotImplementedError
