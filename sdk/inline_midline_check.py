# -*- coding: utf-8 -*-
"""
Offscreen regression check: an inline component inserted after text on the same
line must not paint over the preceding text (its origin must follow the
placeholder instead of being pinned to the column's left edge).
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtWidgets import QApplication, QMainWindow

from core.environment import Environment
from interface.edition_canvas import EditionCanvas


def process_events() -> None:
    app = QApplication.instance()
    for _ in range(8):
        app.processEvents()


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

    # An edit spanning the canvas width (like assign's value edit)
    edit = canvas.create_visual_code_edit(QRectF(20, 20, 0, 30))
    process_events()

    edit.setPlainText('hello world')
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit.setTextCursor(cursor)

    entry = next(e for e in edit.completions if e.component_name == 'clk.field')
    component = edit.insert_component(entry)
    assert component is not None, 'component insertion failed'
    process_events()

    spacer = edit._component_spacers[component]
    # Placeholder position in canvas coordinates (spacer is a child of the viewport)
    viewport_on_canvas = canvas.mapFromGlobal(edit.viewport().mapToGlobal(QPoint(0, 0)))
    spacer_canvas = QPoint(viewport_on_canvas.x() + spacer.x(), viewport_on_canvas.y() + spacer.y())
    origin = component.interface.origin

    print(f'placeholder (canvas coords): ({spacer_canvas.x()}, {spacer_canvas.y()})')
    print(f'component origin           : ({origin.x()}, {origin.y()})')

    # 1. The component origin must follow the placeholder (both axes)
    assert abs(origin.x() - spacer_canvas.x()) <= 1, (
        f'origin x {origin.x()} does not follow placeholder x {spacer_canvas.x()}: '
        'the component would paint over the preceding text')
    assert abs(origin.y() - spacer_canvas.y()) <= 1, (
        f'origin y {origin.y()} does not follow placeholder y {spacer_canvas.y()}')

    # 2. The placeholder must sit after (not before) the preceding text
    content_left = edit._content_left()
    cursor_before = edit.textCursor()
    cursor_before.movePosition(cursor_before.MoveOperation.End)
    cursor_before.movePosition(cursor_before.MoveOperation.PreviousCharacter)
    text_right = edit.cursorRect(cursor_before).right()
    print(f'text right edge: {text_right}, placeholder x (viewport): '
          f'{spacer.pos().x()}, content left: {content_left}')
    assert spacer.pos().x() >= text_right, 'placeholder overlaps the preceding text'

    # 3. The component box must not overrun the right edge of the text column
    layout = component.interface.layout
    edit.graphics.push_anchor(origin)
    try:
        size = layout.size(edit.graphics)
    finally:
        edit.graphics.pop_anchor()
    content_right = content_left + edit._content_width()
    print(f'component right edge: {origin.x() + size.width()}, column right: {content_right}')
    assert origin.x() + size.width() <= content_right + 1, 'component overruns the text column'

    # 4. The document still contains the preceding text
    assert 'hello world' in edit.toPlainText()
    assert '\ufffc' in edit.toPlainText()

    # 5. Full-width components still start at the column's left edge: after the same
    #    text, a branch component's placeholder wraps onto a new line
    entry_br = next(e for e in edit.completions if e.component_name == 'clk.br')
    branch = edit.insert_component(entry_br)
    assert branch is not None, 'branch insertion failed'
    process_events()

    spacer_br = edit._component_spacers[branch]
    spacer_br_canvas = QPoint(viewport_on_canvas.x() + spacer_br.x(),
                              viewport_on_canvas.y() + spacer_br.y())
    origin_br = branch.interface.origin
    print(f'branch placeholder (canvas coords): ({spacer_br_canvas.x()}, {spacer_br_canvas.y()})')
    assert abs(origin_br.x() - spacer_br_canvas.x()) <= 1, (
        f'branch origin x {origin_br.x()} does not follow its placeholder x {spacer_br_canvas.x()}')
    # Full width: the placeholder cannot stay mid-line after the field placeholder
    assert spacer_br.pos().x() < spacer.pos().x(), 'full-width placeholder should wrap to line start'
    assert spacer_br.pos().y() > spacer.pos().y(), 'branch should wrap below the field row'

    print('MIDLINE OVERLAP CHECK PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
