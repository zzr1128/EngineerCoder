# -*- coding: utf-8 -*-
"""Temporary repro: Backspace at the start of a first VisualCodeEdit field,
following the real application timing (fluent translation unit, popup
confirmations, nested insertions, project load path)."""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow

from alias import serialize, string
from core.environment import Environment
from core.project import Project
from core.script import Script
from interface.edition_canvas import EditionCanvas


def process_events() -> None:
    QApplication.processEvents()


def type_and_confirm(edit, keyword: string) -> None:
    """Type a keyword into the edit and confirm the completion popup (Enter)."""
    edit.setFocus()
    process_events()
    QTest.keyClicks(edit.viewport(), keyword)
    process_events()
    QTest.keyClick(edit.viewport(), Qt.Key.Key_Return)
    process_events()


def backspace_at_start(edit, field) -> bool:
    """Click into the field head and press Backspace (real keyboard path)."""
    target = field.viewport() if hasattr(field, 'viewport') else field
    field.setFocus()
    process_events()
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
    process_events()
    QTest.keyClick(target, Qt.Key.Key_Backspace)
    selected = edit.selectedComponent()
    process_events()
    return selected is not None


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    env = Environment.instance()
    env.import_kit(os.path.join(_root, 'kits', 'cbased'))
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    window = QMainWindow()
    canvas = EditionCanvas(window)
    window.setCentralWidget(canvas)
    window.resize(1000, 700)
    window.show()
    process_events()

    # Real application timing: the script root is a translation unit
    comp_meta = env.kit_manager.lookup('fluent.translation_unit')
    unit = comp_meta.component_type(None, canvas)
    canvas.add_interface(unit.interface)
    script = Script(unit)
    from kits.fluent.fluent import UDF
    project = Project('Test', UDF)
    project.scripts.append(script)
    env.project = project
    body = unit.interface.edit_body
    process_events()

    failures = []

    # 1. Unit body (Domain): DEFINE_ADJUST via popup; its first field is a
    #    QLineEdit (name) - sanity of the two-step selection on plain fields
    type_and_confirm(body, 'adjust')
    adjust = body.inserted_components[0] if body.inserted_components else None
    print('adjust inserted:', adjust is not None)
    if adjust is None:
        print('cannot continue without the macro'); return 1
    name_field = adjust.interface.edit_name
    if not backspace_at_start(body, name_field):
        failures.append('adjust(edit_name QLineEdit) in unit body')
    body.clear_selection()

    # 2. Macro body (Statement): a Branch via popup; its first field edit_cond
    #    is a VisualCodeEdit - the TODO scenario
    macro_body = adjust.interface.edit_body
    type_and_confirm(macro_body, 'if')
    branch = macro_body.inserted_components[0] if macro_body.inserted_components else None
    print('branch inserted:', branch is not None)
    if branch is None:
        print('cannot continue without the branch'); return 1
    cond = branch.interface.edit_cond
    print('focus on edit_cond after insertion:', cond.hasFocus())
    if not backspace_at_start(macro_body, cond):
        failures.append('branch(edit_cond VCE) in macro body')
    macro_body.clear_selection()

    # 3. An operator nested inside the condition (Expression level): the first
    #    field edit_left is a VisualCodeEdit too
    type_and_confirm(cond, 'plus')
    plus = cond.inserted_components[0] if cond.inserted_components else None
    print('plus inserted:', plus is not None)
    if plus is not None:
        left = plus.interface.edit_left
        if not backspace_at_start(cond, left):
            failures.append('plus(edit_left VCE) nested in edit_cond')
        cond.clear_selection()

    # 4. Project load path: serialize the unit, restore into a fresh unit,
    #    then Backspace at the start of the first VCE field of the branch
    archive = serialize(unit)
    restored = comp_meta.component_type.restore(archive, None, canvas)
    canvas.add_interface(restored.interface)
    process_events()
    restored_body = restored.interface.edit_body
    restored_adjust = restored_body.inserted_components[0] if restored_body.inserted_components else None
    restored_branch = restored_adjust.interface.edit_body.inserted_components[0] if restored_adjust else None
    print('restored adjust:', restored_adjust is not None, 'restored branch:', restored_branch is not None)
    if restored_branch is not None:
        restored_cond = restored_branch.interface.edit_cond
        restored_macro_body = restored_adjust.interface.edit_body
        print('cond mapped:', restored_macro_body._widget_components.get(restored_cond, None) is restored_branch)
        print('branch in inserted:', restored_branch in restored_macro_body.inserted_components)
        restored_cond.setFocus()
        process_events()
        QTest.mouseClick(restored_cond.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
        process_events()
        print('cond focus:', restored_cond.hasFocus(), 'cursor pos:', restored_cond.textCursor().position(),
              'visible:', restored_cond.isVisible(), 'size:', restored_cond.width(), restored_cond.height())
        if not backspace_at_start(restored_macro_body, restored_cond):
            failures.append('branch(edit_cond) after project load')
        restored_macro_body.clear_selection()

    print('failures:', failures if failures else 'none')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
