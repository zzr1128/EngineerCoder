# -*- coding: utf-8 -*-
"""
Offscreen regression check: clicking a component selects it whole, and the
clipboard actions (copy/cut/paste) act on the selection.

Covered behaviors:
 1. A left click onto the placeholder of an inserted component selects it whole
    (theme 'selected' highlight); a click outside any component leaves none
    selected.
 2. Ctrl+C copies the selected component onto the clipboard (the SelectionMime
    archive carries its serialization) without removing it; a bare modifier key
    press (Ctrl alone) keeps the selection alive for the shortcut to follow.
 3. Ctrl+X cuts the selected component: the clipboard keeps the archive while
    the component leaves the text flow; undoing restores it.
 4. Ctrl+V pastes the archived component back at the caret, restoring an equal
    serialization.
 5. The clipboard shortcuts also work while the focus stands in a field of the
    inserted component (routed through the event filter); a bare modifier key
    press there keeps the selection too.
 6. The completion filter criteria apply to pastes: a plain-name field
    (derived-only) rejects the component archive.
"""

import json
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from alias import serialize
from core.environment import Environment
from interface.edition_canvas import EditionCanvas
from interface.visual_code_edit import VisualCodeEdit

PLACEHOLDER = '\uFFFC'


def process_events() -> None:
    app = QApplication.instance()
    for _ in range(8):
        app.processEvents()


def key_press(target, key, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifier)
    QApplication.sendEvent(target, event)


def click(edit, point) -> None:
    """A left click into the viewport of the edit (viewport coordinates)."""
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point), QPointF(point),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(edit.viewport(), event)


def clipboard_archive():
    mime = QApplication.clipboard().mimeData()
    if mime is None or not mime.hasFormat(VisualCodeEdit.SelectionMime):
        return None
    return json.loads(bytes(mime.data(VisualCodeEdit.SelectionMime)).decode('utf-8'))


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

    entry_br = next(e for e in edit.completions if e.component_name == 'clk.br')
    entry_field = next(e for e in edit.completions if e.component_name == 'clk.field')

    # ---- 1. Clicking the component selects it whole; clicking beside clears
    branch = edit.insert_component(entry_br)
    assert branch is not None, 'component insertion failed'
    process_events()
    spacer = edit._component_spacers[branch]
    click(edit, spacer.geometry().center())
    assert edit.selectedComponent() is branch, 'clicking the component must select it'
    assert spacer.styleSheet(), 'the selected placeholder must carry the highlight style'
    assert PLACEHOLDER in edit.toPlainText(), 'selecting must not delete'

    click(edit, spacer.geometry().bottomRight() + edit.viewport().rect().bottomRight())
    assert edit.selectedComponent() is None, 'a click outside any component must clear the selection'
    print('STEP 1 PASSED: click selects the component whole')

    # ---- 2. Ctrl+C copies the selected component (archive on the clipboard)
    click(edit, spacer.geometry().center())
    assert edit.selectedComponent() is branch
    key_press(edit, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    archive = clipboard_archive()
    assert archive is not None, 'the copy must put the SelectionMime archive on the clipboard'
    assert archive['text'] == PLACEHOLDER, 'the archive must hold exactly the component'
    assert archive['components'][0]['name'] == 'clk.br', 'the archive must name the component'
    assert archive['components'][0]['data'] == serialize(branch), 'the archive must carry the serialization'
    assert PLACEHOLDER in edit.toPlainText(), 'copying must not remove the component'
    print('STEP 2 PASSED: Ctrl+C copies the selected component')

    # ---- 2b. A bare modifier key press keeps the selection alive
    key_press(edit, Qt.Key.Key_Control)
    assert edit.selectedComponent() is branch, 'Ctrl alone must not clear the selection'
    key_press(edit, Qt.Key.Key_Shift)
    assert edit.selectedComponent() is branch, 'Shift alone must not clear the selection'
    print('STEP 2B PASSED: bare modifier keys keep the selection')

    # ---- 3. Ctrl+X cuts: the component leaves, the clipboard keeps it; undo restores
    key_press(edit, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    assert PLACEHOLDER not in edit.toPlainText(), 'cutting must remove the component'
    assert branch not in edit.inserted_components
    assert clipboard_archive() is not None, 'the clipboard must keep the archive'
    edit.undo()
    edit.viewport().repaint()
    process_events()
    assert PLACEHOLDER in edit.toPlainText(), 'undo must restore the cut component'
    assert len(edit.inserted_components) == 1
    branch = edit.inserted_components[0]
    print('STEP 3 PASSED: Ctrl+X cuts the selected component')

    # ---- 4. Ctrl+V pastes the archived component back at the caret
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit.setTextCursor(cursor)
    key_press(edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    process_events()
    assert edit.toPlainText().count(PLACEHOLDER) == 2, 'the paste must insert a second placeholder'
    assert len(edit.inserted_components) == 2, 'the pasted component must join the edit'
    pasted = edit.inserted_components[-1]
    assert serialize(pasted) == serialize(branch), 'the pasted component must equal the archived one'
    print('STEP 4 PASSED: Ctrl+V pastes the archived component')

    # ---- 5. The shortcuts also work while the focus stands in a field
    edit._remove_component(pasted)  # Back to a single component
    process_events()
    cond = branch._interface.edit_cond
    cond.setFocus()
    key_press(cond, Qt.Key.Key_Backspace)  # Select through the field-level trigger
    assert edit.selectedComponent() is branch, 'the field-level backspace must select'
    key_press(cond, Qt.Key.Key_Control)
    assert edit.selectedComponent() is branch, 'Ctrl alone in a field must not clear the selection'
    key_press(cond, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard_archive() is not None, 'Ctrl+C in a field must copy the selected component'
    key_press(cond, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    assert PLACEHOLDER not in edit.toPlainText(), 'Ctrl+X in a field must cut the selected component'
    edit.undo()
    edit.viewport().repaint()
    process_events()
    print('STEP 5 PASSED: clipboard shortcuts route through the fields')

    # ---- 6. A derived-only field rejects the component archive
    key_press(edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)  # Restore the component
    process_events()
    branch = edit.inserted_components[0] if edit.inserted_components else branch
    click(edit, edit._component_spacers[branch].geometry().center())
    key_press(edit, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    member = edit.insert_component(entry_field)
    assert member is not None
    process_events()
    owner = member._interface.edit_owner
    assert owner.derivedCompletionsEnabled(), 'the owner field must be derived-only'
    assert not owner.paste_components(), 'a derived-only field must reject the component archive'
    assert not owner.inserted_components, 'no component must enter the plain-name field'
    print('STEP 6 PASSED: pastes obey the completion filter criteria')

    print('COMPONENT CLIPBOARD CHECK PASSED')
    sys.stdout.flush()
    # Qt offscreen teardown segfaults nondeterministically during interpreter
    # shutdown; the test has already succeeded, so hard-exit instead.
    os._exit(0)


if __name__ == '__main__':
    sys.exit(main())
