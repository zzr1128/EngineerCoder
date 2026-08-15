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
        # The tab widget is the scroll area wrapping the canvas
        container = self.widget(index)
        canvas = container.findChild(EditionCanvas) if container is not null else null
        self.removeTab(index)
        if canvas is not null:
            self.editor.remove_canvas(canvas)
