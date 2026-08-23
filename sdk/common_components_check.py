# -*- coding: utf-8 -*-
"""
Headless check of the Common Language Kit components in isolation:

- branch, loops (while/for), native, field (member access) and every
  arithmetic/relation operator register at the expected level;
- each family compiles into UDF source through its delegation, verified by
  rendering the component's serialization archive (the same contract the
  building pipeline consumes);
- expression components nest: an operator embeds another operator and a member
  access in its operand edits, and the rendered source keeps the precedence
  parentheses intact;
- count loops pick explicit counters as given, auto-name free ones (i/j/k) and
  fall back to ``_ec_N`` when those are occupied;
- the whole families round-trip through ``__serialize__``/``restore``;
- an end-to-end build of a branch-rooted script (operators nested inside the
  condition, loops and native code inside the body) produces the exact source.
"""

import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.build import BuildConfig, Compiler
from core.component import ComponentMetadata
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.project import Project
from core.script import Script
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


_OPERATORS: Final[tuple[tuple[string, string], ...]] = (
    ('plus', '+'), ('minus', '-'), ('multiply', '*'), ('divide', '/'), ('modulus', '%'),
    ('greater', '>'), ('less', '<'), ('greater_equal', '>='), ('less_equal', '<='),
    ('equal', '=='), ('not_equal', '!='),
)


