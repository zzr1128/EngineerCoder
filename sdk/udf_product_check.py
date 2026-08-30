# -*- coding: utf-8 -*-
"""
Headless check of the UDF product validity check (B1007):

- the udf.h stand-in covers every DEFINE_* macro the kit components emit,
  every traversal loop and every API snippet the kit registers (a drift
  guard keeping the stand-in in step with the kits);
- a translation unit whose rendered body is valid C compiles without a
  product warning;
- a translation unit whose body references an undeclared identifier still
  builds (the artifacts are written) but reports a B1007 warning whose
  lines are rebased onto the rendered unit itself.
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
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.project import Project
from core.script import Script
from interface.visual_code_edit import VisualCodeEdit
from kits.cbased.checker import clang_tool
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


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'cbased'))
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    from kits.fluent import udf
    from kits.fluent.api import CFluentConstant
    from kits.fluent.general import CFluentMacro
    from kits.fluent.traversal import CFluentIterationLoop

    assert clang_tool() is not null, 'the bundled clang must drive the product check'

    # 1. Drift guard: every DEFINE_* macro and traversal loop the fluent kit
    #    emits, and every macro its API quantity components render, resolves
    #    inside the stub; a new macro without a stub counterpart fails here
    macros = 0
    quantities = 0
    for meta in env.kit_manager['fluent'].components.values():
        comp_type = meta.component_type
        if issubclass(comp_type, CFluentMacro):
            assert comp_type.macro and f'#define {comp_type.macro}(' in udf._UdfStub, comp_type.macro
            macros += 1
        elif issubclass(comp_type, CFluentIterationLoop):
            assert f'#define {comp_type.head}(' in udf._UdfStub, comp_type.head
            if comp_type.tail:
                assert f'#define {comp_type.tail}(' in udf._UdfStub, comp_type.tail
        elif issubclass(comp_type, CFluentConstant) and comp_type.macro:
            assert f'#define {comp_type.macro}' in udf._UdfStub, comp_type.macro
            quantities += 1
    assert macros >= 30, macros
    assert quantities >= 40, quantities
    print(f'stub coverage ok: {macros} DEFINE_* macros, {quantities} API quantities')

    # 2. Unit-level call: an empty body stays silent, a body with an undeclared
    #    identifier reports one B1007 warning rebased onto the body's own lines
    compiler = Compiler(BuildConfig(UDF))
    udf.check_product('   ', compiler)
    assert compiler.warnings == [], compiler.warnings
    compiler = Compiler(BuildConfig(UDF))
    udf.check_product('void ec_probe(void)\n{\n    broken_identifier += 1;\n}', compiler)
    assert len(compiler.warnings) == 1, compiler.warnings
    assert compiler.warnings[0].code == 'B1007'
    assert 'broken_identifier' in compiler.warnings[0].message
    assert '\n3: ' in '\n' + compiler.warnings[0].message, compiler.warnings[0].message
    print('unit-level product check ok:', compiler.warnings[0].texts[0].splitlines()[0])

    # 3. End-to-end: a clean translation unit (a DEFINE_ADJUST walking the mesh
    #    through the loop components) builds without a product warning
    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    unit = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    body = unit.interface.edit_body
    adjust = body.insert_component(body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('clean_adjust')
    macro_body = adjust.interface.edit_body
    macro_body.setPlainText('real total = 0.0;')
    cursor = macro_body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    macro_body.setTextCursor(cursor)
    macro_body.insertPlainText('\n')
    loop = macro_body.insert_component(macro_body._lookup_entry('thread_loop_c'))
    assert loop is not null, 'insert_component(thread_loop_c) failed'
    loop_body = loop.interface.edit_body
    cell_loop = loop_body.insert_component(loop_body._lookup_entry('begin_c_loop'))
    assert cell_loop is not null, 'insert_component(begin_c_loop) failed'
    cell_loop.interface.edit_body.setPlainText('total += C_T(c, t);')
    cursor = macro_body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    macro_body.setTextCursor(cursor)
    macro_body.insertPlainText('\nMessage("total = %g\\n", total);')

    project = Project('product-check', UDF)
    project.scripts.append(Script(unit))
    env.project = project
    with tempfile.TemporaryDirectory() as tmp:
        artifacts, warnings = env.build(BuildConfig(UDF, output=Path(tmp)))
        assert warnings == [], [str(warning) for warning in warnings]
        source = artifacts[0].read_text(encoding='utf-8')
        assert 'DEFINE_ADJUST(clean_adjust, d)' in source, source
    print('clean product ok: no warnings')

    # 4. End-to-end: a broken unit still builds (the artifact is written) but
    #    its undeclared reference surfaces as a B1007 warning
    bad_unit = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    on_demand = bad_unit.interface.edit_body.insert_component(bad_unit.interface.edit_body._lookup_entry('on_demand'))
    assert on_demand is not null, 'insert_component(on_demand) failed'
    on_demand.interface.edit_name.setText('bad_probe')
    on_demand.interface.edit_body.setPlainText('missing_var = 3;')
    bad_project = Project('product-bad', UDF)
    bad_project.scripts.append(Script(bad_unit))
    env.project = bad_project
    with tempfile.TemporaryDirectory() as tmp:
        artifacts, warnings = env.build(BuildConfig(UDF, output=Path(tmp)))
        assert artifacts and artifacts[0].is_file(), 'the artifact is written despite the warning'
        assert len(warnings) == 1, [str(warning) for warning in warnings]
        assert warnings[0].code == 'B1007'
        assert 'missing_var' in warnings[0].message
        assert '\n3: ' in '\n' + warnings[0].message, warnings[0].message
    print('broken product ok:', warnings[0].texts[0].splitlines()[0])

    print('ALL PASSED')


if __name__ == '__main__':
    main()
