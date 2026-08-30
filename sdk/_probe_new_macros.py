# -*- coding: utf-8 -*-
"""Probe: the newly added F_*/C_* helper macros register with resolved
locale phrases and render their context arguments correctly."""

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
    maybe_unused(app)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    compiler = Compiler(BuildConfig(UDF))

    names = ('f_profile', 'c_profile', 'f_area', 'f_flux', 'f_flux_i',
             'f_vof', 'f_yi', 'f_rho', 'f_c0', 'f_c1')
    # 1. Every new macro registers with resolved locale phrases
    for name in names:
        meta = env.kit_manager.lookup(f'fluent.{name}')
        assert meta.display_name and meta.display_name != f'{name}_display', name
        assert meta.description and meta.description != f'api_{name}', name
    print('locale phrases ok')

    # 2. The face-gated macros render inside a DEFINE_HEAT_FLUX body
    heat = env.kit_manager.lookup('fluent.heat_flux').component_type(null, graphics)
    heat.interface.edit_name.setText('hf')
    body = heat.interface.edit_body
    expectations = []
    cases = (('f_profile', '2', 'F_PROFILE(f, t0, 2)'),
             ('f_area', 'a', 'F_AREA(a, f, t0)'),
             ('f_flux', '', 'F_FLUX(f, t0)'),
             ('f_flux_i', '1', 'F_FLUX_I(f, t0, 1)'),
             ('f_vof', '', 'F_VOF(f, t0)'),
             ('f_yi', '0', 'F_YI(f, t0, 0)'),
             ('f_rho', '', 'F_RHO(f, t0)'),
             ('f_c0', '', 'F_C0(f, t0)'),
             ('f_c1', '', 'F_C1(f, t0)'))
    for name, field_text, expected in cases:
        comp = body.insert_component(VisualCodeEdit.CompletionEntry(name, f'fluent.{name}'))
        assert comp is not null, f'insert_component({name}) failed'
        if field_text:
            comp.interface.field_edits[0].setPlainText(field_text)
        body.insertPlainText(';\n')
        expectations.append(expected)
    heat.build(compiler)
    product = compiler.products[UDF.id][-1]
    for expected in expectations:
        assert f'{expected};' in product, f'{expected} missing in:\n{product}'
    print('face-gated renders ok')

    # 3. C_PROFILE renders inside a DEFINE_SOURCE body (cell context)
    src = env.kit_manager.lookup('fluent.source').component_type(null, graphics)
    src.interface.edit_name.setText('cs')
    src_body = src.interface.edit_body
    profile = src_body.insert_component(VisualCodeEdit.CompletionEntry('c_profile', 'fluent.c_profile'))
    assert profile is not null, 'insert_component(c_profile) failed'
    profile.interface.field_edits[0].setPlainText('3')
    src_body.insertPlainText(';\n')
    lonely = Compiler(BuildConfig(UDF))
    src.build(lonely)
    assert 'C_PROFILE(c, t, 3);' in lonely.products[UDF.id][-1], lonely.products[UDF.id][-1]
    print('cell-gated render ok')

    # 3a. F_CENTROID: the vector field shows the placeholder hint, and the
    #     call renders with the identifiers the face context provides
    from kits.fluent.localization import _  # Deferred: the singleton order of the probe matters
    centroid = body.insert_component(VisualCodeEdit.CompletionEntry('face_centroid', 'fluent.f_centroid'))
    assert centroid is not null, 'insert_component(face_centroid) failed'
    assert centroid.interface.field_edits[0].placeholderText() == _('placeholder_symbol'), \
        centroid.interface.field_edits[0].placeholderText()
    centroid.interface.field_edits[0].setPlainText('x')
    body.insertPlainText(';\n')
    rebuilt = Compiler(BuildConfig(UDF))
    heat.build(rebuilt)
    assert 'F_CENTROID(x, f, t0);' in rebuilt.products[UDF.id][-1], rebuilt.products[UDF.id][-1]
    print('face centroid placeholder and render ok')

    # 4. The assignment accessors write through their lvalue macros
    set_profile = src_body.insert_component(VisualCodeEdit.CompletionEntry('set_cell_profile', 'fluent.set_cell_profile'))
    assert set_profile is not null, 'insert_component(set_cell_profile) failed'
    set_profile._interface.edit_index.setPlainText('0')
    set_profile._interface.edit_value.setPlainText('300')
    set_temp = src_body.insert_component(VisualCodeEdit.CompletionEntry('set_cell_temperature', 'fluent.set_cell_temperature'))
    assert set_temp is not null, 'insert_component(set_cell_temperature) failed'
    assert not hasattr(set_temp._interface, 'edit_index'), 'a plain accessor carries no index field'
    set_temp._interface.edit_value.setPlainText('293.15')
    assigned = Compiler(BuildConfig(UDF))
    src.build(assigned)
    product = assigned.products[UDF.id][-1]
    assert 'C_PROFILE(c, t, 0) = 300;' in product, product
    assert 'C_T(c, t) = 293.15;' in product, product
    set_face_profile = body.insert_component(VisualCodeEdit.CompletionEntry('set_face_profile', 'fluent.set_face_profile'))
    assert set_face_profile is not null, 'insert_component(set_face_profile) failed'
    set_face_profile._interface.edit_index.setPlainText('2')
    set_face_profile._interface.edit_value.setPlainText('1.5')
    set_face_udmi = body.insert_component(VisualCodeEdit.CompletionEntry('set_face_user_memory', 'fluent.set_face_user_memory'))
    assert set_face_udmi is not null, 'insert_component(set_face_user_memory) failed'
    set_face_udmi._interface.edit_index.setPlainText('1')
    set_face_udmi._interface.edit_value.setPlainText('2')
    assigned_face = Compiler(BuildConfig(UDF))
    heat.build(assigned_face)
    product = assigned_face.products[UDF.id][-1]
    assert 'F_PROFILE(f, t0, 2) = 1.5;' in product, product
    assert 'F_UDMI(f, t0, 1) = 2;' in product, product
    print('assignment accessors render ok')

    # 4a. The assignment accessors refuse a contextless position
    for name in ('set_cell_profile', 'set_face_profile', 'set_cell_temperature'):
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        try:
            comp.build(compiler)
            raise AssertionError(f'{name} must reject a contextless position')
        except Compiler.CompileError:
            pass
    print('assignment gating ok')

    # 5. The face-gated macros refuse a contextless position
    for name in names:
        if name == 'c_profile':
            continue
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        try:
            comp.build(compiler)
            raise AssertionError(f'{name} must reject a contextless position')
        except Compiler.CompileError:
            pass
    print('ALL PASSED')


if __name__ == '__main__':
    main()
