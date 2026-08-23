# -*- coding: utf-8 -*-
"""Probe: reproduce the minimized-restore clipping and the focus drift of the
number fields by collapsing the canvas geometry to zero and restoring it."""

import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from alias import *
from core.environment import Environment
from interface.edition_canvas import EditionCanvas


def _dump(tag: string, edit) -> void:
    doc = edit.document()
    print(f'[{tag}] w={edit.width()} h={edit.height()} '
          f'min={edit.minimumHeight()} max={edit.maximumHeight()} '
          f'basic={edit.basic_height} cached_max={edit.max_height} '
          f'vp={edit.viewport().width()}x{edit.viewport().height()} '
          f'textWidth={doc.textWidth()} docH={doc.documentLayout().documentSize().height()} '
          f'fit={edit._heightToFit()} vscroll={edit.verticalScrollBar().value()}')


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    window = QWidget()
    window.resize(800, 600)
    canvas = EditionCanvas(window)
    canvas.setGeometry(0, 0, 800, 600)

    tu = env.kit_manager.lookup('fluent.translation_unit').component_type(null, canvas)
    canvas.add_interface(tu.interface)
    body = tu.interface.edit_body

    window.show()
    canvas.show()
    canvas.resize(800, 600)
    app.processEvents()

    # Insert the assignment like a user would: after the canvas has painted
    assign = body.insert_component(body._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('speed')
    assign.interface.edit_value.setPlainText('123.5')
    value_edit = assign.interface.edit_value
    canvas.repaint()
    app.processEvents()
    print(f'canvas {canvas.width()}x{canvas.height()} painted '
          f'components={len(canvas.components)} widgets={len(canvas.widgets)}')
    _dump('body    ', body)
    _dump('normal ', value_edit)

    # Focus phase first: observe the drift while the geometry is healthy
    print('--- focus phase ---')
    body.setFocus()
    app.processEvents()
    _dump('pre-focus ', value_edit)
    value_edit.setFocus()
    app.processEvents()
    _dump('on-focus  ', value_edit)
    QTimer.singleShot(0, lambda: _dump('tick-focus', value_edit))
    print('--- minimize phase ---')

    # Simulate the window minimization: the whole geometry collapses to zero
    window.resize(0, 0)
    canvas.resize(0, 0)
    canvas.repaint()
    app.processEvents()
    _dump('collapse', value_edit)

    # Simulate the restore: the geometry comes back
    window.resize(800, 600)
    canvas.resize(800, 600)
    canvas.repaint()
    app.processEvents()
    _dump('restored', value_edit)

    # Deferred refits settle one event-loop tick later
    QTimer.singleShot(0, lambda: _dump('settled ', value_edit))
    QTimer.singleShot(100, app.quit)
    app.exec()


if __name__ == '__main__':
    main()
