# -*- coding: utf-8 -*-
"""
Headless check of the scope machinery (visibility annotations):

- an assignment restricted to the local scope compiles unchanged: no
  declaration is emitted for it, so names declared natively (free C) are never
  shadowed;
- an unrestricted (``auto``) assignment contributes one ``real`` declaration,
  lifted to the top of the smallest block shared by every definition and
  reference of the name: the macro body, a loop body, a block enclosing a
  branch, or the translation unit itself when the uses span several macros;
  ``constant`` assignments keep declaring in place;
- the completion analyzer is scope-aware: locally scoped variables are
  suggested only inside the block that introduces them (and at its siblings),
  ``auto`` variables everywhere of their script, and the whole-project view
  (or edits that cannot be located) suggests everything;
- kits contribute scope-bound suggestions through ``register_scope_contributor``:
  the parameters a macro declares complete inside the macro only (``scoped``
  visibility), and a provider may attach suggestions to any scope up to the
  translation unit;
- the plain-name fields (the assignment target and the member fields) are
  derived-only visual code edits, and the completer registry survives a bare
  ``Environment()`` re-initialization (the original no-completion bug).

Note: no kit module is imported at top level on purpose; the kits are imported
through ``Environment.import_kit`` after the environment exists, mirroring the
application flow.
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
from core.script import Script
from interface.visual_code_edit import VisualCodeEdit


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


def _append_text(edit, text: string) -> void:
    """Type text at the end of an edit (behind any inserted components)."""
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit.setTextCursor(cursor)
    edit.insertPlainText(text)


def _make_adjust(env, graphics, name: string):
    adjust = env.kit_manager.lookup('fluent.adjust').component_type(null, graphics)
    adjust.interface.edit_name.setText(name)
    return adjust


def _make_assign(edit, env, name: string, value: string, *, local_only: bool = False,
                 constant: bool = False):
    assign = edit.insert_component(edit._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText(name)
    assign.interface.edit_value.setPlainText(value)
    assign.interface.check_constant.setChecked(constant)
    assign.interface.check_local.setChecked(local_only)
    maybe_unused(env)
    return assign


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    from kits.fluent.analyzer import FluentAnalyzer  # Already cached by the kit import
    from kits.fluent.analyzer import register_scope_contributor
    from kits.fluent.fluent import UDF
    from core.completer import Completion
    from core.component import ComponentMetadata

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)

    # 1. Variables restricted to the local scope compile unchanged: no
    #    declaration is emitted for them
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    body = tu.interface.edit_body
    adjust = body.insert_component(body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('iter_adjust')
    _make_assign(adjust.interface.edit_body, env, 'counter', 'counter + 1', local_only=True)
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    expected = ('#include "udf.h"\n'
                '\n'
                'DEFINE_ADJUST(iter_adjust, d)\n'
                '{\n'
                '    counter = counter + 1;\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('local compiles unchanged ok')

    # 2. Unrestricted variables declare once at the top of the macro body; a
    #    constant assignment keeps declaring in place
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    body = tu.interface.edit_body
    adjust = body.insert_component(body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('sum_adjust')
    body = adjust.interface.edit_body
    _make_assign(body, env, 'total', 'total + 1.0')
    _append_text(body, '\n')
    _make_assign(body, env, 'limit', '2.0', constant=True)
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    expected = ('#include "udf.h"\n'
                '\n'
                'DEFINE_ADJUST(sum_adjust, d)\n'
                '{\n'
                '    real total;\n'
                '    total = total + 1.0;\n'
                '    const real limit = 2.0;\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('auto hoisted to the macro body ok')

    # 3. Defined inside a branch and used after it: the declaration lands in the
    #    smallest shared block (the macro body), ahead of the branch
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    unit_body = tu.interface.edit_body
    adjust = unit_body.insert_component(unit_body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('flow_adjust')
    body = adjust.interface.edit_body
    branch = body.insert_component(body._lookup_entry('if'))
    assert branch is not null, 'insert_component(if) failed'
    branch.interface.edit_cond.setPlainText('x > 0.')
    _make_assign(branch.interface.edit_then, env, 'acc', '0')
    _append_text(body, '\nacc = acc * 2;')
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    expected = ('#include "udf.h"\n'
                '\n'
                'DEFINE_ADJUST(flow_adjust, d)\n'
                '{\n'
                '    real acc;\n'
                '    if (x > 0.) {\n'
                '        acc = 0;\n'
                '    }\n'
                '    acc = acc * 2;\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('auto hoisted to the enclosing block ok')

    # 4. Used only inside a loop body: the declaration stays at the loop-body top
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    unit_body = tu.interface.edit_body
    adjust = unit_body.insert_component(unit_body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('loop_adjust')
    body = adjust.interface.edit_body
    loop = body.insert_component(body._lookup_entry('loop'))
    assert loop is not null, 'insert_component(loop) failed'
    loop.interface.edit_cond.setPlainText('i < 3')
    _make_assign(loop.interface.edit_body, env, 's', 's + 1')
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    expected = ('#include "udf.h"\n'
                '\n'
                'DEFINE_ADJUST(loop_adjust, d)\n'
                '{\n'
                '    while (i < 3) {\n'
                '        real s;\n'
                '        s = s + 1;\n'
                '    }\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('auto hoisted to the loop body ok')

    # 5. Defined in one macro and used in another: the declaration reaches the
    #    translation unit (the smallest namespace shared by both macros)
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    body = tu.interface.edit_body
    maker = body.insert_component(body._lookup_entry('adjust'))
    assert maker is not null, 'insert_component(adjust) failed'
    maker.interface.edit_name.setText('maker')
    _make_assign(maker.interface.edit_body, env, 'shared', '0.')
    _append_text(body, '\n')
    user = body.insert_component(body._lookup_entry('adjust'))
    assert user is not null, 'insert_component(adjust) failed'
    user.interface.edit_name.setText('user')
    _make_assign(user.interface.edit_body, env, 'shared', 'shared + 1')
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    expected = ('#include "udf.h"\n'
                '\n'
                'real shared;\n'
                'DEFINE_ADJUST(maker, d)\n'
                '{\n'
                '    shared = 0.;\n'
                '}\n'
                'DEFINE_ADJUST(user, d)\n'
                '{\n'
                '    shared = shared + 1;\n'
                '}')
    assert compiler.products[UDF.id][-1] == expected, compiler.products[UDF.id][-1]
    print('auto hoisted to the translation unit ok')

    # 6. The analyzer filters by scope: locals stay inside their introducer's
    #    subtree, autos reach the whole script, the whole-project view sees all
    adjust = _make_adjust(env, graphics, 'scope_adjust')
    body = adjust.interface.edit_body
    branch = body.insert_component(body._lookup_entry('if'))
    assert branch is not null, 'insert_component(if) failed'
    branch.interface.edit_cond.setPlainText('x > 0.')
    edit_then = branch.interface.edit_then
    inner = _make_assign(edit_then, env, 'inner', '1', local_only=True)
    shared = _make_assign(edit_then, env, 'shared_v', '2')
    for_comp = edit_then.insert_component(edit_then._lookup_entry('for'))
    assert for_comp is not null, 'insert_component(for) failed'
    for_comp.interface.edit_counter.setText('k')
    for_comp.interface.edit_count.setPlainText('2')

    project = Project('scope-check', UDF)
    project.scripts.append(Script(adjust))
    analyzer = FluentAnalyzer(project)

    outside = {completion.keyword for completion in analyzer.complete(at=body)}
    assert 'shared_v' in outside and 'inner' not in outside, outside
    inside = {completion.keyword for completion in analyzer.complete(at=inner.interface.edit_value)}
    assert {'inner', 'shared_v'} <= inside, inside
    in_loop = {completion.keyword for completion in analyzer.complete(at=for_comp.interface.edit_body)}
    assert 'k' in in_loop, in_loop
    outside_loop = {completion.keyword for completion in analyzer.complete(at=body)}
    assert 'k' not in outside_loop, outside_loop
    whole = {completion.keyword for completion in analyzer.complete()}
    assert {'inner', 'shared_v', 'k'} <= whole, whole
    visibilities = {completion.keyword: completion.visibility
                    for completion in analyzer.complete()}
    assert visibilities['shared_v'] == 'auto' and visibilities['inner'] == 'local', visibilities
    print('scope-aware completion ok')

    # 7. The plain-name fields are derived-only edits, the completer registry
    #    survives a bare Environment() re-initialization, and the assignment
    #    target absorbs the project variables (the original no-completion bug)
    assert inner.interface.edit_name.derivedCompletionsEnabled(), \
        'the assignment target must restrict to derived suggestions'
    field = env.kit_manager.lookup('clk.field').component_type(null, graphics)
    assert field.interface.edit_owner.derivedCompletionsEnabled()
    assert field.interface.edit_member.derivedCompletionsEnabled()
    assert FluentAnalyzer in env.completers
    Environment()  # The editor window re-initializes the environment on startup
    assert FluentAnalyzer in env.completers, 're-initialization must not wipe the completers'
    env.project = project
    name_edit = inner.interface.edit_name
    name_edit._sync_completer_completions()
    absorbed = {entry.keyword for entry in name_edit.completions}
    # The target absorbs project variables; of the components only the member
    # access may embed (the other kit keywords stay excluded)
    assert 'shared_v' in absorbed, absorbed
    assert all(not entry.component_name or entry.component_name == 'clk.field'
               for entry in name_edit.completions), name_edit.completions
    print('plain-name fields complete ok')

    # 8. Kits contribute scope-bound suggestions: the parameters a macro
    #    declares complete inside the macro only ('scoped'), and a registered
    #    provider may attach suggestions to any scope up to the translation unit
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    unit_body = tu.interface.edit_body
    adjust = unit_body.insert_component(unit_body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('param_adjust')
    macro_body = adjust.interface.edit_body
    project = Project('scope-contrib-check', UDF)
    project.scripts.append(Script(tu))
    analyzer = FluentAnalyzer(project)

    inside = {completion.keyword for completion in analyzer.complete(at=macro_body)}
    assert 'd' in inside, inside
    outside = {completion.keyword for completion in analyzer.complete(at=unit_body)}
    assert 'd' not in outside, 'macro parameters never leave their macro'
    visibilities = {completion.keyword: completion.visibility
                    for completion in analyzer.complete()}
    assert visibilities['d'] == 'scoped', visibilities

    def _unit_globals(component) -> IList[Completion]:
        if component is not tu:  # Anchored at the translation unit
            return []
        return [Completion(keyword='g_case', kind=ComponentMetadata.Kind.Variable,
                           visibility='auto', description='unit global')]

    register_scope_contributor(_unit_globals)
    assert 'g_case' in {completion.keyword for completion in analyzer.complete(at=macro_body)}
    assert 'g_case' in {completion.keyword for completion in analyzer.complete(at=unit_body)}, \
        'a translation-unit contribution reaches every edit of the script'
    print('scope contributors ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
