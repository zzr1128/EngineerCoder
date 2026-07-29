# -*- coding: utf-8 -*-

from alias import *
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QSize


class SizingDockContent(QWidget):
    def __init__(self, parent: QWidget = None):
        super(SizingDockContent, self).__init__(parent)
        self._preferred_size = super(SizingDockContent, self).sizeHint()

    def sizeHint(self) -> QSize:
        return self._preferred_size

    def setPreferredSize(self, size: QSize) -> void:
        self._preferred_size = size

    def setPreferredWidth(self, width: int) -> void:
        self._preferred_size.setWidth(width)

    def setPreferredHeight(self, height: int) -> void:
        self._preferred_size.setHeight(height)
