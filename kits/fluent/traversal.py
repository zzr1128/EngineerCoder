# -*- coding: utf-8 -*-
"""
Mesh traversal loops of Ansys Fluent as native UDF components.

Fluent organizes the mesh in *threads* (groups of cells or faces sharing a
zone); UDF code walks the mesh through a small family of macros: the
``thread_loop_*`` macros iterate the threads of a domain, ``begin_c_loop``/
``end_c_loop`` iterate the cells inside one thread, ``begin_f_loop``/
``end_f_loop`` iterate the faces inside one thread, and ``c_face_loop``/
``c_node_loop`` iterate the faces or nodes bounding one cell.

Each macro family becomes one statement-level component: the usernames the
identifiers the macro's arguments declare (the loop variables), fills the
body, and compilation emits the macro invocation(s) wrapping the body block::

    thread_loop_c(t, d)
    {
        begin_c_loop(c, t)
        {
            ...
        }
        end_c_loop(c, t)
    }

The loops nest inside visual code edits (they carry the ``Statement`` level),
so ``udf.render_component`` renders them through their archive-based
``render`` classmethod. The identifiers the arguments declare enter the
scope analysis (``register_scope_contributor``), so the bodies complete them;
arguments tagged with a semantic role (``roles``) additionally enter the
compilation context while the body renders (``udf.enter_context``), so the
context-aware components nested inside resolve their arguments through them.
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from alias import *
from core.build import Compiler
from core.completer import Completion
from core.component import Component, ComponentMetadata, IComponentInterface
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.kit import KitManager
from kits.common.library import CLLibrary
from kits.common.validation import attach_identifier_check, attach_source_lint
from kits.fluent.analyzer import register_scope_contributor
from kits.fluent.fluent import UDF, fluent
from kits.fluent.localization import _


class CFluentIterationLoop(Component, abstract):
    """
    Base of the mesh traversal loop components.

    Subclasses declare, besides the metadata, the opening macro emitted to
    the source (``head``), the closing macro (``tail``, empty when the family
    closes with the body block alone), the identifiers the macro's arguments
    declare (``args_spec``: (label, conventional identifier) pairs), which of
    them introduce fresh loop variables (``introduced``: indices into
    ``args_spec``) and the completion keyword (``completion_keyword``). The
    interface, the serialization contract and the compilation are shared.
    """

    # Opening macro as it appears in the generated source
    head: ClassVar[string] = ''
    # Closing macro (same arguments); empty when the body block closes the loop
    tail: ClassVar[string] = ''
    # (label, identifier) pairs of the macro arguments
    args_spec: ClassVar[tuple[tuple[string, string], ...]] = ()
    # Indices into args_spec of the arguments declaring fresh loop variables
    introduced: ClassVar[tuple[int, ...]] = ()
    # Semantic roles of the arguments, aligned with args_spec ('' for arguments
    # without one): the identifiers enter the compilation context under their
    # role while the body renders (see ``ContextKey`` in ``kits.fluent.udf``)
    roles: ClassVar[tuple[string, ...]] = ()
    # Keyword that inserts this component through code completion
    completion_keyword: ClassVar[string] = ''

    @classmethod
    def context_roles(cls) -> frozenset[string]:
        """
        :return: the semantic roles the loop's arguments enter the compilation
            context under while the body renders; the completion analyzer offers
            the context-aware components requiring these roles inside the loop only
        """
        return frozenset(role for role in cls.roles if role)

    class FIterationLoopInterface(IComponentInterface):
        lt_body: Final[string] = _('label_body')

        def __init__(self, owner: typeof['CFluentIterationLoop'], graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            head_font = QFont("Courier New", 10, QFont.Weight.Bold)
            self.label_head = graphics.create_native_label(owner.head, head_font)
            graphics.label_metric_width(self.label_head, modify=True)
            self.label_body = graphics.create_native_label(self.lt_body, self.font)
            graphics.label_metric_width(self.label_body, modify=True)
            # A short caption restating what the loop is for in plain words (the
            # localized component description), so non-programmer users can tell
            # the loops apart; drop the macro-name prefix the description carries
            brief = owner.meta().description
            for separator in ('：', ': '):  # Punctuation of both locale languages
                if brief.startswith(owner.head + separator):
                    brief = brief[len(owner.head) + len(separator):]
                    break
            self.label_brief = graphics.create_native_label(brief, self.font)
            graphics.label_metric_width(self.label_brief, modify=True)
            try:
                colors = Environment.instance().theme.colors
                subdued = QColor.fromRgb(colors.foreground.rgb() // 2 + colors.background.rgb() // 2)
            except Exception:  # Headless contexts without a loaded theme
                subdued = QColor('#808080')
            self.label_brief.setStyleSheet(f'color: {subdued.name()};')
            # The loop variables are plain names: single-line edits never embed
            # components; the registered checkers mark illegal identifiers red
            self.arg_labels: IList[QLabel] = []
            self.arg_edits: IList[QLineEdit] = []
            for label_text, arg_name in owner.args_spec:
                label = graphics.create_native_label(label_text, self.font)
                graphics.label_metric_width(label, modify=True)
                self.arg_labels.append(label)
                # Pre-fill the identifier the macro argument conventionally uses
                edit = graphics.create_lineedit(QRectF(0, 0, 100, 24))
                edit.setText(arg_name)
                attach_identifier_check(edit)
                self.arg_edits.append(edit)
            self.edit_body = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 60))
            self.edit_body.setPlaceholderText(_('placeholder_body'))
            # A loop body is a statement context
            self.edit_body.filter(ComponentMetadata.Level.Statement)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_head, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    null, null)
            for label, edit in zip(self.arg_labels, self.arg_edits):
                # A label may start a new row; its edit glues to it (NoBreak),
                # so the layout wraps the pair as a whole
                self.layout.add_element(label, CLLibrary.GLinearLayout.ElementRowPolicy.Default, null, null)
                self.layout.add_element(edit, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.label_brief, CLLibrary.GLinearLayout.ElementRowPolicy.New, null, null)
            self.layout.add_element(self.label_body, null, null, null)
            self.layout.add_element(self.edit_body, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)
            self.color = graphics.alloc_color()

        def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:
            # Locate figures and widgets at the UI origin of this interface
            graphics.push_anchor(self.origin)
            try:
                self.layout.update(graphics)

                if painting:
                    size = self.layout.size(graphics)
                    # Box size includes one margin on each side; deduct 2*2.5 so the frame insets 2.5px into margins
                    graphics.disp_draw_rect(QRectF(2.5, 2.5, size.width() - 5, size.height() - 5), self.color, round_radius=5)
            finally:
                graphics.pop_anchor()

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        super().__init__(parent, graphics)
        self._interface = CFluentIterationLoop.FIterationLoopInterface(type(self), graphics)
        # The body holds handwritten UDF statements: the asynchronous lint
        # checks them gently (wrapped into a minimal translation unit)
        attach_source_lint(self._interface.edit_body, fragment=True)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.arg_edits[0]  # The first loop variable is the first field

    def editableWidgets(self) -> IList[QWidget]:
        return [*self._interface.arg_edits, self._interface.edit_body]

    def __serialize__(self) -> dict:
        return {
            'args': [edit.text() for edit in self._interface.arg_edits],
            'body': serialize(self._interface.edit_body)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a traversal loop from its serialization.

        The constructor reconstructs the interface (whose fields are empty);
        the archived contents are then loaded into those controls in place,
        since their references are held by the interface layout.
        """
        require_member(data, 'args', 'body')
        require_type(data['args'], list, 'args')
        if len(data['args']) != len(cls.args_spec):
            raise SerializationError(f'{cls.meta().name} expects {len(cls.args_spec)} argument(s), '
                                     f'got {len(data["args"])}')
        component = cls(parent, graphics)
        for edit, arg in zip(component._interface.arg_edits, data['args']):
            require_type(arg, string, 'args')
            edit.setText(arg)
        component._interface.edit_body.load(data['body'])
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the archive of this loop into UDF source: the opening macro
        wrapping the body block, followed by the closing macro when the family
        carries one.

        The UDF convention requires every macro argument to stay on the same
        line as the macro name, hence the header is always a single line.
        """
        from kits.fluent import udf  # Deferred: udf.py and traversal.py share the kit entry chain

        require_member(data, 'args', 'body')
        require_type(data['args'], list, 'args')
        if len(data['args']) != len(cls.args_spec):
            raise SerializationError(f'{cls.meta().name} expects {len(cls.args_spec)} argument(s), '
                                     f'got {len(data["args"])}')
        parts = [string(arg).strip() for arg in data['args']]
        # The identifiers the role-tagged arguments declare enter the compilation
        # context while the body renders, so context-aware components resolve
        # through them
        context: IDictionary[string, string] = {
            role: part for role, part in zip(cls.roles, parts) if role
        }
        udf.enter_context(builder, context)
        try:
            # The body is a fresh block: declarations lifted into it precede its contents
            body = udf._hoist_prefix(builder, data['body']) + udf.render_edit(data['body'], builder)
        finally:
            udf.exit_context(builder)
        source = f'{cls.head}({", ".join(parts)})\n{udf._block(body)}'
        if cls.tail:
            source += f'\n{cls.tail}({", ".join(parts)})'
        return source

    def compile(self, builder: Compiler) -> void:
        """
        Emit the loop into the UDF products.
        """
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(type(self).render(serialize(self), builder))


@fluent.register
@Component.use__interface
@ComponentMetadata.create('thread_cell_loop', _('thread_cell_display_name'), _('thread_cell_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CThreadCellLoop(CFluentIterationLoop):
    """``thread_loop_c(t, d)``: iterate every cell thread of the domain;
    ``t`` names the ``Thread *`` loop variable."""
    head = 'thread_loop_c'
    args_spec = ((_('label_thread'), 't'), (_('label_domain'), 'd'))
    introduced = (0,)
    roles = ('thread', 'domain')
    completion_keyword = 'thread_loop_c'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('thread_face_loop', _('thread_face_display_name'), _('thread_face_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CThreadFaceLoop(CFluentIterationLoop):
    """``thread_loop_f(t, d)``: iterate every face thread of the domain;
    ``t`` names the ``Thread *`` loop variable."""
    head = 'thread_loop_f'
    args_spec = ((_('label_thread'), 't'), (_('label_domain'), 'd'))
    introduced = (0,)
    roles = ('thread', 'domain')
    completion_keyword = 'thread_loop_f'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('cell_loop', _('cell_loop_display_name'), _('cell_loop_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CCellLoop(CFluentIterationLoop):
    """``begin_c_loop(c, t)`` ... ``end_c_loop(c, t)``: iterate every cell of
    one thread; ``c`` names the ``cell_t`` loop variable."""
    head = 'begin_c_loop'
    tail = 'end_c_loop'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'))
    introduced = (0,)
    roles = ('cell', 'thread')
    completion_keyword = 'begin_c_loop'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('face_loop', _('face_loop_display_name'), _('face_loop_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CFaceLoop(CFluentIterationLoop):
    """``begin_f_loop(f, t)`` ... ``end_f_loop(f, t)``: iterate every face of
    one thread; ``f`` names the ``face_t`` loop variable."""
    head = 'begin_f_loop'
    tail = 'end_f_loop'
    args_spec = ((_('label_face'), 'f'), (_('label_thread'), 't'))
    introduced = (0,)
    roles = ('face', 'thread')
    completion_keyword = 'begin_f_loop'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('face_of_cell_loop', _('face_of_cell_display_name'), _('face_of_cell_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CFaceOfCellLoop(CFluentIterationLoop):
    """``c_face_loop(c, t, n)``: iterate every face bounding one cell; ``n``
    names the ``Thread *``-indexed face number (``C_FACE``/``C_FACE_THREAD``
    resolve the face and its thread inside the body)."""
    head = 'c_face_loop'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'), (_('label_index'), 'n'))
    introduced = (2,)
    roles = ('cell', 'thread', '')
    completion_keyword = 'c_face_loop'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('node_of_cell_loop', _('node_of_cell_display_name'), _('node_of_cell_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CNodeOfCellLoop(CFluentIterationLoop):
    """``c_node_loop(c, t, n)``: iterate every node of one cell; ``n`` names
    the node number (``C_NODE`` resolves the node inside the body)."""
    head = 'c_node_loop'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'), (_('label_index'), 'n'))
    introduced = (2,)
    roles = ('cell', 'thread', '')
    completion_keyword = 'c_node_loop'


# Description of the loop variables in the popup detail pane
lt_iteration_var: Final[string] = _('desc_iteration_var')


def _iteration_variables(component: Component) -> IList[Completion]:
    """The identifiers the loop's arguments declare: variables of the loop's
    own scope (they never leave the loop body)."""
    if not isinstance(component, CFluentIterationLoop):
        return []
    introduced: IList[Completion] = []
    for index in type(component).introduced:
        name = component.interface.arg_edits[index].text().strip()
        if name:
            introduced.append(Completion(keyword=name,
                                         kind=ComponentMetadata.Kind.Variable,
                                         visibility='scoped',
                                         description=lt_iteration_var))
    return introduced


# Contribute the completion keywords to the global registry, so any visual code
# edit picks the loops up (filtered by level)
for _comp in (CThreadCellLoop, CThreadFaceLoop, CCellLoop, CFaceLoop, CFaceOfCellLoop, CNodeOfCellLoop):
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))

# Contribute the loop variables to the scope analysis, so the bodies of the
# loops complete them (the registration is idempotent, so the sibling kit
# modules sharing this import never double it)
register_scope_contributor(_iteration_variables)
