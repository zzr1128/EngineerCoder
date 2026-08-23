# -*- coding: utf-8 -*-
"""
Headless check of the building pipeline:

- importing kits registers their languages in the environment;
- ``Environment.build`` compiles every script of the loaded project and
  writes the compilation products to files (explicit and default output),
  returning the artifacts together with the build warnings;
- the generated artifacts contain the UDF source rendered from the root
  component tree, including components nested inside visual code edits.
"""

import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.build import BuildConfig
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.project import Project
from core.script import Script
from interface.visual_code_edit import VisualCodeEdit
from kits.fluent.fluent import UDF
from path import BASE_DIR


class _CanvasStub(QWidget):
    """Stands in for the canvas: the nearest ancestor providing ``add_interface``."""

    def __init__(self):
        super().__init__()
        self.interfaces: IList[Any] = []

    def add_interface(self, component: Any, right_occupation: float = 0.) -> void:
        self.interfaces.append(component)

    def remove_interface(self, component: Any) -> void:
        if component in self.interfaces:
            self.interfaces.remove(component)


def _noop(*args, **kwargs):
    maybe_unused(args, kwargs)
    return None


class _GraphicsStub(IComponentGraphics):
    """Minimal graphics implementation sufficient for headless construction."""

    def __init__(self, canvas: _CanvasStub):
        self.canvas = canvas

    def create_visual_code_edit(self, rect) -> VisualCodeEdit:
        return VisualCodeEdit(self.canvas, self)

    def create_hypertext_edit(self, rect) -> HyperTextEdit:
        return HyperTextEdit(self.canvas)

    def create_lineedit(self, rect) -> QLineEdit:
        edit = QLineEdit(self.canvas)
        edit.setFixedSize(int(rect.width()), int(rect.height()))
        return edit

    def create_checkbox(self, text: string, font) -> QCheckBox:
        box = QCheckBox(text, self.canvas)
        box.setFont(font)
        hint = box.sizeHint()
        box.setFixedSize(hint.width(), hint.height())
        return box

    def create_combobox(self, rect) -> QComboBox:
        box = QComboBox(self.canvas)
        box.setFixedSize(int(rect.width()), int(rect.height()))
        return box

    def create_native_label(self, text: string, font) -> QLabel:
        return QLabel(text, self.canvas)

    def label_metric_width(self, label: QLabel, *, modify: bool = False) -> int:
        return 40

    def alloc_color(self) -> QColor:
        return QColor('#4488CC')

    @property
    def client_rect(self) -> QRectF:
        return QRectF(0, 0, 600, 400)

    def add_interface(self, component: Any, right_occupation: float = 0.) -> void:
        self.canvas.add_interface(component, right_occupation)

    def remove_interface(self, component: Any) -> void:
        self.canvas.remove_interface(component)


# Everything else of IComponentGraphics is irrelevant for this check
for _name in dir(IComponentGraphics):
    if not _name.startswith('_') and callable(getattr(IComponentGraphics, _name)) \
            and _name not in vars(_GraphicsStub):
        setattr(_GraphicsStub, _name, staticmethod(_noop))


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    # 0. Building without a loaded project is refused
    try:
        env.build()
        raise AssertionError('building without a project should fail')
    except ValueError as e:
        print(f'no-project rejection ok: {e}')

    # 1. Importing kits registers their languages in the environment
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    assert UDF in env.languages, 'importing the fluent kit should register UDF'
    print('language registration ok:', env.languages)

    # 2. A script whose root is a branch with a nested assignment component
    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    branch = env.kit_manager.lookup('clk.br').component_type(null, graphics)
    branch.interface.edit_cond.setPlainText('x > 0.0')
    edit_then = branch.interface.edit_then
    assign = edit_then.insert_component(edit_then._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('velocity')
    assign.interface.edit_value.setPlainText('1.5')
    assign.interface.check_constant.setChecked(True)
    cursor = edit_then.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    edit_then.setTextCursor(cursor)
    edit_then.insertPlainText('\nMessage("done");')

    project = Project('check', UDF)
    project.scripts.append(Script(branch))
    env.project = project

    # 3. Explicit output directory: env.build produces main.c (unsaved script
    #    falls back to the 'main' basename; UDF artifacts use the C extension)
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)
        artifacts, warnings = env.build(BuildConfig(UDF, output=output))
        assert artifacts == [output / 'main.c'], artifacts
        assert warnings == [], [str(warning) for warning in warnings]
        source = artifacts[0].read_text(encoding='utf-8')
        expected = ('if (x > 0.0) {\n'
                    '    const real velocity = 1.5;\n'
                    '    Message("done");\n'
                    '}')
        assert source == expected, source
        print('explicit-output build ok:')
        print(source)

    # 4. Default configuration: the project's target language is used and the
    #    artifacts of an unsaved project land in <workspace>/build/<project>
    artifacts, warnings = env.build()
    default_dir = BASE_DIR / 'build' / 'check'
    assert artifacts == [default_dir / 'main.c'], artifacts
    assert warnings == [], [str(warning) for warning in warnings]
    assert artifacts[0].is_file()
    print(f'default build ok: {artifacts[0]}')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
