# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QWidget, QTabWidget

from alias import *
from interface.edition_canvas import EditionCanvas


class EditorTabWidget(QTabWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.editor = null
        self.tabCloseRequested.connect(self.onRemoveTab)

    def setEditor(self, editor) -> void:
        self.editor = editor

    def onRemoveTab(self, index: int) -> void:
        canvas: EditionCanvas = cast(EditionCanvas, self.widget(index))
        self.removeTab(index)
        self.editor.remove_canvas(canvas)
