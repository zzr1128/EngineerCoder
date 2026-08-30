# -*- coding: utf-8 -*-
"""Probe: the component palette of the left dock and the drag&drop insertion
into visual code edits (acceptance rules included)."""

import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from alias import *


def _mime(component_name: string) -> QMimeData:
    mime = QMimeData()
    mime.setData('application/x-engineercoder-component', component_name.encode('utf-8'))
    return mime


def _drop(edit, component_name: string, x: int = 10, y: int = 10) -> bool:
    # A synthetic QDropEvent never enters the Qt dnd routing (only a real drag
    # session dispatches it), so the probe drives the handler directly: Qt maps
    # the drop position onto widget coordinates before calling dropEvent.
    # The mime data must outlive the event (a real drag's QDrag owns it)
    mime = _mime(component_name)
    event = QDropEvent(QPointF(x, y), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    event.setDropAction(Qt.DropAction.CopyAction)
    edit.dropEvent(event)
    return event.isAccepted() and event.dropAction() == Qt.DropAction.CopyAction


def main() -> void:
    app = QApplication(sys.argv)
    from interface.editor import EditorWindow
    from interface.visual_code_edit import VisualCodeEdit
    window = EditorWindow()
    window.resize(1200, 800)
    window.show()
    app.processEvents()

    palette = window.component_palette
    sections = palette._sections
    total = sum(len(entries) for _, entries in sections)
    print(f'palette sections={len(sections)} entries={total}')
    assert len(sections) >= 2, 'expected at least the clk and the fluent kit sections'
    assert total >= 20, f'expected a well-filled palette, got {total}'
    for header, entries in sections:
        print(f'  [{header.text()}] {len(entries)} entries')

    # The filter narrows the listing and restores it
    palette.apply_filter('zzz_no_such_component')
    assert all(not entry.isVisible() for _, entries in sections for entry in entries), \
        'a non-matching pattern must hide every entry'
    palette.apply_filter('set')
    hit = sum(1 for _, entries in sections for entry in entries if entry.isVisible())
    print(f'filter "set" leaves {hit} visible entries')
    assert hit >= 1, 'the keyword "set" must match at least the assignment'
    palette.apply_filter('')
    assert all(entry.isVisible() for _, entries in sections for entry in entries), \
        'an empty pattern must restore every entry'

    handler = next(iter(window.tabs))
    canvas = window.canvas(handler)
    body = window.script.tu.interface.edit_body

    # A statement drops into the translation unit body
    before = len(body.inserted_components)
    accepted = _drop(body, 'clk.assign')
    app.processEvents()
    assert accepted, 'the body edit must accept the assignment drop'
    assert len(body.inserted_components) == before + 1, 'the drop must insert the component'
    print('drop clk.assign into the body: inserted')

    assign = body.inserted_components[-1]
    name_edit = assign.interface.edit_name
    value_edit = assign.interface.edit_value

    # A plain-name field embeds no components (derived restriction)
    assert name_edit._dropped_component_name(_mime('clk.assign')) is null, \
        'the name field must reject component drops'
    assert not _drop(name_edit, 'clk.assign'), 'the name field must ignore the drop'
    # An expression field rejects statement-level components
    assert value_edit._dropped_component_name(_mime('clk.br')) is null, \
        'the value field must reject statement-level drops'
    # ...but accepts expression-level ones
    assert value_edit._dropped_component_name(_mime('clk.plus')) is not null, \
        'the value field must accept expression-level drops'
    before = len(value_edit.inserted_components)
    assert _drop(value_edit, 'clk.plus'), 'the value field must accept the plus drop'
    assert len(value_edit.inserted_components) == before + 1, 'the plus must be inserted'
    print('filter rules hold: name field rejects, value field takes expressions only')

    # An unknown component never drops
    assert body._dropped_component_name(_mime('clk.no_such')) is null
    assert not _drop(body, 'clk.no_such'), 'unknown components must be ignored'

    # The palette entries carry the right mime payload
    entry = sections[0][1][0]
    assert entry.component_name and '.' in entry.component_name
    print(f'sample entry: {entry.text()} -> {entry.component_name} ({entry.keyword})')

    canvas.repaint()
    app.processEvents()
    print('ALL PASSED')
    app.quit()


if __name__ == '__main__':
    main()
