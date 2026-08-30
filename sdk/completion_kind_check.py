# -*- coding: utf-8 -*-
"""
Headless check of the completion symbol kinds and the completer abstraction:

- control-flow components register as ``builtin`` kind, the DEFINE_* macro
  components as ``macro`` kind and the mesh traversal loops as ``function``
  kind (``ComponentMetadata.Kind``);
- ``_kind_icon`` yields no glyph for builtin kinds and the theme-aware glyphs
  (``cpl_macro.svg`` / ``cpl_var.svg`` / ``cpl_func.svg`` / ``cpl_type.svg`` /
  ``cpl_param.svg``) for the other kinds; the popup reserves the glyph column
  on every row, so the texts align whether a row shows a glyph or not;
- the API snippets carry the kind of their category (data access ``type``,
  callable helpers ``function``, solver state ``parameter``); the cell field
  accessors (``C_T``, ``C_P``...) are no snippets but context-bound components
  carrying the ``type`` kind;
- the fluent kit's analyzer registers itself in the environment on kit import
  and derives ``variable`` completions from the variables the project introduces
  (assignment targets and count-loop counters; nesting and deduplication included);
  it offers the context-bound completions (the cell accessors, the source
  statements) only inside components providing the semantic roles they require;
- ``VisualCodeEdit`` absorbs the completer suggestions, prefixes the popup rows
  with the glyph of their kind, and confirms component-less entries as text;
  the matching is fuzzy (the typed characters hit a keyword whenever they
  appear in order) and the popup rows carry the matched spans the delegate
  renders bold;
- plain-name fields (the member fields) restrict completion to the derived
  suggestions: kit keywords stay out and nothing confirms into a component.

Note: no kit module is imported at top level on purpose; the kits are imported
through ``Environment.import_kit`` after the environment exists, mirroring the
application flow. The completer registry is shared at the class level, so a
bare ``Environment()`` re-initialization (as the editor window performs) never
wipes the completers registered during kit importation.
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QWidget

from alias import *
from core.completer import Completion
from core.component import ComponentMetadata
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit
from core.project import Project
from core.resource import Resource
from core.script import Script
from interface.visual_code_edit import (VisualCodeEdit, _CompletionPopup, _blank_icon, _kind_icon,
                                        _resolve_entry_kind)

Kind = ComponentMetadata.Kind


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
        if modify:
            label.setFixedWidth(40)
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

    env.import_kit(os.path.join(_root, 'kits', 'common'))
    env.import_kit(os.path.join(_root, 'kits', 'fluent'))
    from kits.fluent.analyzer import FluentAnalyzer  # Already cached by the kit import
    from kits.fluent.fluent import UDF

    # 1. Kind classification: control flow stays builtin, DEFINE_* macros are macro
    for name in ('clk.br', 'clk.loop', 'clk.for', 'clk.native', 'clk.assign'):
        meta = env.kit_manager.lookup(name)
        assert meta.kind is Kind.Builtin, (name, meta.kind)
    for name in ('fluent.adjust', 'fluent.on_demand', 'fluent.profile',
                 'fluent.mass_transfer', 'fluent.dpm_law', 'fluent.cg_motion',
                 'fluent.dom_source'):
        meta = env.kit_manager.lookup(name)
        assert meta.kind is Kind.Macro, (name, meta.kind)
    for name in ('fluent.thread_cell_loop', 'fluent.thread_face_loop', 'fluent.cell_loop',
                 'fluent.face_of_cell_loop', 'fluent.node_of_cell_loop'):
        meta = env.kit_manager.lookup(name)
        assert meta.kind is Kind.Function, (name, meta.kind)
    print('kind classification ok')

    # 2. Glyph resolution: builtin carries no icon; the glyphed kinds resolve to
    #    their theme-aware glyph files (omittable icon policy); the transparent
    #    placeholder occupies the glyph column of the rows without a glyph
    assert _kind_icon(Kind.Builtin) is null, 'builtin kind must carry no glyph'
    for kind, icon_file in ((Kind.Macro, 'cpl_macro.svg'), (Kind.Variable, 'cpl_var.svg'),
                            (Kind.Function, 'cpl_func.svg'), (Kind.Type, 'cpl_type.svg'),
                            (Kind.Parameter, 'cpl_param.svg')):
        for theme_name in ('light', 'dark'):
            assert Resource.resource_path('images', theme_name, icon_file).is_file(), \
                (theme_name, icon_file)
        icon = _kind_icon(kind)
        assert icon is not null and not icon.isNull(), (kind, icon)
    placeholder = _blank_icon()
    assert not placeholder.isNull(), 'the alignment placeholder must be a valid icon'
    print('glyph resolution ok')

    # 2a. The cell field accessors became context-bound components: they carry
    #     the type glyph and register at the Expression level (they nest inside
    #     expressions); the argument-less constants became components completing
    #     anywhere; the remaining API entries stay snippets carrying the kind of
    #     their category
    for name in ('c_t', 'c_p', 'c_u', 'c_v', 'c_w', 'c_r', 'c_mu_l', 'c_k_l',
                 'c_t_g', 'c_p_g', 'c_volume'):
        meta = env.kit_manager.lookup(f'fluent.{name}')
        assert meta.kind is Kind.Type, (name, meta.kind)
        assert meta.level == ComponentMetadata.Level.Expression, (name, meta.level)
    assert 'cell_temperature' not in env.snippets and 'cell_volume' not in env.snippets, \
        'the cell accessors must not stay snippets'
    # The argument-less constants register as Expression-level components with
    # global completion keywords (no context gating: they take no argument)
    for name, kind in (('current_timestep', Kind.Parameter), ('current_time', Kind.Parameter),
                       ('previous_time', Kind.Parameter), ('rp_2d', Kind.Type),
                       ('rp_3d', Kind.Type), ('nd_nd', Kind.Type)):
        meta = env.kit_manager.lookup(f'fluent.{name}')
        assert meta.kind is kind, (name, meta.kind)
        assert meta.level == ComponentMetadata.Level.Expression, (name, meta.level)
    for keyword, component_name in (('CURRENT_TIMESTEP', 'fluent.current_timestep'),
                                    ('CURRENT_TIME', 'fluent.current_time'),
                                    ('ND_ND', 'fluent.nd_nd')):
        assert env.kit_manager.completions.get(keyword) == component_name, \
            (keyword, env.kit_manager.completions.get(keyword))
    assert 'ND_ND' not in env.snippets and 'CURRENT_TIME' not in env.snippets, \
        'the constants must not stay snippets'
    # The subscripted C_UDMI access and its writer became context-bound components
    c_udmi = env.kit_manager.lookup('fluent.c_udmi')
    assert c_udmi.kind is Kind.Function and c_udmi.level == ComponentMetadata.Level.Expression
    set_udmi = env.kit_manager.lookup('fluent.set_udmi')
    assert set_udmi.kind is Kind.Function and set_udmi.level == ComponentMetadata.Level.Statement
    # The remaining API helper macros became components too: the ones whose
    # arguments are plain expressions register a global keyword, the ones the
    # context feeds stay out of the global registry (gated completion)
    for component_name, kind in (('fluent.nv_mag', Kind.Function),
                                 ('fluent.lookup_thread', Kind.Function),
                                 ('fluent.thread_id', Kind.Parameter)):
        meta = env.kit_manager.lookup(component_name)
        assert meta.kind is kind, (component_name, meta.kind)
        assert meta.level == ComponentMetadata.Level.Expression, (component_name, meta.level)
    assert env.kit_manager.completions.get('NV_MAG') == 'fluent.nv_mag'
    assert 'Lookup_Thread' not in env.kit_manager.completions \
        and 'THREAD_ID' not in env.kit_manager.completions, \
        'context-bound calls must not register a global keyword'
    assert not env.snippets, 'no snippet must survive the component migration'
    print('api call kinds ok')

    # 3. The analyzer registered itself during the kit import; registration is
    #    idempotent and survives a bare Environment() re-initialization (the
    #    registry is shared at the class level)
    assert FluentAnalyzer in env.completers, 'FluentAnalyzer should register itself on kit import'
    env.register_completer(FluentAnalyzer)
    assert env.completers.count(FluentAnalyzer) == 1, 'register_completer must deduplicate'
    Environment()
    assert FluentAnalyzer in env.completers, 're-initialization must not wipe the completers'
    print('completer registration ok')

    # 4. The analyzer derives one variable completion per distinct introduced name
    #    (assignment targets, count-loop counters and the parameters the macros
    #    declare), descending into nested edits (loop bodies, macro bodies) of
    #    every script
    canvas = _CanvasStub()
    graphics = _GraphicsStub(canvas)
    branch = env.kit_manager.lookup('clk.br').component_type(null, graphics)
    branch.interface.edit_cond.setPlainText('x > 0.0')
    edit_then = branch.interface.edit_then
    assign = edit_then.insert_component(edit_then._lookup_entry('set'))
    assert assign is not null, 'insert_component(set) failed'
    assign.interface.edit_name.setPlainText('velocity')
    loop = edit_then.insert_component(edit_then._lookup_entry('loop'))
    assert loop is not null, 'insert_component(loop) failed'
    nested = loop.interface.edit_body.insert_component(loop.interface.edit_body._lookup_entry('set'))
    assert nested is not null, 'nested insert_component(set) failed'
    nested.interface.edit_name.setPlainText('pressure')
    duplicate = edit_then.insert_component(edit_then._lookup_entry('set'))
    assert duplicate is not null
    duplicate.interface.edit_name.setPlainText('velocity')  # Same name: deduplicated
    for_comp = edit_then.insert_component(edit_then._lookup_entry('for'))
    assert for_comp is not null, 'insert_component(for) failed'
    for_comp.interface.edit_counter.setText('idx')  # Counter name: a variable too

    adjust = env.kit_manager.lookup('fluent.adjust').component_type(null, graphics)
    adjust.interface.edit_name.setText('my_adjust')
    body = adjust.interface.edit_body
    body_assign = body.insert_component(body._lookup_entry('set'))
    assert body_assign is not null, 'insert_component(set) in macro body failed'
    body_assign.interface.edit_name.setPlainText('kount')

    project = Project('kind-check', UDF)
    project.scripts.append(Script(branch))
    project.scripts.append(Script(adjust))
    env.project = project

    derived = FluentAnalyzer(project).complete()
    assert all(isinstance(completion, Completion) for completion in derived)
    assert [completion.keyword for completion in derived] \
        == ['velocity', 'pressure', 'idx', 'd', 'kount'], \
        [completion.keyword for completion in derived]
    assert all(completion.kind is Kind.Variable for completion in derived)
    assert all(not completion.component_name for completion in derived)
    print('analyzer derivation ok:', [completion.keyword for completion in derived])

    # 4a. Context gating: the analyzer offers the context-bound completions only
    #     where the components hosting the requesting edit provide every role
    #     they require (a DEFINE_SOURCE body provides them all; a cell loop the
    #     cell accessors alone; a contextless position none)
    src = env.kit_manager.lookup('fluent.source').component_type(null, graphics)
    src.interface.edit_name.setText('ctx_src')
    src_project = Project('ctx-check', UDF)
    src_project.scripts.append(Script(src))
    src_analyzer = FluentAnalyzer(src_project)
    inside = src_analyzer.complete(at=src.interface.edit_body)
    inside_keywords = {completion.keyword for completion in inside}
    for keyword in ('cell_temperature', 'cell_pressure', 'cell_volume', 'cell_user_memory', 'set_udmi',
                    'set_cell_profile', 'set_cell_temperature',
                    'set_source_const', 'set_source_diff', 'end_source', 'phase_index'):
        assert keyword in inside_keywords, (keyword, sorted(inside_keywords))
    # The whole-project view carries no context completions
    assert not any(completion.component_name for completion in src_analyzer.complete()), \
        'context completions must never surface in the whole-project view'
    # A cell loop provides the cell and the thread (the accessors complete),
    # the enclosing adjust body provides neither (nothing completes)
    adjust2 = env.kit_manager.lookup('fluent.adjust').component_type(null, graphics)
    adjust2.interface.edit_name.setText('ctx_adjust')
    loop_body = adjust2.interface.edit_body
    cell_loop = loop_body.insert_component(loop_body._lookup_entry('begin_c_loop'))
    assert cell_loop is not null, 'insert_component(begin_c_loop) failed'
    loop_project = Project('ctx-loop-check', UDF)
    loop_project.scripts.append(Script(adjust2))
    loop_analyzer = FluentAnalyzer(loop_project)
    in_loop = {completion.keyword for completion in loop_analyzer.complete(at=cell_loop.interface.edit_body)}
    assert 'cell_temperature' in in_loop and 'set_udmi' in in_loop and 'set_source_const' not in in_loop, sorted(in_loop)
    assert 'phase_index' in in_loop, sorted(in_loop)  # The loop thread serves the PHASE_INDEX macro
    assert 'cell_centroid' in in_loop and 'Lookup_Thread' in in_loop, sorted(in_loop)  # cell+thread, domain
    assert 'face_temperature' not in in_loop, sorted(in_loop)  # No face in a cell loop
    # The assignment accessors gate like their reading counterparts
    assert 'set_cell_profile' in in_loop and 'set_face_profile' not in in_loop, sorted(in_loop)
    # A face loop provides the face and the thread (the face accessors
    # complete), but no cell (the cell accessors stay out)
    face_loop = loop_body.insert_component(loop_body._lookup_entry('begin_f_loop'))
    assert face_loop is not null, 'insert_component(begin_f_loop) failed'
    in_face_loop = {completion.keyword for completion in loop_analyzer.complete(at=face_loop.interface.edit_body)}
    assert 'face_temperature' in in_face_loop and 'face_centroid' in in_face_loop, sorted(in_face_loop)
    assert 'cell_temperature' not in in_face_loop, sorted(in_face_loop)  # No cell in a face loop
    assert 'set_face_profile' in in_face_loop and 'set_face_user_memory' in in_face_loop, sorted(in_face_loop)
    assert 'set_cell_profile' not in in_face_loop, sorted(in_face_loop)  # No cell in a face loop
    out_loop = {completion.keyword for completion in loop_analyzer.complete(at=loop_body)}
    assert 'cell_temperature' not in out_loop, sorted(out_loop)
    assert 'Lookup_Thread' in out_loop, sorted(out_loop)  # The macro body provides the domain
    assert 'THREAD_ID' not in out_loop and 'phase_index' not in out_loop, sorted(out_loop)
    print('context gating ok')

    # 5. The editor absorbs the completer suggestions; derived entries bypass the
    #    level filter (they carry no component) and survive repeated absorption
    stmt_edit = graphics.create_visual_code_edit(QRectF(0, 0, 0, 30))
    stmt_edit.filter(ComponentMetadata.Level.Statement)
    stmt_edit._sync_completer_completions()
    stmt_edit._sync_completer_completions()
    absorbed = [entry for entry in stmt_edit.completions if entry.keyword == 'velocity']
    assert len(absorbed) == 1, f'velocity absorbed {len(absorbed)} times'
    var_entry = absorbed[0]
    assert var_entry.component_name == '' and var_entry.kind is Kind.Variable
    assert stmt_edit._entry_participates(var_entry), \
        'derived suggestions must stay available in every level context'
    print('editor absorption ok')

    # 6. Kind resolution of entries: explicit kind wins, otherwise the component
    #    metadata decides; the popup prefixes the rows with the glyph accordingly
    macro_entry = VisualCodeEdit.CompletionEntry('adjust', 'fluent.adjust')
    builtin_entry = VisualCodeEdit.CompletionEntry('if', 'clk.br')
    assert _resolve_entry_kind(var_entry) is Kind.Variable
    assert _resolve_entry_kind(macro_entry) is Kind.Macro
    assert _resolve_entry_kind(builtin_entry) is Kind.Builtin
    popup = _CompletionPopup()
    popup.set_entries([var_entry, macro_entry, builtin_entry])
    assert popup.list.count() == 3
    assert popup.list.iconSize() == QSize(16, 16), 'the glyph column must have a uniform size'
    assert not popup.list.item(0).icon().isNull(), 'variable row must carry the variable glyph'
    assert not popup.list.item(1).icon().isNull(), 'macro row must carry the macro glyph'
    assert not popup.list.item(2).icon().isNull(), 'builtin row must reserve the glyph column'
    print('popup glyphs ok')

    # 6a. Fuzzy matching: the typed word hits a keyword whenever its characters
    #     appear in order (the head need not be typed); exact and prefix hits
    #     outrank fuzzy ones, and each popup row carries the matched spans the
    #     delegate bolds
    from interface.visual_code_edit import _fuzzy_match
    assert _fuzzy_match('cell_temperature', 'tmpr') == [(5, 6), (7, 9), (10, 11)], \
        _fuzzy_match('cell_temperature', 'tmpr')
    assert _fuzzy_match('cell_temperature', '') == []
    assert _fuzzy_match('for', 'xyz') is null
    stmt_edit.setPlainText('fr')
    cursor = stmt_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    stmt_edit.setTextCursor(cursor)
    stmt_edit._update_completion()
    assert stmt_edit._popup is not null and stmt_edit._popup.entries, \
        'a fuzzy hit must open the popup'
    fuzzy_keywords = [entry.keyword for entry in stmt_edit._popup.entries]
    assert fuzzy_keywords[0] == 'for' and 'for' in fuzzy_keywords, fuzzy_keywords
    first_item = stmt_edit._popup.list.item(0)
    assert first_item.data(Qt.ItemDataRole.UserRole + 1) == 3, 'the row carries the keyword length'
    assert [list(span) for span in first_item.data(Qt.ItemDataRole.UserRole)] == [[0, 1], [2, 3]], \
        'the row carries the matched spans'
    stmt_edit._hide_popup()
    print('fuzzy completion matching ok')

    # 7. Confirming a derived suggestion completes the keyword as plain text
    stmt_edit.setPlainText('velo')
    cursor = stmt_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    stmt_edit.setTextCursor(cursor)
    stmt_edit._confirm_completion(var_entry)
    assert stmt_edit.toPlainText() == 'velocity', stmt_edit.toPlainText()
    print('derived completion confirmation ok')

    # 8. Plain-name fields (the member fields) restrict completion to the derived
    #    suggestions: the project variables are offered, kit keywords stay out and
    #    nothing typed confirms into a component
    field_comp = stmt_edit.insert_component(stmt_edit._lookup_entry('member'))
    assert field_comp is not null, 'insert_component(member) failed'
    owner_edit = field_comp._interface.edit_owner
    assert owner_edit.derivedCompletionsEnabled(), 'member fields must restrict to derived suggestions'
    assert not any(entry.component_name for entry in owner_edit.completions), \
        'a derived-only edit must hold no component entries'
    owner_edit._sync_kit_completions()  # Kit keywords never enter a derived-only edit
    assert not any(entry.component_name for entry in owner_edit.completions)
    owner_edit._sync_completer_completions()
    owner_var = next(entry for entry in owner_edit.completions if entry.keyword == 'velocity')
    assert owner_var.kind is Kind.Variable and not owner_var.component_name
    assert owner_edit._lookup_entry('adjust') is null, 'kit keywords must not complete in name fields'
    owner_edit.setPlainText('vel')
    cursor = owner_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    owner_edit.setTextCursor(cursor)
    owner_edit._confirm_completion(owner_var)
    assert owner_edit.toPlainText() == 'velocity', owner_edit.toPlainText()
    print('derived-only name fields ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
