# -*- coding: utf-8 -*-
"""
Headless check of the project lifecycle guards:

- exiting publishes a save/discard/cancel dialog while the project is dirty
  (``closeEvent``): cancel keeps the window open, discard closes it, save
  persists the archive before closing (and stays open when the save aborts);
- ``save_project`` / ``save_project_as`` report their outcome so the callers
  (exit, new project, open project) can abort when the user backs out;
- ``NewProjectDialog`` lists the imported kits with their dependencies and
  languages: checking a kit pulls its dependencies in, unchecking a kit a
  checked one depends on is refused, and the target language combo follows
  the languages the checked kits support;
- ``new_project`` asks about the dirty project first, then applies the name,
  the kits and the target language the dialog publishes.
"""

import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface'),
             os.path.join(_root, 'sdk')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QMessageBox

from alias import *
from core.localization import _


def main() -> int:
    app = QApplication(sys.argv)
    from interface.editor import EditorWindow
    from interface.new_project_dialog import NewProjectDialog

    original_question = QMessageBox.question
    original_save_file = QFileDialog.getSaveFileName
    original_exec = NewProjectDialog.exec
    window = EditorWindow()
    window.show()
    app.processEvents()

    try:
        # --- startup: the fresh blank project is clean and declares its kits ---
        assert not window.env.project.is_dirty, 'a fresh blank project starts clean'
        assert {kit.meta.name for kit in window.env.project.required_kits} == \
               {'cbased', 'clk', 'fluent'}, window.env.project.required_kits
        print('startup state ok')

        # --- NewProjectDialog: kits, dependencies and languages ---
        dlg = NewProjectDialog(window.env.kit_manager, 'demo')
        assert {kit.meta.name for kit in dlg.selected_kits()} == \
               {'cbased', 'clk', 'fluent'}, 'every imported kit starts checked'
        assert dlg.target_language().id == 'udf', dlg.target_language()
        assert dlg._combo_lang.count() == 1, 'only fluent contributes a language'
        # The detail line shows the highlighted kit's languages and dependencies
        assert dlg._label_detail.text(), 'the highlighted kit publishes its details'

        # Unchecking clk is refused: fluent (still checked) depends on it
        clk_item = dlg._item_of('clk')
        clk_item.setCheckState(Qt.CheckState.Unchecked)
        assert clk_item.checkState() == Qt.CheckState.Checked, 'refused unchecking reverts'
        assert dlg._label_status.text(), 'the refusal publishes a hint'

        # Unchecking fluent is fine: nothing depends on it; the language goes
        # away and accepting becomes impossible
        fluent_item = dlg._item_of('fluent')
        fluent_item.setCheckState(Qt.CheckState.Unchecked)
        assert fluent_item.checkState() == Qt.CheckState.Unchecked
        assert dlg._combo_lang.count() == 0, 'no checked kit supports a language now'
        ok_button = dlg._buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert not ok_button.isEnabled(), 'no target language disables accepting'

        # Drop the remaining dependencies too, then re-checking fluent pulls
        # them back in automatically (with a hint)
        dlg._item_of('clk').setCheckState(Qt.CheckState.Unchecked)
        dlg._item_of('cbased').setCheckState(Qt.CheckState.Unchecked)
        assert dlg.selected_kits() == [], dlg.selected_kits()
        dlg._label_status.setText('')
        fluent_item.setCheckState(Qt.CheckState.Checked)
        assert {kit.meta.name for kit in dlg.selected_kits()} == \
               {'fluent', 'clk', 'cbased'}, 'dependencies follow their dependant'
        assert dlg._label_status.text(), 'the automatic checking publishes a hint'
        assert dlg._combo_lang.count() == 1 and ok_button.isEnabled()

        # An empty name disables accepting as well
        dlg._edit_name.setText('   ')
        assert not ok_button.isEnabled()
        dlg._edit_name.setText('demo')
        assert dlg.project_name() == 'demo'
        print('new-project dialog ok')

        # --- save_project reports its outcome ---
        with tempfile.TemporaryDirectory() as tmp:
            window.env.project.path = null  # No path: Save routes through Save As
            QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: ('', ''))
            try:
                assert window.save_project() is False, 'canceling Save As aborts the save'
            finally:
                QFileDialog.getSaveFileName = original_save_file

            archive = Path(tmp) / 'lifecycle.ecproj'
            script = window.env.project.scripts[0]
            window.env.project.path = str(archive)
            script.path = Path(tmp) / 'main.ecscript'
            script.mark_dirty()
            answers = iter([QMessageBox.StandardButton.Cancel])
            QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
            try:
                assert window.save_project() is False, 'canceling a script save aborts'
                assert not archive.exists()
            finally:
                QMessageBox.question = original_question
            assert script.is_dirty, 'the canceled script stays dirty'

            answers = iter([QMessageBox.StandardButton.Save])
            QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
            try:
                assert window.save_project() is True
                assert archive.exists() and not window.env.project.is_dirty
            finally:
                QMessageBox.question = original_question
        print('save outcome reporting ok')

        # --- new_project guards the dirty project, then applies the dialog ---
        window.env.project.mark_dirty()
        old_project = window.env.project
        answers = iter([QMessageBox.StandardButton.Cancel])
        QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
        try:
            window.new_project()
        finally:
            QMessageBox.question = original_question
        assert window.env.project is old_project, 'canceling keeps the current project'

        answers = iter([QMessageBox.StandardButton.Discard])
        QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
        NewProjectDialog.exec = lambda self: QDialog.DialogCode.Accepted
        try:
            window.new_project()
        finally:
            QMessageBox.question = original_question
            NewProjectDialog.exec = original_exec
        assert window.env.project is not old_project, 'discarding proceeds to the dialog'
        assert window.env.project.name == _('ui.project.default_name')
        assert {kit.meta.name for kit in window.env.project.required_kits} == \
               {'cbased', 'clk', 'fluent'}
        assert window.env.project.target_lang.id == 'udf'
        assert len(window.env.project.scripts) == 1, 'the fluent kit provides a root'
        assert not window.env.project.is_dirty, 'a fresh project starts clean'
        print('new-project flow ok')

        # --- closeEvent publishes the exit dialog while dirty ---
        window.env.project.mark_dirty()
        answers = iter([QMessageBox.StandardButton.Cancel])
        QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
        try:
            window.close()
            assert window.isVisible(), 'canceling the exit dialog keeps the window open'
        finally:
            QMessageBox.question = original_question

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'exit.ecproj'
            window.env.project.path = str(archive)
            script = window.env.project.scripts[0]
            script.path = Path(tmp) / 'main.ecscript'
            script.mark_dirty()
            # Exit dialog chooses Save, then the per-script dialog chooses Save too
            answers = iter([QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Save])
            QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
            try:
                window.close()
            finally:
                QMessageBox.question = original_question
            assert not window.isVisible(), 'saving succeeds and the window closes'
            assert archive.exists(), 'the exit save persists the archive'

        window.show()
        window.env.project.mark_dirty()
        answers = iter([QMessageBox.StandardButton.Discard])
        QMessageBox.question = staticmethod(lambda *args, **kwargs: next(answers))
        try:
            window.close()
            assert not window.isVisible(), 'discarding closes without saving'
        finally:
            QMessageBox.question = original_question
        print('exit dialog ok')

        window.env.project.clear_dirty()  # The discard above kept the dirt: settle it
        window.close()
    finally:
        QMessageBox.question = original_question
        QFileDialog.getSaveFileName = original_save_file
        NewProjectDialog.exec = original_exec

    print('ALL PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
