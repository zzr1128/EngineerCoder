# -*- coding: utf-8 -*-
"""
Offscreen regression check: two-step selection/deletion of inline components.

Covered behaviors:
 1. Backspace/Delete adjacent to the placeholder of a component owning fields
    selects it first (theme 'selected' highlight on the placeholder); a second
    Backspace/Delete deletes it.
 2. Deletion and restoration participate in undo/redo.
 3. Components without an auto-focus widget (operators) are deleted directly.
 4. Backspace at the very beginning of a field selects the owning component;
    a further Backspace/Delete deletes it; clicking elsewhere clears the
    selection.
 5. Nested components are selected/deleted within their own enclosing edit.
 6. Inline-object positions stay accurate when text is typed around them.
 7. Deleting an enclosing component cascades the detachment of the components
    nested inside it (their interfaces must not keep being painted); undoing
    cascades the reattachment through the repaint path of the placeholders.
 8. The plain-name fields of a field component never take part in the completion:
    kit-contributed keywords are never absorbed and no popup shows while typing.
 9. Single-line (QLineEdit) first fields follow the same two-step selection:
    Backspace at position 0 selects the owner, a second press deletes it.
"""

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


def mouse_press(target) -> None:
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(4, 4), QPointF(4, 4),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, event)


def cursor_to_end(edit) -> None:
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit.setTextCursor(cursor)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    env = Environment.instance()
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))  # Contributes kit completion keywords

    window = QMainWindow()
    canvas = EditionCanvas(window)
    window.setCentralWidget(canvas)
    window.resize(800, 600)
    window.show()
    process_events()

    edit = canvas.create_visual_code_edit(QRectF(20, 20, 0, 30))
    process_events()

    entry_field = next(e for e in edit.completions if e.component_name == 'clk.field')
    entry_plus = next(e for e in edit.completions if e.component_name == 'clk.plus')
    entry_assign = next(e for e in edit.completions if e.component_name == 'clk.assign')
    entry_br = next(e for e in edit.completions if e.component_name == 'clk.br')

    # ---- 1. Backspace behind the placeholder selects; second Backspace deletes
    comp = edit.insert_component(entry_field)
    assert comp is not None, 'component insertion failed'
    process_events()
    cursor_to_end(edit)

    key_press(edit, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is comp, 'backspace behind the placeholder must select'
    spacer = edit._component_spacers[comp]
    assert spacer.styleSheet(), 'the selected placeholder must carry the highlight style'
    assert PLACEHOLDER in edit.toPlainText(), 'selecting must not delete'

    key_press(edit, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is None, 'selection must be consumed by the deletion'
    assert PLACEHOLDER not in edit.toPlainText(), 'second backspace must delete the placeholder'
    assert comp not in edit.inserted_components, 'the component must be detached'
    assert spacer.isHidden(), 'the placeholder must be hidden after removal'
    print('STEP 1 PASSED: select then delete via Backspace')

    # ---- 2. Undo restores the component; redo removes it again
    edit.undo()
    edit.viewport().repaint()
    process_events()
    assert PLACEHOLDER in edit.toPlainText(), 'undo must restore the placeholder'
    assert comp in edit.inserted_components, 'undo must reattach the component'
    assert not spacer.isHidden(), 'undo must show the placeholder again'

    edit.redo()
    process_events()
    assert PLACEHOLDER not in edit.toPlainText(), 'redo must remove the placeholder again'
    assert comp not in edit.inserted_components, 'redo must detach the component again'
    edit.undo()
    edit.viewport().repaint()
    process_events()
    assert PLACEHOLDER in edit.toPlainText()
    print('STEP 2 PASSED: undo/redo round trip')

    # ---- 3. Delete ahead of the placeholder selects too
    cursor = edit.textCursor()
    cursor.setPosition(0)  # Right before the placeholder
    edit.setTextCursor(cursor)
    key_press(edit, Qt.Key.Key_Delete)
    assert edit.selectedComponent() is comp, 'delete ahead of the placeholder must select'
    key_press(edit, Qt.Key.Key_Delete)
    assert PLACEHOLDER not in edit.toPlainText(), 'second delete must remove the component'
    edit.undo()
    edit.viewport().repaint()
    process_events()
    assert PLACEHOLDER in edit.toPlainText()
    print('STEP 3 PASSED: Delete-key selection')

    # ---- 4. Operators (field-bearing like every other component now) select
    #      first and delete on the second key press
    edit.setPlainText('')  # Detaches the restored component through the regular path
    process_events()
    plus = edit.insert_component(entry_plus)
    assert plus is not None
    process_events()
    cursor_to_end(edit)
    key_press(edit, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is plus, 'backspace behind the placeholder must select'
    key_press(edit, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is None, 'selection must be consumed by the deletion'
    assert PLACEHOLDER not in edit.toPlainText(), 'the operator must be deleted after selection'
    print('STEP 4 PASSED: select then delete operators')

    # ---- 5. Field-level trigger: Backspace at the beginning of a field selects
    #      the owning component (with text typed before it: positions must hold)
    assign = edit.insert_component(entry_assign)
    assert assign is not None
    process_events()

    doc = edit.document()
    cursor = edit.textCursor()
    cursor.setPosition(0)
    cursor.insertText('hi ')  # Type before the placeholder; positions must follow
    process_events()
    spacer_assign = edit._component_spacers[assign]
    pos = int(edit.objects[spacer_assign.objectName()].position)
    assert doc.characterAt(pos) == PLACEHOLDER, (
        f'recorded position {pos} does not point at the placeholder '
        f'(found {doc.characterAt(pos)!r})')
    assert edit.toPlainText() == f'hi {PLACEHOLDER}', 'unexpected document contents'

    field = assign._interface.edit_value
    field.setFocus()
    key_press(field, Qt.Key.Key_Backspace)  # Cursor starts at position 0
    assert edit.selectedComponent() is assign, 'backspace at the field start must select the owner'
    assert spacer_assign.styleSheet(), 'the owner placeholder must be highlighted'

    key_press(field, Qt.Key.Key_Delete)  # Any Backspace/Delete confirms the deletion
    assert PLACEHOLDER not in edit.toPlainText(), 'the owner must be deleted'
    assert assign not in edit.inserted_components
    assert edit.toPlainText() == 'hi ', 'surrounding text must survive the deletion'
    print('STEP 5 PASSED: field-level selection and deletion')

    # ---- 6. Undo restores; clicking inside a field clears the selection
    edit.undo()
    edit.viewport().repaint()
    process_events()
    assert assign in edit.inserted_components, 'undo must reattach the owner component'

    key_press(field, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is assign
    mouse_press(field)
    assert edit.selectedComponent() is None, 'clicking elsewhere must clear the selection'
    assert not spacer_assign.styleSheet(), 'the highlight must be removed on deselection'
    print('STEP 6 PASSED: click deselects')

    # ---- 7. Nested components are handled by their own enclosing edit
    branch = field.insert_component(entry_br)
    assert branch is not None
    process_events()
    nested_field = branch._interface.edit_cond
    nested_field.setFocus()
    key_press(nested_field, Qt.Key.Key_Backspace)
    assert field.selectedComponent() is branch, 'the nested edit must own the selection'
    assert edit.selectedComponent() is None, 'the outer edit must stay uninvolved'
    key_press(nested_field, Qt.Key.Key_Backspace)
    assert PLACEHOLDER not in field.toPlainText(), 'the nested component must be deleted'
    assert branch not in field.inserted_components
    assert assign in edit.inserted_components, 'the outer component must survive'
    print('STEP 7 PASSED: nested selection and deletion')

    # ---- 8. Deleting the enclosing component must cascade: the interfaces of the
    #      nested components are registered flatly on the same graphics and must be
    #      detached as well (and reattached on undo)
    branch = field.insert_component(entry_br)
    assert branch is not None
    process_events()
    cond_edit = branch._interface.edit_cond
    inner = cond_edit.insert_component(entry_field)
    assert inner is not None
    process_events()
    assert branch.interface in canvas.components, 'the nested component must be painted'
    assert inner.interface in canvas.components, 'the deeply nested component must be painted'

    cursor_to_end(edit)
    key_press(edit, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is assign, 'the outer component must be selected'
    key_press(edit, Qt.Key.Key_Backspace)
    assert PLACEHOLDER not in edit.toPlainText(), 'the outer component must be deleted'
    assert assign not in edit.inserted_components
    assert branch not in field.inserted_components, 'the nested component must be cascade-detached'
    assert inner not in cond_edit.inserted_components, 'the deep component must be cascade-detached'
    assert branch.interface not in canvas.components, 'the nested interface must not remain painted'
    assert inner.interface not in canvas.components, 'the deep interface must not remain painted'

    edit.undo()
    edit.viewport().repaint()
    process_events()
    assert assign in edit.inserted_components, 'undo must reattach the outer component'
    field.viewport().repaint()  # Repainting the hidden nested placeholders cascades
    process_events()
    assert branch in field.inserted_components, 'undo must cascade-reattach the nested component'
    cond_edit.viewport().repaint()
    process_events()
    assert inner in cond_edit.inserted_components, 'undo must cascade-reattach the deep component'
    assert branch.interface in canvas.components, 'the nested interface must be painted again'
    assert inner.interface in canvas.components, 'the deep interface must be painted again'
    print('STEP 8 PASSED: cascade detachment and reattachment of nested components')

    # ---- 9. The plain-name fields of a field component restrict completion to
    #      derived suggestions: the kit keywords (e.g. the fluent DEFINE_* macros)
    #      must not be absorbed back, and no popup shows while typing (no project
    #      is loaded here, so no derived suggestion exists either)
    assert env.kit_manager.completions, 'the fluent kit must have contributed keywords'
    member_comp = edit.insert_component(entry_field)
    assert member_comp is not None
    process_events()
    owner_edit = member_comp._interface.edit_owner
    member_edit = member_comp._interface.edit_member
    assert owner_edit.derivedCompletionsEnabled(), 'the owner field must restrict to derived suggestions'
    assert member_edit.derivedCompletionsEnabled(), 'the member field must restrict to derived suggestions'
    absorbed = len(owner_edit.completions)
    assert absorbed == 0, \
        'a derived-only edit without a project holds no entries (kit keywords excluded)'

    owner_edit.setFocus()
    for ch in 'adjust':  # Real key presses run the kit synchronization every time
        key = getattr(Qt.Key, f'Key_{ch.upper()}')
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, ch)
        QApplication.sendEvent(owner_edit, event)
        process_events()
        assert owner_edit._popup is None or not owner_edit._popup.isVisible(), \
            'the completion popup must never show in a plain-name field'
    assert owner_edit.toPlainText() == 'adjust', 'the typed name must stay plain text'
    assert len(owner_edit.completions) == absorbed, \
        'kit keywords must not be absorbed into a derived-only edit'
    assert PLACEHOLDER not in owner_edit.toPlainText(), \
        'typing must stay plain text in a derived-only edit'
    print('STEP 9 PASSED: plain-name fields restrict completion to derived suggestions')

    # ---- 10. Single-line first fields (e.g. the function name of a DEFINE_*
    #      macro) trigger the same two-step selection as text edits
    edit.setPlainText('')  # Detach the leftovers of the previous steps
    process_events()
    entry_adjust = next(e for e in edit.completions if e.component_name == 'fluent.adjust')
    adjust = edit.insert_component(entry_adjust)
    assert adjust is not None
    process_events()
    name_field = adjust._interface.edit_name  # A QLineEdit: the macro's function name
    name_field.setFocus()
    key_press(name_field, Qt.Key.Key_Backspace)  # Cursor starts at position 0
    assert edit.selectedComponent() is adjust, \
        'backspace at the lineedit start must select the owner'
    key_press(name_field, Qt.Key.Key_Backspace)
    assert edit.selectedComponent() is None, 'selection must be consumed by the deletion'
    assert PLACEHOLDER not in edit.toPlainText(), 'the owner must be deleted'
    assert adjust not in edit.inserted_components
    print('STEP 10 PASSED: single-line field selection and deletion')

    print('SELECTION CHECK PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
