# -*- coding: utf-8 -*-
"""
Headless check of the delegation mechanism:

- delegations buffered in ``kits.fluent`` resolve onto the CLK components even
  when the fluent kit is imported **before** the common kit (pending retry);
- ``Component.build`` dispatches unsupported languages to the delegation and
  rejects languages no delegation serves;
- nested components embedded in visual code edits compile recursively into
  UDF (C) source.
"""

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
from core.component import ComponentMetadata
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.meta import SupportedLanguage
from interface.visual_code_edit import VisualCodeEdit
from kits.fluent.fluent import UDF


class _CanvasStub(QWidget):
    """Stands in for the canvas: the nearest ancestor providing ``add_interface``."""

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
    """Minimal graphics implementation sufficient for headless construction."""

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


# Everything else of IComponentGraphics is irrelevant for this check
for _name in dir(IComponentGraphics):
    if not _name.startswith('_') and callable(getattr(IComponentGraphics, _name)) \
            and _name not in vars(_GraphicsStub):
        setattr(_GraphicsStub, _name, staticmethod(_noop))


CLK_COMPONENTS = ('native', 'br', 'loop', 'for', 'assign',
                  'plus', 'minus', 'multiply', 'divide', 'modulus',
                  'greater', 'less', 'greater_equal', 'less_equal', 'equal', 'not_equal',
                  'field')


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    # 1. Importation order: fluent first, its delegations stay pending because
    #    the delegated CLK components are not registered yet
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    assert len(env.kit_manager['fluent'].delegation_buffer) == 17, \
        f'delegations should stay pending, got {len(env.kit_manager["fluent"].delegation_buffer)}'
    try:
        env.kit_manager.lookup('clk.br')
        raise AssertionError('clk should not be imported yet')
    except LookupError:
        pass
    print('pending delegation buffer ok')

    env.import_kit(os.path.join(_root, 'kits', 'common'))

    # 2. Flushing happened automatically: every CLK component now serves UDF
    assert env.kit_manager['fluent'].delegation_buffer == [], \
        'delegation buffer should be flushed after the delegated kit is imported'
    for name in CLK_COMPONENTS:
        meta = env.kit_manager.lookup(f'clk.{name}')
        assert meta.support_language(UDF), f'clk.{name} should support UDF through delegation'
        assert meta.delegations.valid(UDF) == ComponentMetadata.Delegation.VALID, \
            f'clk.{name} delegation should be valid for UDF'
    print('delegation resolution ok')

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    compiler = Compiler(BuildConfig(UDF))

    # 3. Branch with a nested assignment component inside its then-edit
    branch = env.kit_manager.lookup('clk.br').component_type(null, graphics)
    branch.interface.edit_cond.setPlainText('x > 0.0')
    edit_then = branch.interface.edit_then
    assign = edit_then.insert_component(edit_then._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('velocity')
    assign.interface.edit_value.setPlainText('1.5')
    assign.interface.check_constant.setChecked(True)
    cursor = edit_then.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit_then.setTextCursor(cursor)
    edit_then.insertPlainText('\nMessage("done");')

    branch.build(compiler)
    expected = ('if (x > 0.0) {\n'
                '    const real velocity = 1.5;\n'
                '    Message("done");\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('branch delegation compile ok:')
    print(expected)

    # 4. Expression composition: an operator component nested in a value edit
    assign2 = env.kit_manager.lookup('clk.assign').component_type(null, graphics)
    assign2.interface.edit_name.setPlainText('sum')
    edit_value = assign2.interface.edit_value
    plus = edit_value.insert_component(edit_value._lookup_entry('plus'))
    assert plus is not null, 'insert_component(plus) failed'
    plus.interface.edit_left.setPlainText('a')
    plus.interface.edit_right.setPlainText('b')
    assign2.build(compiler)
    assert compiler.products[UDF.id][-1] == 'sum = (a + b);', compiler.products[UDF.id][-1]
    print('nested operator delegation compile ok:', compiler.products[UDF.id][-1])

    # 5. Remaining statement delegations
    loop = env.kit_manager.lookup('clk.loop').component_type(null, graphics)
    loop.interface.edit_cond.setPlainText('i < 10')
    loop.interface.edit_body.setPlainText('i = i + 1;')
    loop.build(compiler)
    expected = 'while (i < 10) {\n    i = i + 1;\n}'
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('loop delegation compile ok:')
    print(expected)

    for_ = env.kit_manager.lookup('clk.for').component_type(null, graphics)
    for_.interface.edit_count.setPlainText('3')
    for_.interface.edit_body.setPlainText('Message("tick");')
    for_.build(compiler)
    expected = 'for (int i = 0; i < (3); ++i) {\n    Message("tick");\n}'
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('for delegation compile ok:')
    print(expected)

    # Nested count loops occupy i, j, ... in turn while enclosing scopes hold them
    outer = env.kit_manager.lookup('clk.for').component_type(null, graphics)
    outer.interface.edit_count.setPlainText('2')
    edit_body = outer.interface.edit_body
    inner = edit_body.insert_component(edit_body._lookup_entry('for'))
    assert inner is not null, 'insert_component(for) failed'
    inner.interface.edit_count.setPlainText('3')
    inner.interface.edit_body.setPlainText('Message("tick");')
    outer.build(compiler)
    expected = ('for (int i = 0; i < (2); ++i) {\n'
                '    for (int j = 0; j < (3); ++j) {\n'
                '        Message("tick");\n'
                '    }\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('nested for delegation compile ok:')
    print(expected)

    # Once i, j, k are all occupied, naming falls back to _ec_xxx
    deep = env.kit_manager.lookup('clk.for').component_type(null, graphics)
    deep.interface.edit_count.setPlainText('2')
    level = deep
    for _ in range(3):
        edit_body = level.interface.edit_body
        level = edit_body.insert_component(edit_body._lookup_entry('for'))
        assert level is not null, 'insert_component(for) failed'
        level.interface.edit_count.setPlainText('2')
    level.interface.edit_body.setPlainText('Message("deep");')
    deep.build(compiler)
    expected = ('for (int i = 0; i < (2); ++i) {\n'
                '    for (int j = 0; j < (2); ++j) {\n'
                '        for (int k = 0; k < (2); ++k) {\n'
                '            for (int _ec_1 = 0; _ec_1 < (2); ++_ec_1) {\n'
                '                Message("deep");\n'
                '            }\n'
                '        }\n'
                '    }\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('occupation fallback compile ok:')
    print(expected)

    # An explicit counter name is used as is (and occupied for nested scopes)
    named = env.kit_manager.lookup('clk.for').component_type(null, graphics)
    named.interface.edit_count.setPlainText('3')
    named.interface.edit_counter.setText('tick_index')
    named.interface.edit_body.setPlainText('Message("tick");')
    named.build(compiler)
    expected = ('for (int tick_index = 0; tick_index < (3); ++tick_index) {\n'
                '    Message("tick");\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('named counter delegation compile ok:')
    print(expected)

    # Occupations are released when a loop body ends: siblings restart at i
    for_.build(compiler)
    assert compiler.products[UDF.id][-1] == 'for (int i = 0; i < (3); ++i) {\n    Message("tick");\n}', \
        compiler.products[UDF.id][-1]
    print('occupation release ok')

    native = env.kit_manager.lookup('clk.native').component_type(null, graphics)
    native.interface.edit_code.setPlainText('real area = 2.0 * 3.0;')
    native.build(compiler)
    assert compiler.products[UDF.id][-1] == 'real area = 2.0 * 3.0;'
    print('native delegation compile ok:', compiler.products[UDF.id][-1])

    field = env.kit_manager.lookup('clk.field').component_type(null, graphics)
    field.interface.edit_owner.setPlainText('cell')
    field.interface.edit_member.setPlainText('volume')
    field.build(compiler)
    assert compiler.products[UDF.id][-1] == 'cell.volume'
    print('field delegation compile ok:', compiler.products[UDF.id][-1])

    for keyword, symbol in (('plus', '+'), ('minus', '-'), ('multiply', '*'),
                            ('divide', '/'), ('modulus', '%'), ('greater', '>'),
                            ('less', '<'), ('greater_equal', '>='), ('less_equal', '<='),
                            ('equal', '=='), ('not_equal', '!=')):
        op = env.kit_manager.lookup(f'clk.{keyword}').component_type(null, graphics)
        op.interface.edit_left.setPlainText('a')
        op.interface.edit_right.setPlainText('b')
        op.build(compiler)
        assert compiler.products[UDF.id][-1] == f'(a {symbol} b)', (keyword, compiler.products[UDF.id][-1])
    # Legacy fieldless archives still render the bare symbol
    plus_meta = env.kit_manager.lookup('clk.plus')
    assert plus_meta.delegations.delegated(UDF).render({}, compiler) == '+'
    print('operator delegation compile ok')

    # 6. A language no delegation serves is rejected with B1004
    foreign = Compiler(BuildConfig(SupportedLanguage('Python', 'py', null)))
    try:
        branch.build(foreign)
        raise AssertionError('unsupported language was accepted')
    except Compiler.BuildError as e:
        assert e.code == 'B1004', e
        print(f'unsupported language rejection ok: {e}')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
