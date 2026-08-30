# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from alias import *
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPaintEvent, QPainter, QBrush, QColor


class SizingDockContent(QWidget):
    def __init__(self, parent: Nullable[QWidget] = null):
        super(SizingDockContent, self).__init__(parent)
        self._preferred_size = super(SizingDockContent, self).sizeHint()
        self.brush: Nullable[QBrush] = null

    def setBackgroundColor(self, color: QColor) -> void:
        self.brush = QBrush(color)

    def paintEvent(self, event: QPaintEvent, /) -> void:
        super().paintEvent(event)
        painter = QPainter(self)
        with painter:
            painter.setBrush(self.brush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self.rect())

    def sizeHint(self) -> QSize:
        return self._preferred_size

    def setPreferredSize(self, size: QSize) -> void:
        self._preferred_size = size

    def setPreferredWidth(self, width: int) -> void:
        self._preferred_size.setWidth(width)

    def setPreferredHeight(self, height: int) -> void:
        self._preferred_size.setHeight(height)
