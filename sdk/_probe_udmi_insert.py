# -*- coding: utf-8 -*-
"""Probe: inserting the C_UDMI reader and the set_udmi writer must construct
their interfaces without error (regression: edit_index entered the layout
without graphics, which HyperTextEdit elements refuse)."""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from interface.visual_code_edit import VisualCodeEdit


class _CanvasStub(QWidget):
    def __init__(self):
        super().__init__()
        self.interfaces: IList[Any] = []

    def add_interface(self, component: Any, right_occupation: float = 0.) -> void:
        self.interfaces.append(component)

    def remove_interface(self, component: Any) -> void:
        if component in self.interfaces:
            self.interfaces.remove(component)


def _noop(*args, **kwargs):
    maybe_unused(args, kwargs)
    return None


class _GraphicsStub(IComponentGraphics):
    def __init__(self, canvas: _CanvasStub):
        self.canvas = canvas

    def create_visual_code_edit(self, rect) -> VisualCodeEdit:
        return VisualCodeEdit(self.canvas, self)

    def create_hypertext_edit(self, rect) -> HyperTextEdit:
        return HyperTextEdit(self.canvas)

    def create_lineedit(self, rect) -> QLineEdit:
        edit = QLineEdit(self.canvas)
        edit.setFixedSize(int(rect.width()), int(rect.height()))
        return edit

    def create_checkbox(self, text: string, font) -> QCheckBox:
        box = QCheckBox(text, self.canvas)
        box.setFont(font)
        hint = box.sizeHint()
        box.setFixedSize(hint.width(), hint.height())
        return box

    def create_combobox(self, rect) -> QComboBox:
        box = QComboBox(self.canvas)
        box.setFixedSize(int(rect.width()), int(rect.height()))
        return box

    def create_native_label(self, text: string, font) -> QLabel:
        return QLabel(text, self.canvas)

    def label_metric_width(self, label: QLabel, *, modify: bool = False) -> int:
        if modify:
            label.setFixedWidth(40)
        return 40

    def alloc_color(self) -> QColor:
        return QColor('#4488CC')

    @property
    def client_rect(self) -> QRectF:
        return QRectF(0, 0, 600, 400)

    def add_interface(self, component: Any, right_occupation: float = 0.) -> void:
        self.canvas.add_interface(component, right_occupation)

    def remove_interface(self, component: Any) -> void:
        self.canvas.remove_interface(component)


for _name in dir(IComponentGraphics):
    if not _name.startswith('_') and callable(getattr(IComponentGraphics, _name)) \
            and _name not in vars(_GraphicsStub):
        setattr(_GraphicsStub, _name, staticmethod(_noop))


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)

    # An explicit completion entry bypasses the level filter, so a plain edit
    # suffices to exercise the construction path
    host = graphics.create_visual_code_edit(QRectF(0, 0, 600, 200))

    reader = host.insert_component(VisualCodeEdit.CompletionEntry('cell_user_memory', 'fluent.c_udmi'))
    assert reader is not null, 'insert_component(cell_user_memory) failed'
    reader.interface.edit_index.setPlainText('0')
    host.insertPlainText('\n')
    writer = host.insert_component(VisualCodeEdit.CompletionEntry('set_udmi', 'fluent.set_udmi'))
    assert writer is not null, 'insert_component(set_udmi) failed'
    writer.interface.edit_index.setPlainText('1')
    writer.interface.edit_value.setPlainText('3.14')
    print('insert_component(cell_user_memory / set_udmi) ok')
    print('ALL PASSED')


if __name__ == '__main__':
    main()
