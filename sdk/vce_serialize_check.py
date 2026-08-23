# -*- coding: utf-8 -*-
"""
Headless check of the serialization convention:

- pure-data archiving through ``__serialize__`` (generic ``serialize``);
- UI-context-aware restoration through ``restore``/``load`` for components,
  visual code edits, scripts and projects.
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# The archived texts carry U+FFFC placeholders: keep stdout UTF-8 even when
# redirected, so the round-trip prints never hit the console code page
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.component import Component, ComponentMetadata, IComponentInterface
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.meta import SupportedLanguage
from core.project import Project
from core.script import Script
from interface.visual_code_edit import VisualCodeEdit
from kits.common.branch import CBranch


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
    return None


class _GraphicsStub(IComponentGraphics):
    """Minimal graphics implementation sufficient for headless restoration."""

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


class _MockInterface(IComponentInterface):
    def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:
        pass


@Component.use__interface
@ComponentMetadata.create('mock', 'Mock', 'Mock component for serialization checks', [])
class _MockComponent(Component):
    def __init__(self, parent: Nullable[Component], graphics: IComponentGraphics):
        super().__init__(parent, graphics)
        self.payload: string = ''
        self._interface = _MockInterface(graphics)

    def __serialize__(self) -> IDictionary[string, Any]:
        return {'payload': self.payload}

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable[Component],
                graphics: IComponentGraphics) -> '_MockComponent':
        require_member(data, 'payload')
        component = cls(parent, graphics)
        component.payload = data['payload']
        return component


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()
    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.kit_manager['clk'].register(_MockComponent)

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)

    # 1. Plain text round trip
    edit = VisualCodeEdit(canvas, graphics)
    edit.setPlainText('hello world')
    data = serialize(edit)
    assert data == {'text': 'hello world', 'components': []}, data
    assert serialize(VisualCodeEdit.restore(data, graphics, canvas)) == data
    print('plain text round trip ok:', data)

    # 2. Placeholder/component count mismatch is rejected
    try:
        VisualCodeEdit.restore({'text': 'a\uFFFC', 'components': []}, graphics, canvas)
        raise AssertionError('mismatching archive was accepted')
    except SerializationError:
        print('mismatch rejection ok')

    # 3. Mock component round trip through insert -> serialize -> restore
    edit = VisualCodeEdit(canvas, graphics)
    edit.setPlainText('pre  post')
    cursor = edit.textCursor()
    cursor.setPosition(4)
    edit.setTextCursor(cursor)
    edit.add_completion('mk', 'clk.mock')
    component = edit.insert_component(edit.completions[-1])
    assert component is not null, 'insert_component failed'
    component.payload = 'state42'
    data = serialize(edit)
    assert data['text'] == 'pre \uFFFC post', data
    assert data['components'][0]['name'] == 'clk.mock', data
    assert serialize(VisualCodeEdit.restore(data, graphics, canvas)) == data
    print('mock component round trip ok:', data)

    # 4. Branch component with nested visual code edits
    edit = VisualCodeEdit(canvas, graphics)
    branch = edit.insert_branch()
    assert branch is not null, 'insert_branch failed'
    branch.interface.edit_cond.setPlainText('x > 0')
    branch.interface.edit_then.setPlainText('print(1)')
    data = serialize(edit)
    assert data['components'][0]['name'] == 'clk.br', data
    restored = VisualCodeEdit.restore(data, graphics, canvas)
    assert serialize(restored) == data
    restored_branch = restored.inserted_components[0]
    assert restored_branch.interface.edit_cond.toPlainText() == 'x > 0'
    assert restored_branch.interface.edit_then.toPlainText() == 'print(1)'
    print('branch round trip ok')

    # 5. Loop and count loop components with nested visual code edits
    edit = VisualCodeEdit(canvas, graphics)
    loop = edit.insert_component(edit._lookup_entry('loop'))
    assert loop is not null, 'insert_component(loop) failed'
    loop.interface.edit_cond.setPlainText('x < 10')
    loop.interface.edit_body.setPlainText('x = x + 1')
    data = serialize(edit)
    assert data['components'][0]['name'] == 'clk.loop', data
    restored = VisualCodeEdit.restore(data, graphics, canvas)
    assert serialize(restored) == data
    restored_loop = restored.inserted_components[0]
    assert restored_loop.interface.edit_cond.toPlainText() == 'x < 10'
    assert restored_loop.interface.edit_body.toPlainText() == 'x = x + 1'
    print('loop round trip ok')

    edit = VisualCodeEdit(canvas, graphics)
    count_loop = edit.insert_component(edit._lookup_entry('for'))
    assert count_loop is not null, 'insert_component(for) failed'
    count_loop.interface.edit_count.setPlainText('3')
    count_loop.interface.edit_counter.setText('idx')
    count_loop.interface.edit_body.setPlainText('print(1)')
    data = serialize(edit)
    assert data['components'][0]['name'] == 'clk.for', data
    restored = VisualCodeEdit.restore(data, graphics, canvas)
    assert serialize(restored) == data
    restored_for = restored.inserted_components[0]
    assert restored_for.interface.edit_count.toPlainText() == '3'
    assert restored_for.interface.edit_counter.text() == 'idx'
    assert restored_for.interface.edit_body.toPlainText() == 'print(1)'
    print('count loop round trip ok')

    # 6. Native component: plain-text archive without nested components
    edit = VisualCodeEdit(canvas, graphics)
    native = edit.insert_component(edit._lookup_entry('native'))
    assert native is not null, 'insert_component(native) failed'
    native.interface.edit_code.setPlainText('x = 1\nprint(x)')
    data = serialize(edit)
    assert data['components'][0]['name'] == 'clk.native', data
    assert data['components'][0]['data'] == {'code': 'x = 1\nprint(x)'}, data
    restored = VisualCodeEdit.restore(data, graphics, canvas)
    assert serialize(restored) == data
    assert restored.inserted_components[0].interface.edit_code.toPlainText() == 'x = 1\nprint(x)'
    print('native round trip ok')

    # 7. Assignment component: target archives as an edit (member accesses may
    #    embed), value is a visual-code edit, check boxes plus the type field
    edit = VisualCodeEdit(canvas, graphics)
    assign = edit.insert_component(edit._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('x')
    assign.interface.edit_value.setPlainText('1 + 2')
    assign.interface.check_constant.setChecked(True)
    data = serialize(edit)
    assert data['components'][0]['name'] == 'clk.assign', data
    assert data['components'][0]['data'] == {'name': {'text': 'x', 'components': []},
                                             'value': {'text': '1 + 2', 'components': []},
                                             'constant': True,
                                             'local_only': False,
                                             'type': ''}, data
    restored = VisualCodeEdit.restore(data, graphics, canvas)
    assert serialize(restored) == data
    restored_assign = restored.inserted_components[0]
    assert restored_assign.interface.edit_name.toPlainText() == 'x'
    assert restored_assign.interface.edit_value.toPlainText() == '1 + 2'
    assert restored_assign.interface.check_constant.isChecked()
    assert not restored_assign.interface.check_local.isChecked()

    # The local-only annotation round-trips; legacy annotations invert into it
    # (``visibility: auto`` lifted the declaration, so it stays unchecked) and
    # archives predating every annotation restore as local only
    assign.interface.check_local.setChecked(True)
    data = serialize(edit)
    assert data['components'][0]['data']['local_only'] is True, data
    assert serialize(VisualCodeEdit.restore(data, graphics, canvas)) == data
    assign.interface.check_local.setChecked(False)
    legacy = {'name': 'x', 'value': {'text': '1 + 2', 'components': []}, 'constant': True}
    legacy_assign = env.kit_manager.lookup('clk.assign').component_type.restore(legacy, null, graphics)
    assert legacy_assign.interface.check_local.isChecked(), 'pre-annotation archives stayed local'
    assert legacy_assign.interface.edit_name.toPlainText() == 'x'
    legacy['visibility'] = 'auto'
    assert not env.kit_manager.lookup('clk.assign').component_type.restore(
        legacy, null, graphics).interface.check_local.isChecked(), 'legacy auto stays lifted'
    legacy['visibility'] = 'local'
    assert env.kit_manager.lookup('clk.assign').component_type.restore(
        legacy, null, graphics).interface.check_local.isChecked(), 'legacy local restricts'
    print('assign round trip ok')

    # 8. Binary operator components: two operand edits around the symbol
    for keyword, full_name in (('plus', 'clk.plus'), ('minus', 'clk.minus'),
                               ('multiply', 'clk.multiply'), ('divide', 'clk.divide'),
                               ('modulus', 'clk.modulus'), ('greater', 'clk.greater'),
                               ('less', 'clk.less'), ('greater_equal', 'clk.greater_equal'),
                               ('less_equal', 'clk.less_equal'), ('equal', 'clk.equal'),
                               ('not_equal', 'clk.not_equal')):
        edit = VisualCodeEdit(canvas, graphics)
        op = edit.insert_component(edit._lookup_entry(keyword))
        assert op is not null, f'insert_component({keyword}) failed'
        op.interface.edit_left.setPlainText('a')
        op.interface.edit_right.setPlainText('b')
        data = serialize(edit)
        assert data['components'][0]['name'] == full_name, data
        assert data['components'][0]['data'] == {'left': {'text': 'a', 'components': []},
                                                 'right': {'text': 'b', 'components': []}}, data
        restored = VisualCodeEdit.restore(data, graphics, canvas)
        assert serialize(restored) == data
        restored_op = restored.inserted_components[0]
        assert restored_op.interface.edit_left.toPlainText() == 'a'
        assert restored_op.interface.edit_right.toPlainText() == 'b'
    # Archives made before the operands existed restore with both operands blank
    legacy_op = env.kit_manager.lookup('clk.plus').component_type.restore({}, null, graphics)
    assert legacy_op.interface.edit_left.toPlainText() == ''
    assert legacy_op.interface.edit_right.toPlainText() == ''
    print('operator round trip ok')

    # 9. Field (member access) component: two plain-text names
    edit = VisualCodeEdit(canvas, graphics)
    field = edit.insert_component(edit._lookup_entry('member'))
    assert field is not null, 'insert_component(member) failed'
    field.interface.edit_owner.setPlainText('point')
    field.interface.edit_member.setPlainText('x')
    data = serialize(edit)
    assert data['components'][0]['name'] == 'clk.field', data
    assert data['components'][0]['data'] == {'owner': 'point', 'member': 'x'}, data
    restored = VisualCodeEdit.restore(data, graphics, canvas)
    assert serialize(restored) == data
    restored_field = restored.inserted_components[0]
    assert restored_field.interface.edit_owner.toPlainText() == 'point'
    assert restored_field.interface.edit_member.toPlainText() == 'x'
    print('field round trip ok')

    # 10. Script and Project restoration (context flows in through restore)
    script = Script(CBranch(null, graphics))
    script.path = Path('test.ecs')
    sdata = serialize(script)
    assert sdata['component']['name'] == 'clk.br', sdata
    assert serialize(Script.restore(sdata, env.kit_manager, graphics)) == sdata
    print('script round trip ok')

    project = Project('demo', SupportedLanguage('Python', 'py', null))
    project.scripts = [script]
    pdata = serialize(project)
    assert serialize(Project.restore(pdata, env.kit_manager, graphics)) == pdata
    print('project round trip ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
