# -*- coding: utf-8 -*-
"""Probe: minimize/restore a real EditorWindow and inspect the number field
geometry, grabbing viewport images to expose clipping and drift."""

import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QTimer, QEvent
from PySide6.QtWidgets import QApplication

from alias import *


def _dump(tag: string, edit) -> void:
    doc = edit.document()
    print(f'[{tag}] w={edit.width()} h={edit.height()} '
          f'min={edit.minimumHeight()} max={edit.maximumHeight()} '
          f'basic={edit.basic_height} cached_max={edit.max_height} '
          f'vp={edit.viewport().width()}x{edit.viewport().height()} '
          f'textWidth={doc.textWidth()} docH={doc.documentLayout().documentSize().height()} '
          f'fit={edit._heightToFit()} frame={edit.frameWidth()} '
          f'geom=({edit.x()},{edit.y()}) visible={edit.isVisible()}')


def _grab(tag: string, edit) -> void:
    pixmap = edit.grab()
    image = pixmap.toImage()
    # Scan the bottom rows for text pixels (anything darker than white-ish bg)
    bottom_ink = 0
    for y in range(max(0, image.height() - 6), image.height()):
        for x in range(0, image.width(), 2):
            pixel = image.pixelColor(x, y)
            if pixel.lightness() < 120:
                bottom_ink += 1
    mid_ink = 0
    for y in range(image.height() // 3, 2 * image.height() // 3):
        for x in range(0, image.width(), 2):
            pixel = image.pixelColor(x, y)
            if pixel.lightness() < 120:
                mid_ink += 1
    print(f'[{tag}] grab {image.width()}x{image.height()} mid-ink={mid_ink} bottom-ink={bottom_ink}')


def _ink_centroid(edit) -> tuple:
    image = edit.grab().toImage()
    total = 0
    sy = 0
    for y in range(image.height()):
        for x in range(0, image.width(), 2):
            pixel = image.pixelColor(x, y)
            if pixel.lightness() < 120:
                total += 1
                sy += y
    return (sy / total if total else -1.0), total


def main() -> void:
    app = QApplication(sys.argv)
    from interface.editor import EditorWindow
    window = EditorWindow()
    window.resize(1200, 800)
    window.show()
    app.processEvents()

    handler = next(iter(window.tabs))
    canvas = window.canvas(handler)
    tu = window.script.tu
    body = tu.interface.edit_body
    assign = body.insert_component(body._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('speed')
    assign.interface.edit_value.setPlainText('123.5')
    value_edit = assign.interface.edit_value
    canvas.repaint()
    app.processEvents()

    _dump('normal ', value_edit)
    _grab('normal ', value_edit)

    print('--- focus phase ---')
    body.setFocus()
    app.processEvents()
    _grab('pre-focus ', value_edit)
    value_edit.setFocus()
    app.processEvents()
    _dump('on-focus  ', value_edit)
    _grab('on-focus  ', value_edit)
    QTimer.singleShot(300, lambda: _grab('late-focus', value_edit))

    def minimize_phase() -> void:
        print('--- minimize phase ---')
        window.showMinimized()
        app.processEvents()
        _dump('minimized', value_edit)
        QTimer.singleShot(500, restore_phase)

    def restore_phase() -> void:
        window.showNormal()
        app.processEvents()
        _dump('restored ', value_edit)
        _grab('restored ', value_edit)
        QTimer.singleShot(500, settle_phase)

    def settle_phase() -> void:
        _dump('settled  ', value_edit)
        _grab('settled  ', value_edit)
        print('--- click-focus phase (sampling ink centroid) ---')
        from PySide6.QtCore import QPoint as _QPoint, Qt as _Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF as _QPointF

        frames: IList[string] = []

        def sample() -> void:
            cy, total = _ink_centroid(value_edit)
            frames.append(f'cy={cy:.2f} ink={total} vscroll={value_edit.verticalScrollBar().value()} '
                          f'h={value_edit.height()}')
            if len(frames) < 12:
                QTimer.singleShot(25, sample)
            else:
                for i, line in enumerate(frames):
                    print(f'  frame{i:02d}: {line}')
                app.quit()

        # Click the middle of the field like a user would
        target = value_edit.viewport()
        pos = _QPoint(target.width() // 2, target.height() // 2)
        press = QMouseEvent(QEvent.Type.MouseButtonPress, _QPointF(pos), _QPointF(pos),
                            _Qt.MouseButton.LeftButton, _Qt.MouseButton.LeftButton,
                            _Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(QEvent.Type.MouseButtonRelease, _QPointF(pos), _QPointF(pos),
                              _Qt.MouseButton.LeftButton, _Qt.MouseButton.NoButton,
                              _Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, press)
        QApplication.sendEvent(target, release)
        sample()

    QTimer.singleShot(600, minimize_phase)
    app.exec()


if __name__ == '__main__':
    main()
