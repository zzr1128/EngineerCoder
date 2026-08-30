# -*- coding: utf-8 -*-
"""
Headless check of the static checking and the Fluent interface library:

- the C-based checker validates identifiers against the C standard the project
  selects and checks free C source (clang or the intrinsic fallback);
- the compilation rejects illegal component contents with B1006 listing every
  problem (``udf.validate_unit``);
- the mesh traversal loop components render nested UDF source and survive a
  serialization round trip;
- the Fluent API helper macros register as components exclusively: the edits
  absorb their keywords and insert the components on confirmation; the cell
  field accessors render through the compilation context their enclosing
  components open (and refuse to render without one);
- the type annotation of an assignment drives the compiled C type;
- the immediate checking marks invalid identifiers red while they are written.
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
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.project import Project
from interface.visual_code_edit import VisualCodeEdit
from kits.cbased.checker import CbasedChecker
from kits.common.validation import InvalidProperty, attach_identifier_check
from kits.fluent.fluent import UDF
from kits.fluent.udf import UdfAssign


class _CanvasStub(QWidget):
    """Stands in for the canvas: the nearest ancestor providing ``add_interface``."""

    def __init__(self):
        super().__init__()
        self.interfaces: IList[Any] = []

    def add_interface(self, component: Any, right_occupation: float = 0.) -> void:
        maybe_unused(right_occupation)
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
        maybe_unused(rect)
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
        maybe_unused(label, modify)
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


def main() -> void:
    app = QApplication(sys.argv)
    maybe_unused(app)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'cbased'))
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    project = Project('StaticCheck', UDF)
    env.project = project
    compiler = Compiler(BuildConfig(UDF))

    # 1. Identifier rules follow the C standard the project selects
    checker = CbasedChecker(project)
    assert checker.standard == 'c99', checker.standard
    assert checker.check_identifier('velocity') is null
    assert checker.check_identifier('9lives').severity == 'error'
    assert checker.check_identifier('my-var').severity == 'error'
    assert checker.check_identifier('for').severity == 'error'
    assert checker.check_identifier('inline').severity == 'error'  # C99 keyword
    assert checker.check_identifier('__reserved').severity == 'warning'
    project.c_standard = 'c89'
    assert checker.check_identifier('inline') is null  # Not a keyword before C99
    project.c_standard = 'c23'
    assert checker.check_identifier('bool').severity == 'error'  # A keyword since C23
    project.c_standard = 'c99'
    print('identifier checking ok')

    # 2. Free C source checking: clang when available, the intrinsic fallback always
    assert CbasedChecker._intrinsic_check('if (x) { y(); }') == []
    assert any(d.severity == 'error' for d in CbasedChecker._intrinsic_check('if (x { '))
    assert any(d.severity == 'error' for d in CbasedChecker._intrinsic_check('char *s = "abc;'))
    assert any(d.severity == 'error' for d in CbasedChecker._intrinsic_check('/* never closed'))
    assert checker.check_source('int f(void) { return 0; }') == [] \
        or all(d.severity != 'error' for d in checker.check_source('int f(void) { return 0; }'))
    assert any(d.severity == 'error' for d in checker.check_source('int f(void) { return 0; '))
    print('source checking ok')

    # 3. The compilation rejects illegal component contents (B1006, all problems listed)
    from kits.fluent import udf
    bad_unit = {
        'text': '\uFFFC\uFFFC',
        'components': [
            {'name': 'fluent.adjust',
             'data': {'name': '9bad', 'args': [''],
                      'body': {'text': '', 'components': []}}},
            {'name': 'clk.assign',
             'data': {'name': 'for', 'value': {'text': '1', 'components': []},
                      'constant': False, 'local_only': True}},
        ]
    }
    try:
        udf.validate_unit(bad_unit, compiler)
        raise AssertionError('validate_unit must reject illegal contents')
    except Compiler.CompileError as e:
        assert e.code == 'B1006', e
        message = str(e)
        assert '9bad' in message, message  # The illegal macro name
        # Every problem is listed: one line per problem plus the summary header
        assert message.count('\n') >= 3, message
    good_unit = {
        'text': '\uFFFC',
        'components': [
            {'name': 'fluent.adjust',
             'data': {'name': 'my_adjust', 'args': ['d'],
                      'body': {'text': '', 'components': []}}},
        ]
    }
    udf.validate_unit(good_unit, compiler)  # Must not raise
    print('compile-time validation ok')

    # 4. Traversal loops render nested UDF source
    nested_unit = {
        'text': '\uFFFC',
        'components': [{
            'name': 'fluent.thread_cell_loop',
            'data': {'args': ['t', 'd'], 'body': {
                'text': '\uFFFC',
                'components': [{
                    'name': 'fluent.cell_loop',
                    'data': {'args': ['c', 't'], 'body': {
                        'text': 'C_T(c, t);', 'components': []}}
                }]
            }}
        }]
    }
    source = udf.render_unit(nested_unit, compiler)
    expected = ('thread_loop_c(t, d)\n'
                '{\n'
                '    begin_c_loop(c, t)\n'
                '    {\n'
                '        C_T(c, t);\n'
                '    }\n'
                '    end_c_loop(c, t)\n'
                '}')
    assert source == expected, source
    face_unit = {
        'text': '\uFFFC',
        'components': [{
            'name': 'fluent.face_of_cell_loop',
            'data': {'args': ['c', 't', 'n'], 'body': {
                'text': 'F_T(C_FACE(c, t, n), C_FACE_THREAD(c, t, n));', 'components': []}}
        }]
    }
    source = udf.render_unit(face_unit, compiler)
    expected = ('c_face_loop(c, t, n)\n'
                '{\n'
                '    F_T(C_FACE(c, t, n), C_FACE_THREAD(c, t, n));\n'
                '}')
    assert source == expected, source
    # The face loop wraps the body in begin_f_loop ... end_f_loop
    face_loop_unit = {
        'text': '\uFFFC',
        'components': [{
            'name': 'fluent.face_loop',
            'data': {'args': ['f', 't'], 'body': {
                'text': 'F_T(f, t);', 'components': []}}
        }]
    }
    source = udf.render_unit(face_loop_unit, compiler)
    expected = ('begin_f_loop(f, t)\n'
                '{\n'
                '    F_T(f, t);\n'
                '}\n'
                'end_f_loop(f, t)')
    assert source == expected, source
    print('traversal rendering ok:')
    print(udf.render_unit(nested_unit, compiler))

    # 5. Traversal components: construction, serialization round trip, completion
    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    meta = env.kit_manager.lookup('fluent.thread_cell_loop')
    loop = meta.component_type(null, graphics)
    assert loop.interface.arg_edits[0].text() == 't'  # Conventional identifiers pre-filled
    assert loop.interface.arg_edits[1].text() == 'd'
    loop.interface.edit_body.setPlainText('Message("cell thread");')
    loop.build(compiler)
    assert compiler.products[UDF.id][-1] == (
        'thread_loop_c(t, d)\n{\n    Message("cell thread");\n}'), compiler.products[UDF.id][-1]
    restored = meta.component_type.restore(serialize(loop), null, graphics)
    assert serialize(restored) == serialize(loop), 'traversal round trip'
    assert env.kit_manager.completions['begin_c_loop'] == 'fluent.cell_loop'
    assert env.kit_manager.completions['begin_f_loop'] == 'fluent.face_loop'
    assert env.kit_manager.completions['thread_loop_f'] == 'fluent.thread_face_loop'
    print('traversal components ok')

    # 6. The API helper macros register as components exclusively (no snippet
    #    survives); the edits absorb their keywords and insert the components
    assert not env.snippets, 'the kits must contribute components exclusively'
    assert env.kit_manager.completions['NV_VV'] == 'fluent.nv_vv'
    assert 'cell_temperature' not in env.kit_manager.completions, \
        'context-bound accessors must gate their completion'
    edit = graphics.create_visual_code_edit(QRectF(0, 0, 300, 30))
    call_entry = next((entry for entry in edit.completions
                       if entry.keyword == 'NV_VV' and entry.component_name == 'fluent.nv_vv'), null)
    assert call_entry is not null, 'the component keyword must be absorbed into the edit'
    edit.setFocus()
    edit._confirm_completion(call_entry)
    assert edit.toPlainText() == '\uFFFC', edit.toPlainText()
    # The call renders its archived fields between the literals its
    # specification carries
    nv_vv_unit = {
        'text': '\uFFFC',
        'components': [{
            'name': 'fluent.nv_vv',
            'data': {'fields': [{'text': 'a', 'components': []},
                                 {'text': 'b', 'components': []},
                                 {'text': 'c', 'components': []}]}}
        ]
    }
    source = udf.render_unit(nv_vv_unit, compiler)
    assert source == 'NV_VV(a, =, b, +, c)', source
    # An accessor nested in a cell context renders with the identifiers the
    # context provides; outside any context the compilation rejects it (B1006)
    ctx_unit = {
        'text': '\uFFFC',
        'components': [{
            'name': 'fluent.cell_loop',
            'data': {'args': ['c', 't'], 'body': {
                'text': 'x = \uFFFC;',
                'components': [{'name': 'fluent.c_t', 'data': {}}]}}
        }]
    }
    source = udf.render_unit(ctx_unit, compiler)
    expected = ('begin_c_loop(c, t)\n'
                '{\n'
                '    x = C_T(c, t);\n'
                '}\n'
                'end_c_loop(c, t)')
    assert source == expected, source
    try:
        udf.render_component('fluent.c_t', {}, compiler)
        raise AssertionError('a contextless accessor must be rejected')
    except Compiler.CompileError as e:
        assert e.code == 'B1006', e
    # Derived-only name fields stay restricted: no component entry leaks in
    name_edit = graphics.create_visual_code_edit(QRectF(0, 0, 120, 24))
    name_edit.setDerivedCompletionsEnabled(True)
    assert all(not entry.component_name for entry in name_edit.completions), \
        'derived-only edits absorb no component entries'
    print('api components ok')

    # 7. The type annotation drives the compiled C type
    source = UdfAssign.render({'name': 'count', 'value': {'text': '5', 'components': []},
                               'constant': True, 'type': 'int'}, compiler)
    assert source == 'const int count = 5;', source
    source = UdfAssign.render({'name': 'ratio', 'value': {'text': '0.5', 'components': []},
                               'constant': True, 'type': ''}, compiler)
    assert source == 'const real ratio = 0.5;', source
    # Hoisted declarations of auto variables use the annotated type as well
    typed_unit = {
        'text': '\uFFFC\nsteps = steps + 1;',
        'components': [{
            'name': 'clk.assign',
            'data': {'name': 'steps', 'value': {'text': '0', 'components': []},
                     'constant': False, 'local_only': False, 'type': 'int'}
        }]
    }
    udf.analyze_scope(typed_unit, compiler)
    source = udf.render_unit(typed_unit, compiler)
    assert source.startswith('int steps;\n'), source
    print('type-aware compilation ok')

    # 8. Immediate checking marks invalid identifiers red while they are written
    field = graphics.create_lineedit(QRectF(0, 0, 120, 24))
    attach_identifier_check(field)
    field.setText('velocity')
    assert not field.property(InvalidProperty), 'a valid identifier stays unmarked'
    field.setText('9lives')
    assert field.property(InvalidProperty) is True, 'an invalid identifier marks red'
    assert field.toolTip(), 'the diagnostic explains the marking'
    field.setText('')
    assert not field.property(InvalidProperty), 'emptying lifts the marking'
    field.setText('_Reserved')
    assert not field.property(InvalidProperty), 'a warning alone marks nothing'
    print('immediate checking ok')

    print('STATIC CHECK SUITE PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
