# -*- coding: utf-8 -*-
"""
Headless reproduction of the "New Script" UI flow: boots the real
EditorWindow off-screen and invokes ``add_script`` the way the menu action
does, so the crash the user sees becomes a traceback we can fix.
Also covers the untitled flow ('Untitled-N' placeholders) and the per-tab
save/discard/cancel dialogs the project save publishes for unsaved tabs.
"""

import os
import sys
import tempfile
import traceback

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface'),
             os.path.join(_root, 'sdk')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from alias import *
from core.localization import _


def main() -> void:
    app = QApplication(sys.argv)
    from interface.editor import EditorWindow
    window = EditorWindow()
    window.show()
    app.processEvents()
    print('window up, scripts =', [s.display_name for s in window.env.project.scripts])

    try:
        window.add_script('case-two')
        window.add_script('case-three')
        app.processEvents()
        print('add_script ok, scripts =', [s.display_name for s in window.env.project.scripts])
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    assert len(window.env.project.scripts) == 3, 'every new script must be appended'
    assert len(window.tabs) == 3, 'every script must own a distinct canvas'
    assert len(window._script_handlers) == 3, 'every tab must map to its script'
    assert len(set(window.tabs.values())) == 3, 'canvases must not be shared'

    # Explicit names stay named: saving must not treat them as untitled
    assert not any(s.untitled for s in window.env.project.scripts)

    # --- untitled flow: no name means an auto 'Untitled-N' placeholder ---
    untitled_base = _('ui.script.untitled')
    try:
        window.add_script()
        window.add_script()
        app.processEvents()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    assert window.env.project.scripts[3].display_name == f'{untitled_base}-1'
    assert window.env.project.scripts[4].display_name == f'{untitled_base}-2'
    assert window.env.project.scripts[3].untitled
    assert window.env.project.scripts[4].untitled
    print('untitled placeholders ok:', [s.display_name for s in window.env.project.scripts])

    original_question = QMessageBox.question
    original_save_file = QFileDialog.getSaveFileName
    original_exec = QInputDialog.exec
    original_text_value = QInputDialog.textValue
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'demo.ecproj'
        window.env.project.path = str(archive)

        # --- save publishes one dialog per dirty tab; path-less scripts get a
        #     save-file dialog before their .ecscript file is written ---
        case_two, untitled_one = window.env.project.scripts[1], window.env.project.scripts[3]
        case_two.mark_dirty()
        untitled_one.mark_dirty()
        asked: IList[int] = [0]
        answers = iter([QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Save])
        save_paths = iter([str(Path(tmp) / 'motor.ecscript'), str(Path(tmp) / 'pump.ecscript')])
        naming_answers = iter(['pump', 'valve'])

        def question(*args, **kwargs):
            asked[0] += 1
            return next(answers)

        def _mock_exec(self_dlg, *args, **kwargs):
            from PySide6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted

        def _mock_text_value(self_dlg):
            return next(naming_answers)

        QMessageBox.question = staticmethod(question)
        QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (next(save_paths), ''))
        QInputDialog.exec = _mock_exec
        QInputDialog.textValue = _mock_text_value
        try:
            window.save_project()
        finally:
            QMessageBox.question = original_question
            QFileDialog.getSaveFileName = original_save_file
            QInputDialog.exec = original_exec
            QInputDialog.textValue = original_text_value
        app.processEvents()

        assert asked[0] == 2, 'one dialog per dirty tab'
        assert archive.exists(), 'the project archive must be written'
        assert (Path(tmp) / 'motor.ecscript').exists(), 'path-less scripts save to the chosen file'
        assert case_two.path == Path(tmp) / 'motor.ecscript'
        assert not case_two.is_dirty and case_two.display_name == 'case-two'
        # The untitled script took its name from the chosen file
        assert untitled_one.display_name == 'pump' and not untitled_one.untitled
        titles = [window.tabWidget_editor.tabText(i)
                  for i in range(window.tabWidget_editor.count())]
        assert 'pump' in titles, 'the tab follows the file-stem rename'
        assert not window.env.project.is_dirty, 'everything saved clears the dirty state'
        print('per-tab save ok, tabs =', titles)

        # --- discard keeps the script dirty but the rest still saves ---
        case_three = window.env.project.scripts[2]
        case_three.mark_dirty()
        asked[0] = 0
        QMessageBox.question = staticmethod(question)
        answers = iter([QMessageBox.StandardButton.Discard])
        archive.unlink()
        try:
            window.save_project()
        finally:
            QMessageBox.question = original_question
        assert asked[0] == 1, 'only the dirty tab gets asked'
        assert archive.exists(), 'the archive still saves the chosen scripts'
        assert case_three.is_dirty, 'discarded changes stay unsaved'
        assert window.env.project.is_dirty, 'unsaved scripts keep the project dirty'
        print('discard branch ok')

        # --- cancel aborts the whole save ---
        QMessageBox.question = staticmethod(question)
        answers = iter([QMessageBox.StandardButton.Cancel])
        archive.unlink()
        try:
            window.save_project()
        finally:
            QMessageBox.question = original_question
        assert not archive.exists(), 'canceling must not write the archive'
        assert case_three.is_dirty
        print('cancel branch ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
