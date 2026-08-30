# -*- coding: utf-8 -*-
"""
Headless check of the fluent translation unit (``kits.fluent.general.CTranslationUnit``):

- the translation unit registers at the Domain level and supports UDF natively;
- compilation emits one fragment: ``#include "udf.h"`` followed by the unit
  contents (free C and DEFINE_* macros) in document order;
- the serialization round-trip through ``restore`` preserves the contents;
- the unit's body edit keeps the client-rectangle height as its basic height
  (fills the area with only its margin) while growing contents still extend it,
  without the canvas extent running away;
- the whole Script/Project pipeline writes the unit into a ``.c`` artifact.
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


EXPECTED_SOURCE = ('#include "udf.h"\n'
                   '\n'
                   'int counter = 0;\n'
                   'DEFINE_ADJUST(iter_adjust, d)\n'
                   '{\n'
                   '    counter = counter + 1;\n'
                   '}\n'
                   'DEFINE_ON_DEMAND(finish)\n'
                   '{\n'
                   '    Message("done");\n'
                   '}')


def _populate(tu) -> void:
    """Fill the unit: a global declaration, a DEFINE_ADJUST (with a nested CLK
    assignment in its body) and a DEFINE_ON_DEMAND, in this order."""
    body = tu.interface.edit_body
    body.setPlainText('int counter = 0;')
    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')

    adjust = body.insert_component(body._lookup_entry('adjust'))
    assert adjust is not null, 'insert_component(adjust) failed'
    adjust.interface.edit_name.setText('iter_adjust')
    assign = adjust.interface.edit_body.insert_component(adjust.interface.edit_body._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('counter')
    assign.interface.edit_value.setPlainText('counter + 1')
    assign.interface.check_local.setChecked(True)  # Declared by the free text above

    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')

    on_demand = body.insert_component(body._lookup_entry('on_demand'))
    assert on_demand is not null, 'insert_component(on_demand) failed'
    on_demand.interface.edit_name.setText('finish')
    on_demand.interface.edit_body.setPlainText('Message("done");')


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    # 1. Registration: Domain-level component supporting UDF natively
    meta = env.kit_manager.lookup('fluent.translation_unit')
    assert meta.level == ComponentMetadata.Level.Domain, meta.level
    assert UDF in meta.languages, 'translation_unit should support UDF natively'
    assert meta.display_name and meta.description, 'translation_unit has no display name/description'
    print('registration ok:', meta.display_name)

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    compiler = Compiler(BuildConfig(UDF))

    # 2. An empty unit still emits the required include
    empty = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    empty.build(compiler)
    assert compiler.products[UDF.id][-1] == '#include "udf.h"', compiler.products[UDF.id][-1]
    print('empty unit compile ok')

    # 3. The unit compiles into one fragment, preserving the document order of
    #    free C text and macros (with components nested inside the macros)
    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, graphics)
    _populate(tu)
    before = len(compiler.products.get(UDF.id, []))
    tu.build(compiler)
    fragments = compiler.products[UDF.id]
    assert len(fragments) == before + 1, f'the unit must emit exactly one fragment ({len(fragments) - before})'
    assert fragments[-1] == EXPECTED_SOURCE, fragments[-1]
    print('unit compile ok:')
    print(EXPECTED_SOURCE)

    # 4. Serialization round-trip through restore (nested macros included)
    data = serialize(tu)
    restored = env.kit_manager.lookup('fluent.translation_unit').component_type.restore(data, null, graphics)
    assert serialize(restored) == data, 'round-trip serialization mismatch'
    restored.build(compiler)
    assert compiler.products[UDF.id][-1] == EXPECTED_SOURCE, compiler.products[UDF.id][-1]
    print('serialization round-trip ok')

    # 5. The unit acts as a script root through the whole building pipeline
    script = Script(restored)
    project = Project('UnitCheck', UDF)
    project.scripts.append(script)
    with tempfile.TemporaryDirectory() as output_dir:
        artifacts, warnings = project.build_project(BuildConfig(UDF, output=Path(output_dir)))
        assert len(artifacts) == 1 and artifacts[0].name == 'main.c', artifacts
        assert artifacts[0].read_text(encoding='utf-8') == EXPECTED_SOURCE
    print('script/project pipeline ok')

    # 6. Fill: painting keeps the client-rectangle height (minus the margins) as
    #    the basic height of the body edit
    edit = tu.interface.edit_body
    tu.interface.paint(graphics)
    assert edit.height() == 400 - 2 * 10, edit.height()
    # Growing contents still extend the edit beyond the floor
    edit.setPlainText('\n'.join(f'line_{i} = {i};' for i in range(80)))
    assert edit.height() > 400 - 2 * 10, edit.height()
    # ... and shrinking contents fall back to the floor
    edit.setPlainText('')
    tu.interface.paint(graphics)
    assert edit.height() == 400 - 2 * 10, edit.height()
    print('client-rectangle fill ok')

    # 7. The body completes at the Domain level (the macros take part)
    entry = next(e for e in edit.completions if e.keyword == 'adjust')
    assert edit._entry_participates(entry), 'macros must complete inside the unit'
    print('unit completion filter ok')

    # 8. On a real canvas the unit fills the client rectangle leaving only its
    #    margin, and the canvas extent stays content-driven (no runaway growth)
    from interface.edition_canvas import EditionCanvas
    real = EditionCanvas(null)
    real.resize(800, 600)
    real_tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, real)
    real.add_interface(real_tu.interface)
    real.grab()  # Force a paint event offscreen
    real_edit = real_tu.interface.edit_body
    assert real_edit.x() == 10 and real_edit.y() == 10, (real_edit.x(), real_edit.y())
    assert real_edit.width() == 800 - 2 * 10, real_edit.width()
    assert real_edit.height() == 600 - 2 * 10, real_edit.height()
    # Empty contents: the extent counts only the contents, not the stretched edit
    assert real.minimumHeight() < 300, real.minimumHeight()
    # Growing contents push the canvas beyond the viewport
    real_edit.setPlainText('\n'.join(f'line_{i} = {i};' for i in range(80)))
    assert real_edit.height() > 600, real_edit.height()
    assert real.minimumHeight() >= real_edit.y() + real_edit.height(), \
        (real.minimumHeight(), real_edit.height())
    print('real canvas fill ok:', real_edit.width(), 'x', real_edit.height(),
          '@ extent', real.minimumHeight())

    print('ALL PASSED')


if __name__ == '__main__':
    main()
