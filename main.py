# -*- coding: utf-8 -*-

import os
import sys

# Source roots (project root, core and interface) use bare imports;
# make them importable when launched outside an IDE that marks source roots.
_root = os.path.dirname(os.path.abspath(__file__))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtWidgets import QApplication

from interface.editor import EditorWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = EditorWindow()
    win.showMaximized()
    sys.exit(app.exec())
