# -*- coding: utf-8 -*-

from dataclasses import dataclass
import enum
from math import ceil

from PySide6.QtCore import QRectF, QSizeF
from PySide6.QtWidgets import QWidget

from alias import *
from alias import Nullable
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit


class CLLibrary:
    """
    Namespace of the Common Language Library (``CLLibrary``).
    """

    class GLinearLayout:
        """
        [Graphics] Linear layout for component interfaces.
        """
        FillWidth: float = 0.

        class ElementRowPolicy(enum.IntEnum):
            ReqBrkPre = 0x01  # Require break line before it
            ReqBrkPost = 0x02  # Require break line after it
            ReqCclBrk = 0x04  # Require cancelling break line before it

            Default = 0                         # Wrap as needed
            Exclusive = ReqBrkPre | ReqBrkPost  # Occupy a whole row
            Break = ReqBrkPost                  # Break line after it
            New = ReqBrkPre                     # Break line before it
            NoBreak = ReqCclBrk                 # No break line before it

        @dataclass
        class _Element:
            widget: QWidget
            width: float
            height: float
            row_policy: 'CLLibrary.GLinearLayout.ElementRowPolicy'

        def __init__(self, *, margin: float = 5., horizonal_padding: float = 5., vertical_padding: float = 10.):
            self.margin: float = margin
            self.horizonal_padding: float = horizonal_padding
            self.vertical_padding: float = vertical_padding

            self._box_size = QSizeF()
            self._valid = False

            self.elements: IList[CLLibrary.GLinearLayout._Element] = []
            self._geometries: IList[QRectF] = []
            # These two lists parallel

        def size(self, graphics: IComponentGraphics) -> QSizeF:
            if self.invalidated:
                self._compute_geometries(graphics.client_rect)
            return self._box_size

        @overload
        def add_element(self, widget: HyperTextEdit, row_policy: Nullable[ElementRowPolicy] = ElementRowPolicy.Default,
                        width: float | int | null = null, height: float | int | null = null, *,
                        graphics: Nullable[IComponentGraphics]) -> void:
            ...

        @overload
        def add_element(self, widget: QWidget, row_policy: Nullable[ElementRowPolicy] = ElementRowPolicy.Default,
                        width: float | int | null = null, height: float | int | null = null, *,
                        graphics: Nullable[IComponentGraphics] = null) -> void:
            ...

        def add_element(self, widget: QWidget, row_policy: Nullable[ElementRowPolicy] = ElementRowPolicy.Default,
                        width: float | int | null = null, height: float | int | null = null, *,
                        graphics: Nullable[IComponentGraphics] = null) -> void:
            """
            Add an element to the layout next to existing elements.
            :param widget: the widget to add
            :param row_policy: policy how the element occupies space in a row; null for default
            :param width: declared width of the widget
            :param height: declared width of the widget
            :param graphics: graphics interface (needed if widget is a ``HyperTextEdit``)

            Parameters ``width`` and ``height`` is **declared**, which means they are not absolutely equal to the real
            size of the widget. Usually, when they are positive, the values equalize to the widget size; otherwise,
            the values are relative to the parent client rectangle.

            This triggers invalidation of computed geometries.

            If the widget is an instance of ``HyperTextEdit``, besides adding the element to the layout,
            it will also connect ``layoutSpaceChanged`` signal to library internal slot to update the
            layout when needed (usually when contents change and size is modified).
            """
            if row_policy is null:
                row_policy = CLLibrary.GLinearLayout.ElementRowPolicy.Default

            element = CLLibrary.GLinearLayout._Element(widget,
                                                       widget.width() if width is None else round(width),
                                                       widget.height() if height is None else round(height),
                                                       row_policy)
            self.elements.append(element)
            self.invalidate()

            if isinstance(widget, HyperTextEdit):
                if graphics is null:
                    raise TypeError('graphics is not nullable when widget is a HyperTextEdit')
                widget.layoutSpaceChanged.connect(lambda: self._on_layout_space_change(graphics, element))

        def _on_layout_space_change(self, graphics: IComponentGraphics, element: _Element) -> void:
            if element.width > 0:
                element.width = element.widget.width()
            if element.height > 0:
                element.height = element.widget.height()

            self.invalidate()
            graphics.refresh()

        def update(self, graphics: IComponentGraphics) -> void:
            """
            Update the layout.
            :param graphics: graphic interface

            This method can be called only in painting context.
            """
            if self.invalidated:
                self._compute_geometries(graphics.client_rect)
            for element, geometry in zip(self.elements, self._geometries):
                graphics.relocate_widget(element.widget, round(geometry.x()), round(geometry.y()))
                # graphics.resize_widget(element.widget, round(geometry.width()), round(geometry.height()))

        @property
        def invalidated(self) -> bool:
            return not self._valid

        def invalidate(self) -> void:
            """
            Invalidate the computed geometries.
            After invalidation, recomputation is lazily triggered when accessing geometries (e.g. ``update``).
            """
            self._valid = False

        def _compute_geometries(self, container: QRectF | QWidget) -> void:
            if isinstance(container, QWidget):
                container = QRectF(container.rect())

            # An FSM in essence
            lines: IList[IList['CLLibrary.GLinearLayout._Element']] = []
            width: float = self.margin
            req_brk = False  # Require break line

            if self.elements:
                lines.append([])

            for element in self.elements:
                try:
                    if (not (element.row_policy & CLLibrary.GLinearLayout.ElementRowPolicy.ReqCclBrk) and
                        (((element.row_policy & CLLibrary.GLinearLayout.ElementRowPolicy.ReqBrkPre)  # Current policy
                              or req_brk  # Policy of previous element
                             ) and width > 0  # Avoid empty line
                            )):
                            lines.append([])
                            width = self.margin
                            # Before the element
                            if element.width <= CLLibrary.GLinearLayout.FillWidth:
                                element_width = max(element.width + container.width() - width - self.margin, 0.)
                                element.widget.setFixedWidth(ceil(element_width))
                            else:
                                element_width = element.width
                            assert False  # Jump out

                    # Before the element
                    if element.width <= CLLibrary.GLinearLayout.FillWidth:
                        element_width = max(element.width + container.width() - width - self.margin, 0.)
                        element.widget.setFixedWidth(ceil(element_width))
                    else:
                        element_width = element.width

                    if (not (element.row_policy & CLLibrary.GLinearLayout.ElementRowPolicy.ReqCclBrk) and
                            (lines[-1] and width + element_width + self.margin + self.horizonal_padding > container.width()) and width > 0):  # Beyond the width limit
                        lines.append([])
                        width = self.margin
                except AssertionError:
                    pass
                finally:
                    req_brk = False  # Reset

                # The element
                lines[-1].append(element)
                width += element_width + self.horizonal_padding

                # After the element
                if element.row_policy & CLLibrary.GLinearLayout.ElementRowPolicy.ReqBrkPost:
                    req_brk = True

            self._geometries.clear()
            height = self.margin
            box_width = 0.
            for line in lines:
                width = self.margin
                line_height = 0.
                for element in line:
                    element_width = container.width() - width if element.width <= CLLibrary.GLinearLayout.FillWidth else element.width
                    self._geometries.append(QRectF(width, height, element_width, element.height))
                    width += element_width + self.horizonal_padding
                    line_height = max(line_height, element.height)
                height += line_height + self.vertical_padding
                box_width = max(box_width, width + self.margin - self.horizonal_padding)
            box_height = height + self.margin - self.vertical_padding
            self._box_size = QSizeF(box_width, box_height)
            self._valid = True
