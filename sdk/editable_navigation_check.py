# -*- coding: utf-8 -*-
"""
Offscreen regression check: Left/Right arrow navigation across the editable
widgets of inline components (``Component.editableWidgets``).

Covered behaviors:
 1. Right at the end of an editable widget moves the focus to the next editable
    widget (caret placed at its beginning); caret-less widgets (check boxes,
    the type combo) always navigate; leaving the list escapes behind the
    component's placeholder in the enclosing edit.
 2. Left is symmetric: it escapes in front of the placeholder when there is no
    previous editable widget.
 3. Carets mid-text keep the default in-widget behavior.
 4. Navigation clears an ongoing component selection.
 5. Nested components navigate within their own enclosing edit first, and the
    navigation continues through the enclosing component afterwards.
 6. Right in front of a component enters its first editable field with the
    caret at the beginning instead of stepping past the placeholder.
 7. Left behind a component is symmetric: it enters the last editable field
    (text fields take the caret at the end) instead of stepping in front of
    the placeholder.
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from core.environment import Environment
from interface.edition_canvas import EditionCanvas

PLACEHOLDER = '\uFFFC'


def process_events() -> None:
    app = QApplication.instance()
    for _ in range(8):
        app.processEvents()


def key_press(target, key) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, event)


def cursor_to_end(edit) -> None:
    edit.setFocus()
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit.setTextCursor(cursor)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    env = Environment.instance()
    env.import_kit(os.path.join(_root, 'kits', 'common'))

    window = QMainWindow()
    canvas = EditionCanvas(window)
    window.setCentralWidget(canvas)
    window.resize(800, 600)
    window.show()
    process_events()

    edit = canvas.create_visual_code_edit(QRectF(20, 20, 0, 30))
    process_events()

    entry_assign = next(e for e in edit.completions if e.component_name == 'clk.assign')
    entry_br = next(e for e in edit.completions if e.component_name == 'clk.br')
    entry_field = next(e for e in edit.completions if e.component_name == 'clk.field')

    # ---- 1. Rightwards through assign: edit_name -> edit_value -> check boxes
    #          -> type field -> escape
    assign = edit.insert_component(entry_assign)
    assert assign is not None
    process_events()
    edit_name = assign._interface.edit_name
    edit_value = assign._interface.edit_value
    check = assign._interface.check_constant
    check_local = assign._interface.check_local
    edit_type = assign._interface.edit_type
    assert list(assign.editableWidgets()) == [edit_name, edit_value, check, check_local, edit_type]

    edit_name.setFocus()
    edit_name.setPlainText('x')
    cursor = edit_name.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit_name.setTextCursor(cursor)
    key_press(edit_name, Qt.Key.Key_Right)
    assert edit_value.hasFocus(), 'Right at the end of edit_name must enter edit_value'
    assert edit_value.textCursor().position() == 0, 'entering from the left starts at the beginning'

    key_press(edit_value, Qt.Key.Key_Right)  # Empty edit: the caret sits at both edges
    assert check.hasFocus(), 'Right on the empty value edit must reach the check box'

    pos = int(edit.objects[edit._component_spacers[assign].objectName()].position)
    key_press(check, Qt.Key.Key_Right)
    assert check_local.hasFocus(), 'Right on the constant check box must reach the local check box'
    key_press(check_local, Qt.Key.Key_Right)
    assert edit_type.hasFocus(), 'Right on the local check box must reach the type field'
    key_press(edit_type, Qt.Key.Key_Right)  # Caret-less combo: always at both edges
    assert edit.hasFocus(), 'Right on the last editable widget must escape behind the component'
    assert edit.textCursor().position() == pos + 1, 'the caret must sit behind the placeholder'
    print('STEP 1 PASSED: rightwards navigation of assign')

    # ---- 2. Leftwards: type field -> check boxes -> edit_value -> edit_name -> escape in front
    edit_type.setFocus()
    key_press(edit_type, Qt.Key.Key_Left)
    assert check_local.hasFocus(), 'Left on the type field must enter the local check box'
    key_press(check_local, Qt.Key.Key_Left)
    assert check.hasFocus(), 'Left on the local check box must enter the constant check box'
    key_press(check, Qt.Key.Key_Left)
    assert edit_value.hasFocus(), 'Left on the check box must enter edit_value'
    key_press(edit_value, Qt.Key.Key_Left)
    assert edit_name.hasFocus(), 'Left on the value edit must enter edit_name'
    assert edit_name.textCursor().position() == 1, 'entering from the right ends at the text end'
    key_press(edit_name, Qt.Key.Key_Left)  # Default in-widget behavior: caret moves home
    assert edit_name.hasFocus() and edit_name.textCursor().position() == 0
    key_press(edit_name, Qt.Key.Key_Left)
    assert edit.hasFocus(), 'Left at the first editable widget must escape in front'
    assert edit.textCursor().position() == pos, 'the caret must sit before the placeholder'
    print('STEP 2 PASSED: leftwards navigation of assign')

    # ---- 3. Mid-text carets keep the default in-widget behavior
    edit_name.setFocus()
    edit_name.setPlainText('ab')
    cursor = edit_name.textCursor()
    cursor.setPosition(1)
    edit_name.setTextCursor(cursor)
    key_press(edit_name, Qt.Key.Key_Right)
    assert edit_name.hasFocus(), 'mid-text Right must stay inside the widget'
    assert edit_name.textCursor().position() == 2
    key_press(edit_name, Qt.Key.Key_Left)
    assert edit_name.hasFocus() and edit_name.textCursor().position() == 1
    print('STEP 3 PASSED: mid-text carets untouched')

    # ---- 4. Branch chain: condition -> then -> else -> escape (and leftwards out)
    branch = edit.insert_component(entry_br)
    assert branch is not None
    process_events()
    cond = branch._interface.edit_cond
    then = branch._interface.edit_then
    els = branch._interface.edit_else
    pos_br = int(edit.objects[edit._component_spacers[branch].objectName()].position)

    assert cond.hasFocus(), 'insertion must focus the first editable field'
    key_press(cond, Qt.Key.Key_Right)
    assert then.hasFocus()
    key_press(then, Qt.Key.Key_Right)
    assert els.hasFocus()
    key_press(els, Qt.Key.Key_Right)
    assert edit.hasFocus(), 'the chain must escape behind the branch'
    assert edit.textCursor().position() == pos_br + 1

    cond.setFocus()
    key_press(cond, Qt.Key.Key_Left)
    assert edit.hasFocus(), 'Left at the first field must escape in front of the branch'
    assert edit.textCursor().position() == pos_br
    print('STEP 4 PASSED: branch navigation chain')

    # ---- 5. Navigating away clears an ongoing selection
    cursor_to_end(edit)
    key_press(edit, Qt.Key.Key_Backspace)  # Selects the trailing assign component
    assert edit.selectedComponent() is assign
    cond.setFocus()
    key_press(cond, Qt.Key.Key_Left)
    assert edit.selectedComponent() is None, 'navigation must clear the selection'
    print('STEP 5 PASSED: navigation clears the selection')

    # ---- 6. Nested components navigate inside their own edit first
    field = edit_value.insert_component(entry_field)
    assert field is not None
    process_events()
    owner = field._interface.edit_owner
    member = field._interface.edit_member
    assert list(field.editableWidgets()) == [owner, member]
    assert owner.hasFocus(), 'insertion must focus the owner field'

    key_press(owner, Qt.Key.Key_Right)
    assert member.hasFocus(), 'Right must enter the member field'
    pos_field = int(edit_value.objects[edit_value._component_spacers[field].objectName()].position)
    key_press(member, Qt.Key.Key_Right)
    assert edit_value.hasFocus(), 'the nested chain must escape into the enclosing edit'
    assert edit_value.textCursor().position() == pos_field + 1
    assert edit_value.document().characterAt(pos_field) == PLACEHOLDER

    # The enclosing edit sits at its end: the navigation continues through assign
    key_press(edit_value, Qt.Key.Key_Right)
    assert check.hasFocus(), 'the outer component must continue the navigation'
    print('STEP 6 PASSED: nested navigation chains through the outer component')

    # ---- 7. Right in front of a component enters its first editable field
    edit_name.setPlainText('nav')
    # The branch inserted in step 4 shifted the assign placeholder; re-read it
    pos = int(edit.objects[edit._component_spacers[assign].objectName()].position)
    edit.setFocus()
    cursor = edit.textCursor()
    cursor.setPosition(pos)  # Right before the assign placeholder
    edit.setTextCursor(cursor)
    key_press(edit, Qt.Key.Key_Right)
    assert edit_name.hasFocus(), 'Right before a component must enter its first field'
    assert edit_name.textCursor().position() == 0, 'the caret must land at the field start'
    print('STEP 7 PASSED: right before a component enters its first field')

    # ---- 8. Left behind a component enters its last editable field
    edit.setFocus()
    cursor = edit.textCursor()
    cursor.setPosition(pos + 1)  # Right behind the assign placeholder
    edit.setTextCursor(cursor)
    key_press(edit, Qt.Key.Key_Left)
    assert edit_type.hasFocus(), 'Left behind a component must enter its last field'

    # Text fields take the caret at their end
    els.setPlainText('xy')
    pos_br = int(edit.objects[edit._component_spacers[branch].objectName()].position)
    edit.setFocus()
    cursor = edit.textCursor()
    cursor.setPosition(pos_br + 1)  # Right behind the branch placeholder
    edit.setTextCursor(cursor)
    key_press(edit, Qt.Key.Key_Left)
    assert els.hasFocus(), 'Left behind the branch must enter its else field'
    assert els.textCursor().position() == len(els.toPlainText()), \
        'text fields must take the caret at the end'
    print('STEP 8 PASSED: left behind a component enters its last field')

    print('EDITABLE NAVIGATION CHECK PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
