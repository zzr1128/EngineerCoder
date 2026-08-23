# -*- coding: utf-8 -*-
"""
Headless check of ``kits.fluent.general`` (the general DEFINE_* macro components):

- the seven macro components register at the Domain level and support UDF natively;
- compilation emits ``MACRO(name, args...) { body }``, nested components included;
- the serialization round-trip through ``restore`` preserves the contents;
- kits contribute completion keywords through the KitManager registry (which
  survives the Environment construction), and the level filter keeps the macros
  out of statement contexts while Domain contexts accept them.
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
from interface.visual_code_edit import VisualCodeEdit
# Imported before Environment(): the kit modules register their completion
# keywords on the kit manager singleton, which Environment() must not wipe
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


# Everything else of IComponentGraphics is irrelevant for this check
for _name in dir(IComponentGraphics):
    if not _name.startswith('_') and callable(getattr(IComponentGraphics, _name)) \
            and _name not in vars(_GraphicsStub):
        setattr(_GraphicsStub, _name, staticmethod(_noop))


# (component name, emitted macro, parameter count)
MACROS = (('adjust', 'DEFINE_ADJUST', 1),
          ('init', 'DEFINE_INIT', 1),
          ('execute_at_end', 'DEFINE_EXECUTE_AT_END', 0),
          ('on_demand', 'DEFINE_ON_DEMAND', 0),
          ('rw_file', 'DEFINE_RW_FILE', 1),
          ('deltat', 'DEFINE_DELTAT', 1),
          ('execute_from_gui', 'DEFINE_EXECUTE_FROM_GUI', 1))

KEYWORDS = {'adjust': 'fluent.adjust', 'init': 'fluent.init',
            'at_end': 'fluent.execute_at_end', 'on_demand': 'fluent.on_demand',
            'rw_file': 'fluent.rw_file', 'deltat': 'fluent.deltat',
            'from_gui': 'fluent.execute_from_gui'}


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    # 1. Registration: Domain-level components supporting UDF natively
    for name, macro, nargs in MACROS:
        meta = env.kit_manager.lookup(f'fluent.{name}')
        assert meta.level == ComponentMetadata.Level.Domain, (name, meta.level)
        assert UDF in meta.languages, f'fluent.{name} should support UDF natively'
        assert meta.description, f'fluent.{name} has no description'
        comp_type = meta.component_type
        assert len(comp_type.args_spec) == nargs, (name, comp_type.args_spec)
        assert comp_type.macro == macro, (name, comp_type.macro)
    print('registration ok')

    # 2. The completion keywords survived the Environment construction
    for keyword, component_name in KEYWORDS.items():
        assert env.kit_manager.completions.get(keyword) == component_name, \
            (keyword, env.kit_manager.completions.get(keyword))
    print('completion registry ok')

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    compiler = Compiler(BuildConfig(UDF))

    # 3. A parameterless macro with an empty body yields an empty block
    on_demand = env.kit_manager.lookup('fluent.on_demand').component_type(null, graphics)
    on_demand.interface.edit_name.setText('my_calc')
    on_demand.build(compiler)
    assert compiler.products[UDF.id][-1] == 'DEFINE_ON_DEMAND(my_calc)\n{\n}', \
        compiler.products[UDF.id][-1]
    print('parameterless macro compile ok')

    # 4. DEFINE_ADJUST whose body embeds a CLK assignment component
    adjust = env.kit_manager.lookup('fluent.adjust').component_type(null, graphics)
    assert adjust.interface.arg_edits[0].text() == 'd'  # Pre-filled identifier
    adjust.interface.edit_name.setText('my_adjust')
    body = adjust.interface.edit_body
    body.setPlainText('int kount = 0;')
    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')
    assign = body.insert_component(body._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setText('kount')
    assign.interface.edit_value.setPlainText('kount + 1')
    assign.interface.check_local.setChecked(True)  # Declared by the free text above
    adjust.build(compiler)
    adjust_expected = ('DEFINE_ADJUST(my_adjust, d)\n'
                       '{\n'
                       '    int kount = 0;\n'
                       '    kount = kount + 1;\n'
                       '}')
    assert compiler.products[UDF.id][-1] == adjust_expected, compiler.products[UDF.id][-1]
    print('macro with nested component compile ok:')
    print(adjust_expected)

    # 5. The remaining macros render their exact headers and bodies
    cases = (('init', 'my_init', 'Message("initialized");',
              'DEFINE_INIT(my_init, d)\n{\n    Message("initialized");\n}'),
             ('execute_at_end', 'finish', 'Message("done");',
              'DEFINE_EXECUTE_AT_END(finish)\n{\n    Message("done");\n}'),
             ('rw_file', 'writer', 'fprintf(fp, "%d", kount);',
              'DEFINE_RW_FILE(writer, fp)\n{\n    fprintf(fp, "%d", kount);\n}'),
             ('execute_from_gui', 'panel_cb', 'Message("gui %d", msg);',
              'DEFINE_EXECUTE_FROM_GUI(panel_cb, msg)\n{\n    Message("gui %d", msg);\n}'))
    for name, func_name, body_text, expected in cases:
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        comp.interface.edit_name.setText(func_name)
        comp.interface.edit_body.setPlainText(body_text)
        comp.build(compiler)
        assert compiler.products[UDF.id][-1] == expected, (name, compiler.products[UDF.id][-1])
    print('remaining macro compiles ok')

    # 5b. DEFINE_DELTAT returns through the body statements: "set deltat"
    #     stores the value the compilation names, "end DEFINE_DELTAT" returns it
    deltat = env.kit_manager.lookup('fluent.deltat').component_type(null, graphics)
    assert not hasattr(deltat.interface, 'edit_result'), 'returning macros must carry no result field'
    deltat.interface.edit_name.setText('my_deltat')
    deltat_body = deltat.interface.edit_body
    set_comp = deltat_body.insert_component(VisualCodeEdit.CompletionEntry('set_deltat', 'fluent.set_deltat'))
    assert set_comp is not null, 'insert_component(set_deltat) failed'
    set_comp.interface.edit_value.setPlainText('0.1')
    deltat_body.insertPlainText('\n')
    end_comp = deltat_body.insert_component(VisualCodeEdit.CompletionEntry('end_deltat', 'fluent.end_deltat'))
    assert end_comp is not null, 'insert_component(end_deltat) failed'
    deltat.build(compiler)
    deltat_expected = ('DEFINE_DELTAT(my_deltat, d)\n'
                       '{\n'
                       '    real deltat = 0.;\n'
                       '    deltat = 0.1;\n'
                       '    return deltat;\n'
                       '}')
    assert compiler.products[UDF.id][-1] == deltat_expected, compiler.products[UDF.id][-1]
    # Void macros carry no result field
    assert not hasattr(on_demand.interface, 'edit_result'), 'void macros must carry no result field'
    # The statements refuse to compile outside a DEFINE_DELTAT body
    lonely = Compiler(BuildConfig(UDF))
    try:
        set_comp.build(lonely)
        raise AssertionError('set_deltat must reject a contextless position')
    except Compiler.CompileError:
        pass
    # Legacy archives carrying a result field migrate it into the body as
    # "set deltat" followed by "end DEFINE_DELTAT"
    migrated = env.kit_manager.lookup('fluent.deltat').component_type.restore(
        {'name': 'legacy_dt', 'args': ['d'],
         'body': {'text': '', 'components': []},
         'result': {'text': '0.05', 'components': []}}, null, graphics)
    migrated.build(compiler)
    migrated_expected = ('DEFINE_DELTAT(legacy_dt, d)\n'
                         '{\n'
                         '    real deltat = 0.;\n'
                         '    deltat = 0.05;\n'
                         '    return deltat;\n'
                         '}')
    assert compiler.products[UDF.id][-1] == migrated_expected, compiler.products[UDF.id][-1]
    print('deltat statements compile ok')

    # 6. Serialization round-trip through restore (nested components included)
    data = serialize(adjust)
    restored = env.kit_manager.lookup('fluent.adjust').component_type.restore(data, null, graphics)
    assert serialize(restored) == data, 'round-trip serialization mismatch'
    restored.build(compiler)
    assert compiler.products[UDF.id][-1] == adjust_expected, compiler.products[UDF.id][-1]
    print('serialization round-trip ok')

    # 7. A shortage of arguments is rejected on restore; a surplus shrinks to
    #    the visible ones (legacy archives recorded parameters since dropped)
    rw_type = env.kit_manager.lookup('fluent.rw_file').component_type
    rw_data = serialize(rw_type(null, graphics))
    rw_data['args'] = ['fp', 'extra']
    rw_extra = rw_type.restore(rw_data, null, graphics)
    assert rw_extra.interface.arg_edits[0].text() == 'fp', 'leading identifiers must survive truncation'
    rw_data['args'] = []
    try:
        rw_type.restore(rw_data, null, graphics)
        raise AssertionError('mismatching argument count was accepted')
    except SerializationError as e:
        print(f'argument count rejection ok: {e}')

    # 8. Level filter: statement contexts reject the macros; Domain accepts them
    stmt_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    stmt_edit.filter(ComponentMetadata.Level.Statement)
    adjust_entry = next(entry for entry in stmt_edit.completions if entry.keyword == 'adjust')
    assert not stmt_edit._entry_participates(adjust_entry), \
        'Domain-level macro must not complete in statement contexts'
    domain_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    domain_edit.filter(ComponentMetadata.Level.Domain)
    adjust_entry = next(entry for entry in domain_edit.completions if entry.keyword == 'adjust')
    assert domain_edit._entry_participates(adjust_entry), \
        'Domain-level macro must complete in Domain contexts'
    br_entry = next(entry for entry in domain_edit.completions if entry.component_name == 'clk.br')
    assert domain_edit._entry_participates(br_entry), \
        'statement components must still complete in Domain contexts'
    print('level filter ok')

    # 9. Late absorption: an entry dropped from an edit comes back from the registry
    domain_edit.completions[:] = [entry for entry in domain_edit.completions
                                  if entry.component_name != 'fluent.deltat']
    domain_edit._sync_kit_completions()
    assert any(entry.component_name == 'fluent.deltat' for entry in domain_edit.completions), \
        'kit completions should be absorbed after construction'
    print('late completion absorption ok')

    # 10. Focus and navigation order
    assert adjust.autoFocusWidget() is adjust.interface.edit_name
    assert adjust.editableWidgets() == [adjust.interface.edit_name,
                                        adjust.interface.arg_edits[0],
                                        adjust.interface.edit_body]
    assert on_demand.editableWidgets() == [on_demand.interface.edit_name,
                                           on_demand.interface.edit_body]
    print('focus and navigation ok')

    # 11. Every macro carries the brief caption (the localized description
    #     minus the macro-name prefix) on its own row
    for name in ('adjust', 'on_demand'):
        meta = env.kit_manager.lookup(f'fluent.{name}')
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        brief = meta.description
        for separator in ('：', ': '):
            if brief.startswith(meta.component_type.macro + separator):
                brief = brief[len(meta.component_type.macro) + len(separator):]
                break
        assert brief and comp.interface.label_brief.text() == brief, \
            (name, comp.interface.label_brief.text())
    print('brief caption ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
