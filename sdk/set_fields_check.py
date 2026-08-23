# -*- coding: utf-8 -*-
"""
Headless check of the assignment-target fields and their integration:

- completing inside an introducer's own name field never suggests the name
  being written (the self-completion bug), while the value field still sees it;
- variables introduced by siblings sharing the same block suggest each other
  (two assignments of the same name see one another);
- every derived variable carries a description (local/global/loop variable);
- assignments are ``auto`` unless restricted to the local scope: unrestricted
  targets lift their declaration while compiling, restricted ones do not;
- the assignment target embeds member components: only the member entry takes
  part under the derived-only restriction, the archive round-trips, and the
  UDF rendering emits ``owner.member``;
- the type field is a selection (real/integer/character) auto-filled when the
  target names a variable the project defines (a native declaration wins, then
  a constant assignment, then the annotation another assignment carries);
  manual choices suppress auto-filling until the field becomes empty again;
- ``lookup_type`` and ``type_options`` are part of the completer contract
  (the default knows no types and offers no options, kits override both; the
  assignment falls back to its built-in C scalar types without an offer);
- identifiers declared at the translation-unit root occupy the counter names
  of count loops, so auto-named loops skip them.

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

from PySide6.QtCore import QEvent, QRectF
from PySide6.QtGui import QColor, QFocusEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.build import BuildConfig, Compiler
from core.completer import Completer
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


def _make_assign(edit, name: string, value: string, *, local_only: bool = False,
                 constant: bool = False):
    assign = edit.insert_component(edit._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText(name)
    assign.interface.edit_value.setPlainText(value)
    assign.interface.check_constant.setChecked(constant)
    assign.interface.check_local.setChecked(local_only)
    return assign


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    from kits.fluent.analyzer import FluentAnalyzer, lt_local_var, lt_auto_var, lt_counter_var
    from kits.fluent.fluent import UDF
    from kits.fluent.udf import UdfAssign, OccupiedKey

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)

    # A translation unit with an external declaration, assignments of every
    # annotation and an explicitly named count loop
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    body = tu.interface.edit_body
    _append_text(body, 'int counter = 0;\n')
    adjust = body.insert_component(body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('field_adjust')
    inner_body = adjust.interface.edit_body
    counter_assign = _make_assign(inner_body, 'counter', 'counter + 1', local_only=True)
    _append_text(inner_body, '\n')
    _make_assign(inner_body, 'total', '1')  # Unrestricted: lifted to a declaration
    _append_text(inner_body, '\n')
    _make_assign(inner_body, 'limit', '2', constant=True)
    _append_text(inner_body, '\n')
    for_comp = inner_body.insert_component(inner_body._lookup_entry('for'))
    assert for_comp is not null, 'insert_component(for) failed'
    for_comp.interface.edit_counter.setText('k')
    for_comp.interface.edit_count.setPlainText('2')

    project = Project('set-fields-check', UDF)
    project.scripts.append(Script(tu))
    env.project = project
    analyzer = FluentAnalyzer(project)

    # 1. The name being written never completes itself
    at_name = {completion.keyword for completion
               in analyzer.complete(at=counter_assign.interface.edit_name)}
    assert 'counter' not in at_name, at_name
    at_value = {completion.keyword for completion
                in analyzer.complete(at=counter_assign.interface.edit_value)}
    assert 'counter' in at_value, at_value
    whole = {completion.keyword for completion in analyzer.complete()}
    assert 'counter' in whole, whole  # No requesting edit: nothing is excluded
    print('self name excluded ok')

    # 2. Siblings sharing a block see each other's variables, and a second
    #    assignment of the same name sees the first one (both ways: from the
    #    name field and from the value field)
    second = _make_assign(inner_body, 'counter', 'counter + 2', local_only=True)
    at_second_name = {completion.keyword for completion
                      in analyzer.complete(at=second.interface.edit_name)}
    assert 'counter' in at_second_name, 'the sibling assignment of the same name must suggest'
    assert 'total' in at_second_name, at_second_name
    at_second_value = {completion.keyword for completion
                       in analyzer.complete(at=second.interface.edit_value)}
    assert 'counter' in at_second_value, at_second_value
    # The first assignment still sees its sibling as well
    at_first_name = {completion.keyword for completion
                     in analyzer.complete(at=counter_assign.interface.edit_name)}
    assert 'total' in at_first_name, at_first_name
    print('same-layer siblings ok')

    # 3. Every derived variable carries a description of its nature
    descriptions = {completion.keyword: completion.description
                    for completion in analyzer.complete()}
    assert descriptions['counter'] == lt_local_var, descriptions
    assert descriptions['total'] == lt_auto_var, descriptions
    assert descriptions['k'] == lt_counter_var, descriptions
    print('variable descriptions ok')

    # 4. Assignments are lifted unless restricted to the local scope; legacy
    #    archives annotated ``visibility: auto`` keep lifting
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    source = compiler.products[UDF.id][-1]
    assert 'real total;' in source, 'unrestricted assignments lift their declaration'
    assert 'real counter;' not in source, 'restricted assignments stay local'
    restricted = _make_assign(inner_body, 'shared_v', '3')
    assert not restricted.interface.check_local.isChecked()
    data = serialize(restricted)
    assert data['local_only'] is False, data
    restricted.interface.check_local.setChecked(True)
    assert serialize(restricted)['local_only'] is True
    legacy = {'name': 'legacy_v', 'value': {'text': '1', 'components': []},
              'constant': False, 'visibility': 'auto'}
    legacy_assign = env.kit_manager.lookup('clk.assign').component_type.restore(
        legacy, null, graphics)
    legacy_assign.interface.edit_name.setPlainText('legacy_v')
    assert not legacy_assign.interface.check_local.isChecked(), 'legacy auto inverts'
    print('local-only annotation ok')

    # 5. The assignment target embeds member components and renders them
    assign_member = env.kit_manager.lookup('clk.assign').component_type(null, graphics)
    name_edit = assign_member.interface.edit_name
    assert name_edit.derivedCompletionsEnabled()
    component_entries = {entry.component_name for entry in name_edit.completions
                         if entry.component_name}
    assert component_entries == {'clk.field'}, component_entries
    member = name_edit.insert_component(name_edit._lookup_entry('member'))
    assert member is not null, 'insert_component(member) into the target failed'
    member.interface.edit_owner.setPlainText('cell')
    member.interface.edit_member.setPlainText('volume')
    assign_member.interface.edit_value.setPlainText('1')
    data = serialize(assign_member)
    assert data['name']['text'] == '\uFFFC' and data['name']['components'], data
    restored = env.kit_manager.lookup('clk.assign').component_type.restore(data, null, graphics)
    assert serialize(restored) == data
    compiler = Compiler(BuildConfig(UDF))
    assert UdfAssign.render(data, compiler) == 'cell.volume = 1;'
    # A member-embedded target introduces no plain variable
    assert FluentAnalyzer._introduced_name(assign_member, 'edit_name') == ''
    print('member target ok')

    # 6. The type field is a selection auto-filled from the project's definitions
    assert analyzer.lookup_type('counter') == 'int'  # External declaration wins
    assert analyzer.lookup_type('limit') == 'const real'  # Constant assignment
    assert analyzer.lookup_type('nowhere') == ''

    typed = env.kit_manager.lookup('clk.assign').component_type(null, graphics)
    type_combo = typed.interface.edit_type
    assert [type_combo.itemData(index) for index in range(type_combo.count())] \
        == ['', 'real', 'int', 'char'], 'the type field offers the selection'
    typed.interface.edit_name.setPlainText('counter')
    app.sendEvent(typed.interface.edit_name, QFocusEvent(QEvent.Type.FocusOut))
    assert type_combo.currentData() == 'int', type_combo.currentText()
    # Committing again refills (the fill was programmatic, not manual)
    typed.interface.edit_name.setPlainText('limit')
    app.sendEvent(typed.interface.edit_name, QFocusEvent(QEvent.Type.FocusOut))
    assert type_combo.currentData() == 'real', 'const real maps onto the real option'
    # Manual choices suppress auto-filling until the field becomes empty again
    type_combo.setCurrentIndex(type_combo.findData('char'))
    assert typed._type_manual, 'choosing an option counts as manual'
    typed.interface.edit_name.setPlainText('counter')
    app.sendEvent(typed.interface.edit_name, QFocusEvent(QEvent.Type.FocusOut))
    assert type_combo.currentData() == 'char', 'manual choices must win'
    type_combo.setCurrentIndex(0)
    assert not typed._type_manual, 'the empty option re-enables auto-fill'
    app.sendEvent(typed.interface.edit_name, QFocusEvent(QEvent.Type.FocusOut))
    assert type_combo.currentData() == 'int', 'clearing re-enables auto-fill'
    # A second assignment inherits the annotation the first one carries
    typed.interface.edit_name.setPlainText('shared_v')
    restricted.interface.edit_type.setCurrentIndex(restricted.interface.edit_type.findData('real'))
    app.sendEvent(typed.interface.edit_name, QFocusEvent(QEvent.Type.FocusOut))
    assert analyzer.lookup_type('shared_v') == 'real'
    assert type_combo.currentData() == 'real', 'the annotation of another assignment inherits'
    # The selection round-trips; legacy free-text types map onto the options
    data = serialize(typed)
    assert data['type'] == 'real', data
    restored = env.kit_manager.lookup('clk.assign').component_type.restore(data, null, graphics)
    assert restored.interface.edit_type.currentData() == 'real'
    assert not restored._type_manual, 'restored types must not count as manual'
    data['type'] = 'const double'
    restored = env.kit_manager.lookup('clk.assign').component_type.restore(data, null, graphics)
    assert restored.interface.edit_type.currentData() == 'real', 'legacy texts normalize'
    print('type selection ok')

    # 7. ``lookup_type`` and ``type_options`` belong to the completer contract;
    #    the default knows no types and offers no options, kits override both
    assert FluentAnalyzer.lookup_type is not Completer.lookup_type, \
        'the kit must override the completer contract'
    assert FluentAnalyzer(project).lookup_type('counter') == 'int'
    assert FluentAnalyzer.type_options is not Completer.type_options, \
        'the kit must override the type options'
    options = FluentAnalyzer(project).type_options()
    assert [key for _, key in options] == ['real', 'int', 'char'], options
    # The assignment offers the options the kit defines (labels included)
    assert type_combo.itemText(1) == options[0][0], 'the kit customizes the selection'

    class _Plain(Completer):
        def complete(self, at: Any = null) -> IList[Any]:
            maybe_unused(at)
            return []

    assert _Plain(project).lookup_type('counter') == '', 'the default knows no types'
    assert _Plain(project).type_options() == [], 'the default offers no options'
    # Without a completer offering options the assignment keeps its built-ins
    env.project = null
    plain = env.kit_manager.lookup('clk.assign').component_type(null, graphics)
    assert [plain.interface.edit_type.itemData(index)
            for index in range(plain.interface.edit_type.count())] \
        == ['', 'real', 'int', 'char'], 'the fallback keeps the C scalar types'
    env.project = project
    print('completer contract ok')

    # 8. External declarations occupy the counter names of count loops
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    body = tu.interface.edit_body
    _append_text(body, 'int i = 0;\n')
    adjust = body.insert_component(body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('loop_adjust')
    loop_body = adjust.interface.edit_body
    outer = loop_body.insert_component(loop_body._lookup_entry('for'))
    assert outer is not null, 'insert_component(for) failed'
    outer.interface.edit_count.setPlainText('3')
    inner = outer.interface.edit_body.insert_component(outer.interface.edit_body._lookup_entry('for'))
    assert inner is not null, 'insert_component(for) failed'
    inner.interface.edit_count.setPlainText('2')
    compiler = Compiler(BuildConfig(UDF))
    tu.build(compiler)
    source = compiler.products[UDF.id][-1]
    assert 'for (int j = 0' in source, source  # 'i' is externally declared
    assert 'for (int k = 0' in source, source  # The nested loop takes the next name
    assert 'for (int i = 0' not in source, source
    assert 'i' in compiler.products[OccupiedKey], 'external declarations stay occupied'
    print('external occupation ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