def _render(env: Environment, compiler: Compiler, component: Any) -> string:
    """Render a live component through its UDF delegation (archive-based)."""
    meta = env.kit_manager.lookup(env.kit_manager.full_name(component))
    delegation = meta.delegations.delegated(UDF)
    return delegation.render(serialize(component), compiler)


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'cbased'))
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    kit_manager = env.kit_manager
    compiler = Compiler(BuildConfig(UDF))

    # 1. Registration: every family exists at the expected level
    statement_names = ('br', 'loop', 'for', 'native')
    expression_names = ('field',) + tuple(name for name, _ in _OPERATORS)
    for name in statement_names:
        meta = kit_manager.lookup(f'clk.{name}')
        assert meta.level == ComponentMetadata.Level.Statement, (name, meta.level)
    for name in expression_names:
        meta = kit_manager.lookup(f'clk.{name}')
        assert meta.level == ComponentMetadata.Level.Expression, (name, meta.level)
        assert meta.delegations.valid(UDF) == ComponentMetadata.Delegation.VALID, \
            f'{name} has no UDF delegation'
    print('registration ok:', len(statement_names) + len(expression_names), 'components')

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    lookup = kit_manager.lookup

    # 2. Branch: if/else rendering, the else part omitted when empty
    branch = lookup('clk.br').component_type(null, graphics)
    branch.interface.edit_cond.setPlainText('x > 0.0')
    branch.interface.edit_then.setPlainText('total = 1;')
    assert _render(env, compiler, branch) == 'if (x > 0.0) {\n    total = 1;\n}'
    branch.interface.edit_else.setPlainText('total = 0;')
    assert _render(env, compiler, branch) == \
        'if (x > 0.0) {\n    total = 1;\n} else {\n    total = 0;\n}'
    print('branch compile ok')

    # 3. While loop
    loop = lookup('clk.loop').component_type(null, graphics)
    loop.interface.edit_cond.setPlainText('x < 10')
    loop.interface.edit_body.setPlainText('x = x + 1;')
    assert _render(env, compiler, loop) == 'while (x < 10) {\n    x = x + 1;\n}'
    print('loop compile ok')

    # 4. Count loop: explicit counter passes through, auto-naming picks the
    #    first free candidate and falls back to _ec_N when i/j/k are occupied
    for_loop = lookup('clk.for').component_type(null, graphics)
    for_loop.interface.edit_count.setPlainText('3')
    for_loop.interface.edit_counter.setText('idx')
    for_loop.interface.edit_body.setPlainText('Message("tick");')
    assert _render(env, compiler, for_loop) == \
        'for (int idx = 0; idx < (3); ++idx) {\n    Message("tick");\n}'
    for_loop.interface.edit_counter.setText('')
    assert _render(env, compiler, for_loop) == \
        'for (int i = 0; i < (3); ++i) {\n    Message("tick");\n}'
    occupied: HashSet[string] = {'i', 'j', 'k'}
    compiler.products['_ec_counters'] = occupied
    assert _render(env, compiler, for_loop) == \
        'for (int _ec_1 = 0; _ec_1 < (3); ++_ec_1) {\n    Message("tick");\n}'
    del compiler.products['_ec_counters']
    print('count loop compile ok')

    # 5. Native: raw C emitted verbatim (multi-line preserved)
    native = lookup('clk.native').component_type(null, graphics)
    native.interface.edit_code.setPlainText('Message("hi");\nx = 0;')
    assert _render(env, compiler, native) == 'Message("hi");\nx = 0;'
    print('native compile ok')

    # 6. Field (member access)
    field = lookup('clk.field').component_type(null, graphics)
    field.interface.edit_owner.setPlainText('point')
    field.interface.edit_member.setPlainText('x')
    assert _render(env, compiler, field) == 'point.x'
    print('field compile ok')

    # 7. All eleven operators render ``(left symbol right)``
    edit = VisualCodeEdit(canvas, graphics)
    for keyword, symbol in _OPERATORS:
        op = edit.insert_component(edit._lookup_entry(keyword))
        assert op is not null, f'insert_component({keyword}) failed'
        op.interface.edit_left.setPlainText('a')
        op.interface.edit_right.setPlainText('b')
        assert _render(env, compiler, op) == f'(a {symbol} b)', (keyword, _render(env, compiler, op))
    print('operator compile ok:', len(_OPERATORS), 'symbols')

    # 8. Nesting: an operator embeds another operator and a member access in
    #    its operands; the precedence parentheses stay intact
    edit = VisualCodeEdit(canvas, graphics)
    plus = edit.insert_component(edit._lookup_entry('plus'))
    assert plus is not null
    left_edit = plus.interface.edit_left
    multiply = left_edit.insert_component(left_edit._lookup_entry('multiply'))
    assert multiply is not null
    multiply.interface.edit_left.setPlainText('a')
    multiply.interface.edit_right.setPlainText('b')
    right_edit = plus.interface.edit_right
    member = right_edit.insert_component(right_edit._lookup_entry('member'))
    assert member is not null
    member.interface.edit_owner.setPlainText('point')
    member.interface.edit_member.setPlainText('x')
    assert _render(env, compiler, plus) == '((a * b) + point.x)', _render(env, compiler, plus)
    print('nested operator compile ok')

    # 9. Round trips: every family restores from its own archive unchanged
    for component in (branch, loop, for_loop, native, field, plus):
        data = serialize(component)
        meta = kit_manager.lookup(kit_manager.full_name(component))
        restored = meta.component_type.restore(data, null, graphics)
        assert serialize(restored) == data, f'{meta.name} round trip mismatch'
        assert _render(env, compiler, restored) == _render(env, compiler, component), \
            f'{meta.name} restored component renders differently'
    print('round trip ok')

    # 10. End-to-end: a branch-rooted script with nested operators, loops and
    #     native code builds into the exact UDF source
    root = lookup('clk.br').component_type(null, graphics)
    cond = root.interface.edit_cond
    greater = cond.insert_component(cond._lookup_entry('greater'))
    assert greater is not null
    greater.interface.edit_left.setPlainText('x')
    greater.interface.edit_right.setPlainText('0.0')

    body = root.interface.edit_then
    assign = body.insert_component(body._lookup_entry('set'))
    assert assign is not null
    assign.interface.edit_name.setPlainText('total')
    value = assign.interface.edit_value
    times = value.insert_component(value._lookup_entry('multiply'))
    assert times is not null
    times.interface.edit_left.setPlainText('a')
    times.interface.edit_right.setPlainText('2.0')

    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')
    while_loop = body.insert_component(body._lookup_entry('loop'))
    assert while_loop is not null
    while_cond = while_loop.interface.edit_cond
    less = while_cond.insert_component(while_cond._lookup_entry('less'))
    assert less is not null
    less.interface.edit_left.setPlainText('x')
    less.interface.edit_right.setPlainText('10')
    while_loop.interface.edit_body.setPlainText('x = x + 1;')

    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')
    count_loop = body.insert_component(body._lookup_entry('for'))
    assert count_loop is not null
    count_loop.interface.edit_count.setPlainText('3')
    count_loop.interface.edit_counter.setText('idx')
    count_loop.interface.edit_body.setPlainText('Message("tick");')

    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')
    trailer = body.insert_component(body._lookup_entry('native'))
    assert trailer is not null
    trailer.interface.edit_code.setPlainText('total = total + 1;')

    project = Project('common-check', UDF)
    project.scripts.append(Script(root))
    env.project = project
    with tempfile.TemporaryDirectory() as tmp:
        artifacts, warnings = env.build(BuildConfig(UDF, output=Path(tmp)))
        assert artifacts == [Path(tmp) / 'main.c'], artifacts
        assert warnings == [], [str(warning) for warning in warnings]
        source = artifacts[0].read_text(encoding='utf-8')
    expected = ('if ((x > 0.0)) {\n'
                '    total = (a * 2.0);\n'
                '    while ((x < 10)) {\n'
                '        x = x + 1;\n'
                '    }\n'
                '    for (int idx = 0; idx < (3); ++idx) {\n'
                '        Message("tick");\n'
                '    }\n'
                '    total = total + 1;\n'
                '}')
    assert source == expected, source
    print('end-to-end build ok:')
    print(source)

    print('ALL PASSED')


if __name__ == '__main__':
    main()
