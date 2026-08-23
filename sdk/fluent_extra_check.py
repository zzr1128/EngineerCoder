# -*- coding: utf-8 -*-
"""
Headless check of the DPM, dynamic mesh and DO radiation DEFINE_* macro
components (``kits.fluent.dpm``/``kits.fluent.dynm``/``kits.fluent.do``) and
of the identifier label the macro components carry:

- the ten macro components register at the Domain level, support UDF natively,
  and contribute their completion keywords;
- compilation emits the exact macro headers (argument lists verified against
  the Ansys Fluent UDF guide), nested components included;
- the serialization round-trip through ``restore`` preserves the contents;
- every macro interface captions the function name field with the localized
  identifier label, which sits in the header row right before the name edit,
  and carries the brief plain-language caption of the macro;
- the layout never exceeds the container width: a wide container keeps the
  header on one row, a narrow one wraps the argument pairs below the name
  edit without ever stranding a label from its identifier edit.
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.build import BuildConfig, Compiler
from core.component import ComponentMetadata
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from interface.visual_code_edit import VisualCodeEdit
# Imported before Environment(): the kit modules register their completion
# keywords on the kit manager singleton, which Environment() must not wipe
from kits.fluent.fluent import UDF


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

    def __init__(self, canvas: _CanvasStub, rect: QRectF = QRectF(0, 0, 2000, 800)):
        self.canvas = canvas
        self.rect = rect

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
        if modify:
            label.setFixedWidth(40)
        return 40

    def alloc_color(self) -> QColor:
        return QColor('#4488CC')

    @property
    def client_rect(self) -> QRectF:
        # Wide like a real whole-page canvas: an eight-argument macro header
        # (DEFINE_DOM_SOURCE) keeps its single line only on a page-width row
        return self.rect

    def add_interface(self, component: Any, right_occupation: float = 0.) -> void:
        self.canvas.add_interface(component, right_occupation)

    def remove_interface(self, component: Any) -> void:
        self.canvas.remove_interface(component)


# Everything else of IComponentGraphics is irrelevant for this check
for _name in dir(IComponentGraphics):
    if not _name.startswith('_') and callable(getattr(IComponentGraphics, _name)) \
            and _name not in vars(_GraphicsStub):
        setattr(_GraphicsStub, _name, staticmethod(_noop))


# (component name, emitted macro, parameter count)
MACROS = (('dpm_injection_init', 'DEFINE_DPM_INJECTION_INIT', 1),
          ('dpm_law', 'DEFINE_DPM_LAW', 2),
          ('dpm_drag', 'DEFINE_DPM_DRAG', 2),
          ('dpm_body_force', 'DEFINE_DPM_BODY_FORCE', 4),
          ('dpm_source', 'DEFINE_DPM_SOURCE', 5),
          ('dpm_bc', 'DEFINE_DPM_BC', 5),
          ('grid_motion', 'DEFINE_GRID_MOTION', 4),
          ('cg_motion', 'DEFINE_CG_MOTION', 5),
          ('dom_source', 'DEFINE_DOM_SOURCE', 8),
          ('emissivity_weighting_factor', 'DEFINE_EMISSIVITY_WEIGHTING_FACTOR', 5))


def same_row(a: QRectF, b: QRectF) -> bool:
    """Whether two element geometries lie on the same layout row (their
    vertically-centered extents overlap)."""
    return a.y() < b.y() + b.height() and b.y() < a.y() + a.height()


def geometries(interface: Any) -> IDictionary[Any, QRectF]:
    return {element.widget: geometry for element, geometry
            in zip(interface.layout.elements, interface.layout._geometries)}


def main() -> void:
    app = QApplication(sys.argv)
    env = Environment()

    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))

    from kits.fluent.localization import _  # After Environment(): reads the local language

    # 1. Registration: Domain-level components supporting UDF natively
    for name, macro, nargs in MACROS:
        meta = env.kit_manager.lookup(f'fluent.{name}')
        assert meta.level == ComponentMetadata.Level.Domain, (name, meta.level)
        assert UDF in meta.languages, f'fluent.{name} should support UDF natively'
        assert meta.description, f'fluent.{name} has no description'
        comp_type = meta.component_type
        assert len(comp_type.args_spec) == nargs, (name, comp_type.args_spec)
        assert comp_type.macro == macro, (name, comp_type.macro)
    print('registration ok')

    # 2. The completion keywords survived the Environment construction
    for name, _macro, _nargs in MACROS:
        comp_type = env.kit_manager.lookup(f'fluent.{name}').component_type
        assert env.kit_manager.completions.get(comp_type.completion_keyword) == f'fluent.{name}', \
            (comp_type.completion_keyword, env.kit_manager.completions.get(comp_type.completion_keyword))
    print('completion registry ok')

    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    compiler = Compiler(BuildConfig(UDF))

    # 3. Every macro captions its name field with the identifier label,
    #    located in the header row right before the name edit, and carries
    #    the brief caption (the localized description minus the macro prefix)
    lt_name = _('label_name')
    for name, _macro, _nargs in MACROS:
        meta = env.kit_manager.lookup(f'fluent.{name}')
        comp = meta.component_type(null, graphics)
        assert comp.interface.label_name.text() == lt_name, (name, comp.interface.label_name.text())
        widgets = [element.widget for element in comp.interface.layout.elements]
        assert widgets.index(comp.interface.label_name) + 1 == widgets.index(comp.interface.edit_name), \
            f'{name}: identifier label must sit right before the name edit'
        brief = meta.description
        for separator in ('：', ': '):
            if brief.startswith(_macro + separator):
                brief = brief[len(_macro) + len(separator):]
                break
        assert comp.interface.label_brief.text() == brief, (name, comp.interface.label_brief.text())
    print('identifier label and brief caption ok')

    # 4. The layout never exceeds the container width; on a wide container the
    #    whole header stays on one row
    for name, _macro, _nargs in MACROS:
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        comp.interface.paint(graphics, painting=False)
        size = comp.interface.layout.size(graphics)
        assert size.width() <= graphics.client_rect.width(), (name, size.width())
    dom = env.kit_manager.lookup('fluent.dom_source').component_type(null, graphics)
    dom.interface.paint(graphics, painting=False)
    geoms = geometries(dom.interface)
    for widget in (dom.interface.edit_name, *dom.interface.arg_labels,
                   *dom.interface.arg_edits):
        assert same_row(geoms[dom.interface.label_macro], geoms[widget]), \
            f'dom_source: {widget.objectName()} must stay on the header row when it fits'
    assert not same_row(geoms[dom.interface.label_macro], geoms[dom.interface.label_brief]), \
        'dom_source: the brief caption must sit on its own row'
    print('header layout width ok')

    # 5. A narrow container wraps the argument pairs below the name edit:
    #    nothing spills past the right edge, the name edit keeps its minimum
    #    width, and no identifier edit is stranded away from its label
    narrow = _GraphicsStub(canvas, QRectF(0, 0, 900, 800))
    dom_narrow = env.kit_manager.lookup('fluent.dom_source').component_type(null, narrow)
    dom_narrow.interface.paint(narrow, painting=False)
    size = dom_narrow.interface.layout.size(narrow)
    assert size.width() <= narrow.client_rect.width(), size.width()
    geoms = geometries(dom_narrow.interface)
    assert geoms[dom_narrow.interface.edit_name].width() >= dom_narrow.interface.edit_name.width(), \
        geoms[dom_narrow.interface.edit_name].width()
    assert same_row(geoms[dom_narrow.interface.edit_name], geoms[dom_narrow.interface.arg_labels[0]]), \
        'the first argument pair should still fit beside the name edit'
    assert not same_row(geoms[dom_narrow.interface.edit_name], geoms[dom_narrow.interface.arg_labels[-1]]), \
        'the last argument pair must wrap below the name edit'
    for label, edit in zip(dom_narrow.interface.arg_labels, dom_narrow.interface.arg_edits):
        assert same_row(geoms[label], geoms[edit]), \
            f'{label.text()}: an identifier edit must never part from its label'
    print('narrow container wrapping ok')

    # 6. The macros render their exact headers and bodies
    cases = (('dpm_injection_init', 'init_inj', 'I->flow_rate = 0.001;',
              'DEFINE_DPM_INJECTION_INIT(init_inj, I)\n'
              '{\n'
              '    I->flow_rate = 0.001;\n'
              '}'),
             ('dpm_law', 'user_law', 'P_DIAM(p) = 1.0e-5;',
              'DEFINE_DPM_LAW(user_law, p, ci)\n'
              '{\n'
              '    P_DIAM(p) = 1.0e-5;\n'
              '}'),
             ('dpm_drag', 'user_drag', 'return 1.0;',
              'DEFINE_DPM_DRAG(user_drag, p, Re)\n'
              '{\n'
              '    return 1.0;\n'
              '}'),
             ('dpm_body_force', 'user_force', 'F[0] = 0.0;\nFd[0] = 0.0;',
              'DEFINE_DPM_BODY_FORCE(user_force, p, mass, F, Fd)\n'
              '{\n'
              '    F[0] = 0.0;\n'
              '    Fd[0] = 0.0;\n'
              '}'),
             ('dpm_source', 'user_source', 'S[0][0] = 0.0;',
              'DEFINE_DPM_SOURCE(user_source, cell, thread, S, strength, p)\n'
              '{\n'
              '    S[0][0] = 0.0;\n'
              '}'),
             ('dpm_bc', 'user_bc', 'return PATH_ABORT;',
              'DEFINE_DPM_BC(user_bc, p, t, f, f_normal, dim)\n'
              '{\n'
              '    return PATH_ABORT;\n'
              '}'),
             ('grid_motion', 'zone_motion', 'NV_S(time, =, 0.0);',
              'DEFINE_GRID_MOTION(zone_motion, d, dt, time, dtime)\n'
              '{\n'
              '    NV_S(time, =, 0.0);\n'
              '}'),
             ('cg_motion', 'piston', 'cg_velocity[1] = 0.1;',
              'DEFINE_CG_MOTION(piston, dt, cg_velocity, cg_omega, time, dtime)\n'
              '{\n'
              '    cg_velocity[1] = 0.1;\n'
              '}'),
             ('dom_source', 'dom_src', '*emission = 0.0;\n*abs_coeff = 0.1;',
              'DEFINE_DOM_SOURCE(dom_src, c, t, s, xi, emission, in_scattering, abs_coeff, scat_coeff)\n'
              '{\n'
              '    *emission = 0.0;\n'
              '    *abs_coeff = 0.1;\n'
              '}'),
             ('emissivity_weighting_factor', 'gray_weight', '*weight = 0.5;',
              'DEFINE_EMISSIVITY_WEIGHTING_FACTOR(gray_weight, c, t, s, xi, weight)\n'
              '{\n'
              '    *weight = 0.5;\n'
              '}'))
    for name, func_name, body_text, expected in cases:
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        comp.interface.edit_name.setText(func_name)
        comp.interface.edit_body.setPlainText(body_text)
        comp.build(compiler)
        assert compiler.products[UDF.id][-1] == expected, (name, compiler.products[UDF.id][-1])
    print('macro compiles ok')

    # 7. DEFINE_DPM_DRAG whose body embeds a CLK assignment component
    drag = env.kit_manager.lookup('fluent.dpm_drag').component_type(null, graphics)
    drag.interface.edit_name.setText('scaled_drag')
    body = drag.interface.edit_body
    body.setPlainText('real factor = 1.5;')
    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')
    assign = body.insert_component(body._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setText('factor')
    assign.interface.edit_value.setPlainText('2.0')
    assign.interface.check_local.setChecked(True)  # Declared by the free text above
    drag.build(compiler)
    drag_expected = ('DEFINE_DPM_DRAG(scaled_drag, p, Re)\n'
                     '{\n'
                     '    real factor = 1.5;\n'
                     '    factor = 2.0;\n'
                     '}')
    assert compiler.products[UDF.id][-1] == drag_expected, compiler.products[UDF.id][-1]
    print('macro with nested component compile ok:')
    print(drag_expected)

    # 8. Serialization round-trip through restore (the richest argument list)
    dom = env.kit_manager.lookup('fluent.dom_source').component_type(null, graphics)
    dom.interface.edit_name.setText('dom_src')
    dom.interface.edit_body.setPlainText('*emission = 0.0;\n*abs_coeff = 0.1;')
    data = serialize(dom)
    restored = env.kit_manager.lookup('fluent.dom_source').component_type.restore(data, null, graphics)
    assert serialize(restored) == data, 'round-trip serialization mismatch'
    restored.build(compiler)
    assert compiler.products[UDF.id][-1] == cases[8][3], compiler.products[UDF.id][-1]
    print('serialization round-trip ok')

    # 9. Level filter: statement contexts reject the macros; Domain accepts them
    stmt_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    stmt_edit.filter(ComponentMetadata.Level.Statement)
    drag_entry = next(entry for entry in stmt_edit.completions if entry.keyword == 'dpm_drag')
    assert not stmt_edit._entry_participates(drag_entry), \
        'Domain-level macro must not complete in statement contexts'
    domain_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    domain_edit.filter(ComponentMetadata.Level.Domain)
    drag_entry = next(entry for entry in domain_edit.completions if entry.keyword == 'dpm_drag')
    assert domain_edit._entry_participates(drag_entry), \
        'Domain-level macro must complete in Domain contexts'
    print('level filter ok')

    # 10. Focus and navigation order (identifier edit first, then arguments, then body)
    assert dom.autoFocusWidget() is dom.interface.edit_name
    assert dom.editableWidgets() == [dom.interface.edit_name, *dom.interface.arg_edits,
                                     dom.interface.edit_body]
    print('focus and navigation ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
