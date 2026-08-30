# -*- coding: utf-8 -*-
"""
Headless check of ``kits.fluent.model`` (the model-specific DEFINE_* macro
components) and of the identifier label the macro components carry:

- the fifteen model macro components register at the Domain level, support UDF
  natively, and contribute their completion keywords;
- compilation emits the exact macro headers (argument lists verified against
  the Ansys Fluent UDF guide), nested components included; ``DEFINE_SOURCE``
  auto-names the derivative array and the returned value, closes the body
  with ``return`` of the value when the body does not end with one already,
  and hosts the three source statements ("set source const", "set source
  diff", "end DEFINE_SOURCE") that compile inside its body only;
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
        # Wide like a real whole-page canvas: a ten-argument macro header
        # (DEFINE_CAVITATION_RATE) keeps its single line only on a page-width row
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
MACROS = (('profile', 'DEFINE_PROFILE', 2),
          ('source', 'DEFINE_SOURCE', 2),
          ('property', 'DEFINE_PROPERTY', 2),
          ('diffusivity', 'DEFINE_DIFFUSIVITY', 3),
          ('turbulent_viscosity', 'DEFINE_TURBULENT_VISCOSITY', 2),
          ('prandtl', 'DEFINE_PRANDTL', 2),
          ('turb_schmidt', 'DEFINE_TURB_SCHMIDT', 3),
          ('specific_heat', 'DEFINE_SPECIFIC_HEAT', 4),
          ('heat_flux', 'DEFINE_HEAT_FLUX', 6),
          ('vr_rate', 'DEFINE_VR_RATE', 7),
          ('sr_rate', 'DEFINE_SR_RATE', 6),
          ('cavitation_rate', 'DEFINE_CAVITATION_RATE', 10),
          ('nox_rate', 'DEFINE_NOX_RATE', 5),
          ('sox_rate', 'DEFINE_SOX_RATE', 5),
          ('cphi', 'DEFINE_CPHI', 2))


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
    profile = env.kit_manager.lookup('fluent.profile').component_type(null, graphics)
    profile.interface.paint(graphics, painting=False)
    geoms = geometries(profile.interface)
    for widget in (profile.interface.edit_name, *profile.interface.arg_labels,
                   *profile.interface.arg_edits):
        assert same_row(geoms[profile.interface.label_macro], geoms[widget]), \
            f'profile: {widget.objectName()} must stay on the header row when it fits'
    assert not same_row(geoms[profile.interface.label_macro], geoms[profile.interface.label_brief]), \
        'profile: the brief caption must sit on its own row'
    print('header layout width ok')

    # 5. A narrow container wraps the argument pairs below the name edit:
    #    nothing spills past the right edge, the name edit keeps its minimum
    #    width, and no identifier edit is stranded away from its label
    narrow = _GraphicsStub(canvas, QRectF(0, 0, 900, 800))
    cav_narrow = env.kit_manager.lookup('fluent.cavitation_rate').component_type(null, narrow)
    cav_narrow.interface.paint(narrow, painting=False)
    size = cav_narrow.interface.layout.size(narrow)
    assert size.width() <= narrow.client_rect.width(), size.width()
    geoms = geometries(cav_narrow.interface)
    assert geoms[cav_narrow.interface.edit_name].width() >= cav_narrow.interface.edit_name.width(), \
        geoms[cav_narrow.interface.edit_name].width()
    assert same_row(geoms[cav_narrow.interface.edit_name], geoms[cav_narrow.interface.arg_labels[0]]), \
        'the first argument pair should still fit beside the name edit'
    assert not same_row(geoms[cav_narrow.interface.edit_name], geoms[cav_narrow.interface.arg_labels[-1]]), \
        'the last argument pair must wrap below the name edit'
    for label, edit in zip(cav_narrow.interface.arg_labels, cav_narrow.interface.arg_edits):
        assert same_row(geoms[label], geoms[edit]), \
            f'{label.text()}: an identifier edit must never part from its label'
    print('narrow container wrapping ok')

    # 6. The macros render their exact headers and bodies
    cases = (('profile', 'inlet_vel', 'begin_f_loop(f, t) { F_PROFILE(f, t, i) = 1.0; } end_f_loop(f, t)',
              'DEFINE_PROFILE(inlet_vel, t, i)\n'
              '{\n'
              '    begin_f_loop(f, t) { F_PROFILE(f, t, i) = 1.0; } end_f_loop(f, t)\n'
              '}'),
             ('source', 'energy_src', 'Message("source");',
              'DEFINE_SOURCE(energy_src, c, t, dS, eqn)\n'
              '{\n'
              '    real source = 0.;\n'
              '    Message("source");\n'
              '    return source;\n'
              '}'),
             ('specific_heat', 'my_cp', '*h = 2000. * (T - Tref);\nreturn 2000.;',
              'DEFINE_SPECIFIC_HEAT(my_cp, T, Tref, h, yi)\n'
              '{\n'
              '    *h = 2000. * (T - Tref);\n'
              '    return 2000.;\n'
              '}'),
             ('heat_flux', 'wall_flux', 'cir[0] = 1.0;',
              'DEFINE_HEAT_FLUX(wall_flux, f, t, c0, t0, cid, cir)\n'
              '{\n'
              '    cir[0] = 1.0;\n'
              '}'),
             ('vr_rate', 'vol_rate', '*rr = 0.1;\n*rr_t = *rr;',
              'DEFINE_VR_RATE(vol_rate, c, t, r, mw, yi, rr, rr_t)\n'
              '{\n'
              '    *rr = 0.1;\n'
              '    *rr_t = *rr;\n'
              '}'),
             ('sr_rate', 'surf_rate', '*rr = 0.2;',
              'DEFINE_SR_RATE(surf_rate, f, t, r, mw, yi, rr)\n'
              '{\n'
              '    *rr = 0.2;\n'
              '}'),
             ('cavitation_rate', 'c_rate', '*m_dot = 0.0;',
              'DEFINE_CAVITATION_RATE(c_rate, c, t, p, rhoV, rhoL, mafV, p_v, cigma, f_gas, m_dot)\n'
              '{\n'
              '    *m_dot = 0.0;\n'
              '}'),
             ('nox_rate', 'user_nox', 'POLLUT_FRATE(Pollut) = 0.0;',
              'DEFINE_NOX_RATE(user_nox, c, t, Pollut, Pollut_Par, NOx)\n'
              '{\n'
              '    POLLUT_FRATE(Pollut) = 0.0;\n'
              '}'),
             ('sox_rate', 'user_sox', 'POLLUT_RRATE(Pollut) = 0.0;',
              'DEFINE_SOX_RATE(user_sox, c, t, Pollut, Pollut_Par, SOx)\n'
              '{\n'
              '    POLLUT_RRATE(Pollut) = 0.0;\n'
              '}'),
             ('cphi', 'user_cphi', 'return 2.0;',
              'DEFINE_CPHI(user_cphi, c, t)\n'
              '{\n'
              '    return 2.0;\n'
              '}'))
    for name, func_name, body_text, expected in cases:
        comp = env.kit_manager.lookup(f'fluent.{name}').component_type(null, graphics)
        comp.interface.edit_name.setText(func_name)
        comp.interface.edit_body.setPlainText(body_text)
        comp.build(compiler)
        assert compiler.products[UDF.id][-1] == expected, (name, compiler.products[UDF.id][-1])
    print('macro compiles ok')

    # 6b. DEFINE_SOURCE keeps the cell and the thread alone in the interface:
    #     the derivative array and the returned value are auto-named by the
    #     compilation, and the body hosts the three source statements
    from kits.fluent.general import _macro_parameters
    src = env.kit_manager.lookup('fluent.source').component_type(null, graphics)
    assert len(src.interface.arg_edits) == 2, 'the derivative and the value must stay out of the interface'
    assert not hasattr(src.interface, 'edit_result'), 'the source returns through the body statements'
    src.interface.edit_name.setText('energy_src')
    keywords = [completion.keyword for completion in _macro_parameters(src)]
    assert keywords == ['c', 't'], keywords
    # The three statements insert through completion entries (the analyzer
    # gates them in real editions; the entries resolve like any component)
    body = src.interface.edit_body
    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    const_comp = body.insert_component(VisualCodeEdit.CompletionEntry('set_source_const', 'fluent.set_source_const'))
    assert const_comp is not null, 'insert_component(set_source_const) failed'
    const_comp.interface.edit_value.setPlainText('1.0e5')
    body.insertPlainText('\n')
    diff_comp = body.insert_component(VisualCodeEdit.CompletionEntry('set_source_diff', 'fluent.set_source_diff'))
    assert diff_comp is not null, 'insert_component(set_source_diff) failed'
    diff_comp.interface.edit_derivative.setPlainText('0.0')
    body.insertPlainText('\n')
    end_comp = body.insert_component(VisualCodeEdit.CompletionEntry('end_source', 'fluent.end_source'))
    assert end_comp is not null, 'insert_component(end_source) failed'
    src.build(compiler)
    src_expected = ('DEFINE_SOURCE(energy_src, c, t, dS, eqn)\n'
                    '{\n'
                    '    real source = 0.;\n'
                    '    source = 1.0e5;\n'
                    '    dS[eqn] = 0.0;\n'
                    '    return source;\n'
                    '}')
    assert compiler.products[UDF.id][-1] == src_expected, compiler.products[UDF.id][-1]
    # The statements refuse to compile outside a DEFINE_SOURCE body
    lonely = Compiler(BuildConfig(UDF))
    try:
        const_comp.build(lonely)
        raise AssertionError('set_source_const must reject a contextless position')
    except Compiler.CompileError:
        pass
    # Legacy four-argument archives restore by keeping the leading identifiers
    legacy = serialize(src)
    legacy['args'] = ['c', 't', 'dS', 'eqn']
    env.kit_manager.lookup('fluent.source').component_type.restore(legacy, null, graphics)
    # Legacy archives carrying a result field migrate it into the body as
    # "set source const" followed by "end DEFINE_SOURCE"
    migrated = env.kit_manager.lookup('fluent.source').component_type.restore(
        {'name': 'legacy_src', 'args': ['c', 't'],
         'body': {'text': '', 'components': []},
         'result': {'text': '2.5', 'components': []}}, null, graphics)
    migrated.build(compiler)
    migrated_expected = ('DEFINE_SOURCE(legacy_src, c, t, dS, eqn)\n'
                         '{\n'
                         '    real source = 0.;\n'
                         '    source = 2.5;\n'
                         '    return source;\n'
                         '}')
    assert compiler.products[UDF.id][-1] == migrated_expected, compiler.products[UDF.id][-1]
    print('source auto-naming and source statements ok')

    # 7. DEFINE_PROPERTY returns through the body statements like DEFINE_SOURCE:
    #    "set property" stores the value the compilation names, "end
    #    DEFINE_PROPERTY" returns it
    prop = env.kit_manager.lookup('fluent.property').component_type(null, graphics)
    assert not hasattr(prop.interface, 'edit_result'), 'the property returns through the body statements'
    prop.interface.edit_name.setText('my_density')
    body = prop.interface.edit_body
    body.setPlainText('real rho = 1.225;')
    cursor = body.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    body.setTextCursor(cursor)
    body.insertPlainText('\n')
    assign = body.insert_component(body._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setText('rho')
    assign.interface.edit_value.setPlainText('1000.0')
    assign.interface.check_local.setChecked(True)  # Declared by the free text above
    body.insertPlainText('\n')
    set_prop = body.insert_component(VisualCodeEdit.CompletionEntry('set_property', 'fluent.set_property'))
    assert set_prop is not null, 'insert_component(set_property) failed'
    set_prop.interface.edit_value.setPlainText('rho')
    body.insertPlainText('\n')
    end_prop = body.insert_component(VisualCodeEdit.CompletionEntry('end_property', 'fluent.end_property'))
    assert end_prop is not null, 'insert_component(end_property) failed'
    prop.build(compiler)
    prop_expected = ('DEFINE_PROPERTY(my_density, c, t)\n'
                     '{\n'
                     '    real property = 0.;\n'
                     '    real rho = 1.225;\n'
                     '    rho = 1000.0;\n'
                     '    property = rho;\n'
                     '    return property;\n'
                     '}')
    assert compiler.products[UDF.id][-1] == prop_expected, compiler.products[UDF.id][-1]
    # The statements refuse to compile outside a DEFINE_PROPERTY body
    lonely = Compiler(BuildConfig(UDF))
    try:
        set_prop.build(lonely)
        raise AssertionError('set_property must reject a contextless position')
    except Compiler.CompileError:
        pass
    # Legacy archives carrying a result field migrate it into the body as
    # "set property" followed by "end DEFINE_PROPERTY"
    migrated = env.kit_manager.lookup('fluent.property').component_type.restore(
        {'name': 'legacy_prop', 'args': ['c', 't'],
         'body': {'text': '', 'components': []},
         'result': {'text': '998.2', 'components': []}}, null, graphics)
    migrated.build(compiler)
    migrated_expected = ('DEFINE_PROPERTY(legacy_prop, c, t)\n'
                         '{\n'
                         '    real property = 0.;\n'
                         '    property = 998.2;\n'
                         '    return property;\n'
                         '}')
    assert compiler.products[UDF.id][-1] == migrated_expected, compiler.products[UDF.id][-1]
    print('macro with nested component compile ok:')
    print(prop_expected)

    # 8. Serialization round-trip through restore (the richest argument list)
    cav = env.kit_manager.lookup('fluent.cavitation_rate').component_type(null, graphics)
    cav.interface.edit_name.setText('c_rate')
    cav.interface.edit_body.setPlainText('*m_dot = 0.0;')
    data = serialize(cav)
    restored = env.kit_manager.lookup('fluent.cavitation_rate').component_type.restore(data, null, graphics)
    assert serialize(restored) == data, 'round-trip serialization mismatch'
    restored.build(compiler)
    assert compiler.products[UDF.id][-1] == cases[6][3], compiler.products[UDF.id][-1]
    print('serialization round-trip ok')

    # 9. Level filter: statement contexts reject the macros; Domain accepts them
    stmt_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    stmt_edit.filter(ComponentMetadata.Level.Statement)
    profile_entry = next(entry for entry in stmt_edit.completions if entry.keyword == 'profile')
    assert not stmt_edit._entry_participates(profile_entry), \
        'Domain-level macro must not complete in statement contexts'
    domain_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    domain_edit.filter(ComponentMetadata.Level.Domain)
    profile_entry = next(entry for entry in domain_edit.completions if entry.keyword == 'profile')
    assert domain_edit._entry_participates(profile_entry), \
        'Domain-level macro must complete in Domain contexts'
    print('level filter ok')

    # 10. Focus and navigation order (identifier edit first, then arguments, then body)
    assert cav.autoFocusWidget() is cav.interface.edit_name
    assert cav.editableWidgets() == [cav.interface.edit_name, *cav.interface.arg_edits,
                                     cav.interface.edit_body]
    print('focus and navigation ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
