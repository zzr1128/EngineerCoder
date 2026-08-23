# -*- coding: utf-8 -*-
"""Probe: the API helper macros became components exclusively (no snippet
left); the phase component renders the PHASE_INDEX macro with the thread the
context provides, and the call components resolve their context arguments
while rendering."""

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
from core.build import BuildConfig, Compiler
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from interface.visual_code_edit import VisualCodeEdit
from kits.fluent.fluent import UDF


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
    assert not env.snippets, 'the fluent kit must contribute components exclusively'

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    compiler = Compiler(BuildConfig(UDF))

    # 1. The phase component renders the PHASE_INDEX macro with the thread
    #    the source term carries, and the source closes its body with the
    #    auto-named value the "end DEFINE_SOURCE" statement returns
    src = env.kit_manager.lookup('fluent.source').component_type(null, graphics)
    src.interface.edit_name.setText('phase_src')
    body = src.interface.edit_body
    set_comp = body.insert_component(VisualCodeEdit.CompletionEntry('set_source_const', 'fluent.set_source_const'))
    assert set_comp is not null, 'insert_component(set_source_const) failed'
    phase = set_comp.interface.edit_value.insert_component(
        VisualCodeEdit.CompletionEntry('phase_index', 'fluent.phase_index'))
    assert phase is not null, 'insert_component(phase_index) failed'
    body.insertPlainText('\n')
    end_comp = body.insert_component(VisualCodeEdit.CompletionEntry('end_source', 'fluent.end_source'))
    assert end_comp is not null, 'insert_component(end_source) failed'
    src.build(compiler)
    expected = ('DEFINE_SOURCE(phase_src, c, t, dS, eqn)\n'
                '{\n'
                '    real source = 0.;\n'
                '    source = PHASE_INDEX(t);\n'
                '    return source;\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    # Outside any thread context the phase index refuses to compile
    lonely = Compiler(BuildConfig(UDF))
    try:
        phase.build(lonely)
        raise AssertionError('phase_index must reject a threadless position')
    except Compiler.CompileError:
        pass
    print('phase component ok')

    # 2. The call components resolve their context arguments: a cell loop
    #    provides the cell and the thread, the adjust body the domain
    adjust = env.kit_manager.lookup('fluent.adjust').component_type(null, graphics)
    adjust.interface.edit_name.setText('api_adjust')
    macro_body = adjust.interface.edit_body
    thread_loop = macro_body.insert_component(macro_body._lookup_entry('thread_loop_c'))
    assert thread_loop is not null, 'insert_component(thread_loop_c) failed'
    loop_body = thread_loop.interface.edit_body
    cell_loop = loop_body.insert_component(loop_body._lookup_entry('begin_c_loop'))
    assert cell_loop is not null, 'insert_component(begin_c_loop) failed'
    cell_body = cell_loop.interface.edit_body
    cell_body.setPlainText('real x[ND_ND];\nreal mag;')
    cursor = cell_body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cell_body.setTextCursor(cursor)
    cell_body.insertPlainText('\n')
    centroid = cell_body.insert_component(VisualCodeEdit.CompletionEntry('cell_centroid', 'fluent.c_centroid'))
    assert centroid is not null, 'insert_component(cell_centroid) failed'
    centroid.interface.field_edits[0].setPlainText('x')
    cell_body.insertPlainText(';\n')
    face = cell_body.insert_component(VisualCodeEdit.CompletionEntry('cell_face', 'fluent.c_face'))
    assert face is not null, 'insert_component(cell_face) failed'
    face.interface.field_edits[0].setPlainText('n')
    cell_body.insertPlainText(';\n')
    nv_mag = loop_body.insert_component(VisualCodeEdit.CompletionEntry('NV_MAG', 'fluent.nv_mag'))
    assert nv_mag is not null, 'insert_component(NV_MAG) failed'
    nv_mag.interface.field_edits[0].setPlainText('x')
    loop_body.insertPlainText('\n')
    lookup = loop_body.insert_component(VisualCodeEdit.CompletionEntry('Lookup_Thread', 'fluent.lookup_thread'))
    assert lookup is not null, 'insert_component(Lookup_Thread) failed'
    lookup.interface.field_edits[0].setPlainText('3')
    loop_body.insertPlainText(';\n')
    message = loop_body.insert_component(VisualCodeEdit.CompletionEntry('Message', 'fluent.message'))
    assert message is not null, 'insert_component(Message) failed'
    message.interface.field_edits[0].setPlainText('"done"')
    loop_body.insertPlainText(';\n')
    thread_id = loop_body.insert_component(VisualCodeEdit.CompletionEntry('THREAD_ID', 'fluent.thread_id'))
    assert thread_id is not null, 'insert_component(THREAD_ID) failed'
    loop_body.insertPlainText(';\n')
    adjust.build(compiler)
    product = compiler.products[UDF.id][-1]
    assert 'C_CENTROID(x, c, t);' in product, product
    assert 'C_FACE(c, t, n);' in product, product
    assert 'NV_MAG(x)' in product, product
    assert 'Lookup_Thread(d, 3);' in product, product
    assert 'Message("done");' in product, product
    assert 'THREAD_ID(t);' in product, product
    print('api call components ok:')
    print(product)

    # 3. A face-gated call refuses to compile inside a cell-only context
    f_t = env.kit_manager.lookup('fluent.f_t').component_type(null, graphics)
    try:
        f_t.build(lonely)
        raise AssertionError('F_T must reject a contextless position')
    except Compiler.CompileError:
        pass
    # Serialization round trip through restore
    data = {'fields': [{'text': 'x', 'components': []}]}
    restored = env.kit_manager.lookup('fluent.nv_mag').component_type.restore(data, null, graphics)
    from core.component import serialize
    assert serialize(restored) == data, serialize(restored)
    print('ALL PASSED')


if __name__ == '__main__':
    main()
