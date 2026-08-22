# -*- coding: utf-8 -*-
"""
General (solver-wide) UDF macros of Ansys Fluent as native UDF components, and
the translation unit that collects them into a UDF source file.

Every macro component wraps one of the ``DEFINE_*`` macros that register a
callback with the Fluent solver: the user supplies the function name, the
identifiers the macro parameters declare, and the function body; compilation
emits the macro invocation followed by the body block, e.g.::

    DEFINE_ADJUST(my_adjust, d)
    {
        ...
    }

These macros define complete functions, so the components carry the ``Domain``
level: they may appear in top-level (file) contexts only, never nested inside
statement blocks (see ``VisualCodeEdit.filter``). The body edit therefore
filters at the ``Statement`` level.

``CTranslationUnit`` is the document root of a UDF script: a whole-page visual
code edit hosting the macros (and free C declarations), which compiles into
one C translation unit starting with ``#include "udf.h"``.
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
from kits.fluent.analyzer import register_context_completion, register_scope_contributor
from kits.fluent.fluent import UDF, fluent
from kits.fluent.localization import _


class MacroArgument(NamedTuple):
    """
    Specification of one parameter of a ``DEFINE_*`` macro.

    ``label`` captions the identifier edit in the interface and ``identifier``
    pre-fills it. ``hidden`` parameters never surface in the interface (the
    header renders them with their conventional identifier): they stay out of
    the way of non-programmer users while the generated source keeps the full
    parameter list the UDF convention requires. ``index``, when non-empty,
    names the index the parameter is conventionally subscripted with: the
    scope contribution then reads ``identifier[index]`` (e.g. the source-term
    derivative ``dS[eqn]``, the only form the UDF guide uses). ``role``, when
    non-empty, tags the identifier with its semantic role ('cell', 'thread'...):
    while the macro body renders, the identifier enters the compilation context
    under that role (see ``ContextKey`` in ``kits.fluent.udf``), so the
    context-aware components nested inside resolve their arguments through it.
    """
    label: string
    identifier: string
    index: string = ''
    hidden: bool = False
    role: string = ''


class CFluentMacro(Component, abstract):
    """
    Base of the ``DEFINE_*`` macro components.

    Subclasses declare, besides the metadata, the macro name emitted to the
    source (``macro``), the identifiers of the parameters the macro declares
    after the function name (``args_spec``, empty for parameterless macros)
    and the completion keyword (``completion_keyword``). The interface, the
    serialization contract and the compilation are shared by the base.
    """

    # Name of the DEFINE_* macro as it appears in the generated source
    macro: ClassVar[string] = ''
    # Parameters of the macro following the name: (label, identifier) pairs or
    # MacroArgument entries (hidden parameters stay out of the interface)
    args_spec: ClassVar[tuple[tuple[string, string] | MacroArgument, ...]] = ()
    # Keyword that inserts this component through code completion
    completion_keyword: ClassVar[string] = ''
    # C type the macro function returns ('' for void macros): a non-empty type
    # gives the interface a result field whose expression the body returns
    return_type: ClassVar[string] = ''

    @classmethod
    def arguments(cls) -> tuple[MacroArgument, ...]:
        """The parameter specification normalized to ``MacroArgument`` entries."""
        return tuple(arg if isinstance(arg, MacroArgument) else MacroArgument(*arg)
                     for arg in cls.args_spec)

    @classmethod
    def _normalized_args(cls, data: IDictionary[string, Any]) -> IList[Any]:
        """
        :return: the archived identifiers of the visible parameters
        :raise SerializationError: raise when the archive fits neither the
            current specification nor its legacy form

        Legacy archives recorded the hidden parameters too: they are reduced
        positionally to the visible ones. Archives made before the visible
        parameters shrank (e.g. ``DEFINE_SOURCE`` dropped the derivative and
        the equation index) keep the leading identifiers only.
        """
        arguments = cls.arguments()
        visible = [argument for argument in arguments if not argument.hidden]
        args = list(data['args'])
        if len(args) == len(arguments) and len(args) != len(visible):
            args = [arg for arg, argument in zip(args, arguments) if not argument.hidden]
        if len(args) > len(visible):
            args = args[:len(visible)]
        if len(args) != len(visible):
            raise SerializationError(f'{cls.meta().name} expects {len(visible)} argument(s), '
                                     f'got {len(data["args"])}')
        return args

    class FMacroInterface(IComponentInterface):
        lt_name: Final[string] = _('label_name')
        lt_body: Final[string] = _('label_body')
        lt_result: Final[string] = _('label_result')

        def __init__(self, owner: typeof['CFluentMacro'], graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            macro_font = QFont("Courier New", 10, QFont.Weight.Bold)
            self.label_macro = graphics.create_native_label(owner.macro, macro_font)
            graphics.label_metric_width(self.label_macro, modify=True)
            # Every DEFINE_* macro names the function it declares, so the name
            # field is always captioned with the identifier label
            self.label_name = graphics.create_native_label(self.lt_name, self.font)
            graphics.label_metric_width(self.label_name, modify=True)
            self.label_body = graphics.create_native_label(self.lt_body, self.font)
            graphics.label_metric_width(self.label_body, modify=True)
            # A short caption restating what the macro is for in plain words (the
            # localized component description), so non-programmer users can tell
            # the macros apart; drop the macro-name prefix the description carries
            brief = owner.meta().description
            for separator in ('：', ': '):  # Punctuation of both locale languages
                if brief.startswith(owner.macro + separator):
                    brief = brief[len(owner.macro) + len(separator):]
                    break
            self.label_brief = graphics.create_native_label(brief, self.font)
            graphics.label_metric_width(self.label_brief, modify=True)
            try:
                colors = Environment.instance().theme.colors
                subdued = QColor.fromRgb(colors.foreground.rgb() // 2 + colors.background.rgb() // 2)
            except Exception:  # Headless contexts without a loaded theme
                subdued = QColor('#808080')
            self.label_brief.setStyleSheet(f'color: {subdued.name()};')
            # The function name and the parameter identifiers are plain names:
            # single-line edits never embed components; the registered checkers
            # mark illegal identifiers red right while the user writes
            self.edit_name = graphics.create_lineedit(QRectF(0, 0, 140, 24))
            self.edit_name.setPlaceholderText(_('placeholder_function_name'))
            attach_identifier_check(self.edit_name)
            self.arg_labels: IList[QLabel] = []
            self.arg_edits: IList[QLineEdit] = []
            for argument in owner.arguments():
                if argument.hidden:
                    continue  # The header renders its conventional identifier
                label = graphics.create_native_label(argument.label, self.font)
                graphics.label_metric_width(label, modify=True)
                self.arg_labels.append(label)
                # Pre-fill the identifier the macro parameter conventionally uses
                edit = graphics.create_lineedit(QRectF(0, 0, 100, 24))
                edit.setText(argument.identifier)
                attach_identifier_check(edit)
                self.arg_edits.append(edit)
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_body = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 60))
            self.edit_body.setPlaceholderText(_('placeholder_body'))
            # A function body is a statement context; Domain-level macros never nest in it
            self.edit_body.filter(ComponentMetadata.Level.Statement)
            # Macros returning a value carry a result field: a single-line
            # expression the body returns at the end, so non-programmer users
            # never write the return statement themselves
            if owner.return_type:
                self.label_result = graphics.create_native_label(self.lt_result, self.font)
                graphics.label_metric_width(self.label_result, modify=True)
                self.edit_result = graphics.create_visual_code_edit(
                    QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 24))
                self.edit_result.setPlaceholderText(_('placeholder_result'))
                # The result is an expression context: operators nest, statements never do
                self.edit_result.filter(ComponentMetadata.Level.Expression)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_macro, null, null, null)
            if self.arg_labels:
                # Reserve the identifier label, the argument labels and identifier
                # edits plus the paddings before them, so the header row ends at
                # the right margin while it fits the container
                reserved = self.label_name.width() + self.layout.horizonal_padding \
                           + sum(label.width() for label in self.arg_labels) \
                           + sum(edit.width() for edit in self.arg_edits) \
                           + 2 * len(self.arg_labels) * self.layout.horizonal_padding
                self.layout.add_element(self.label_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        null, null)
                # The name edit never shrinks below its natural width: when the
                # header is too long for the container (many parameters), the
                # argument pairs wrap below it instead of spilling past the edge
                self.layout.add_element(self.edit_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        CLLibrary.GLinearLayout.FillWidth - reserved,
                                        null, min_width=self.edit_name.width())
                for label, edit in zip(self.arg_labels, self.arg_edits):
                    # A label may start a new row; its edit glues to it (NoBreak),
                    # so the layout wraps the pair as a whole
                    self.layout.add_element(label, CLLibrary.GLinearLayout.ElementRowPolicy.Default, null, null)
                    self.layout.add_element(edit, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            else:
                self.layout.add_element(self.label_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        null, null)
                self.layout.add_element(self.edit_name, CLLibrary.GLinearLayout.ElementRowPolicy.Break, null, null)
            self.layout.add_element(self.label_brief, CLLibrary.GLinearLayout.ElementRowPolicy.New, null, null)
            self.layout.add_element(self.label_body, null, null, null)
            self.layout.add_element(self.edit_body, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)
            if owner.return_type:
                self.layout.add_element(self.label_result, CLLibrary.GLinearLayout.ElementRowPolicy.New,
                                        null, null)
                self.layout.add_element(self.edit_result, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
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
        self._interface = CFluentMacro.FMacroInterface(type(self), graphics)
        # The body holds hand-written UDF statements: the asynchronous lint
        # checks them gently (wrapped into a minimal translation unit)
        attach_source_lint(self._interface.edit_body, fragment=True)
        if type(self).return_type:
            # The result field holds one expression; the same gentle lint applies
            attach_source_lint(self._interface.edit_result, fragment=True)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_name  # The function name is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        widgets: IList[QWidget] = [self._interface.edit_name, *self._interface.arg_edits,
                                   self._interface.edit_body]
        if type(self).return_type:
            widgets.append(self._interface.edit_result)
        return widgets

    def __serialize__(self) -> dict:
        data = {
            'name': self._interface.edit_name.text(),
            'args': [edit.text() for edit in self._interface.arg_edits],
            'body': serialize(self._interface.edit_body)
        }
        if type(self).return_type:
            data['result'] = serialize(self._interface.edit_result)
        return data

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a macro component from its serialization.

        The constructor reconstructs the interface (whose fields are empty);
        the archived contents are then loaded into those controls in place,
        since their references are held by the interface layout.
        """
        require_member(data, 'name', 'args', 'body')
        require_type(data['name'], string, 'name')
        require_type(data['args'], list, 'args')
        args = cls._normalized_args(data)
        component = cls(parent, graphics)
        component._interface.edit_name.setText(data['name'])
        for edit, arg in zip(component._interface.arg_edits, args):
            require_type(arg, string, 'args')
            edit.setText(arg)
        component._interface.edit_body.load(data['body'])
        # 'result' is absent in archives made before the result field existed
        if cls.return_type and 'result' in data:
            component._interface.edit_result.load(data['result'])
        return component

    @classmethod
    def context_roles(cls) -> frozenset[string]:
        """
        :return: the semantic roles the macro's parameters enter the
            compilation context under while the body renders (see ``ContextKey``
            in ``kits.fluent.udf``); the completion analyzer offers the
            context-aware components requiring these roles inside the macro only
        """
        return frozenset(argument.role for argument in cls.arguments() if argument.role)

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the archive of this macro into UDF source: the macro invocation
        followed by the body block.

        The UDF convention requires every macro parameter to stay on the same
        line as the macro name, hence the header is always a single line.
        """
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        require_member(data, 'name', 'args', 'body')
        require_type(data['name'], string, 'name')
        require_type(data['args'], list, 'args')
        provided = iter(cls._normalized_args(data))
        parts = [data['name'].strip()]
        context: IDictionary[string, string] = {}
        for argument in cls.arguments():
            # Hidden parameters keep their conventional identifier in the header
            value = argument.identifier if argument.hidden else string(next(provided)).strip()
            parts.append(value)
            if argument.role:
                context[argument.role] = value
        # The identifiers the parameters declare enter the compilation context
        # while the body renders, so context-aware components resolve through them
        udf.enter_context(builder, context)
        try:
            # The body is a fresh block: declarations lifted into it precede its contents
            body = udf._hoist_prefix(builder, data['body']) + udf.render_edit(data['body'], builder)
            # The result field supplies the return value returning macros carry
            result = data.get('result') if cls.return_type else null
            if isinstance(result, dict):
                result_source = udf.render_edit(result, builder).strip()
                if result_source:
                    body = f'{body}\nreturn ({result_source});' if body.strip() else f'return ({result_source});'
        finally:
            udf.exit_context(builder)
        return f'{cls.macro}({", ".join(parts)})\n{udf._block(body)}'

    def compile(self, builder: Compiler) -> void:
        """
        Emit ``MACRO(name, args...) { body }`` into the UDF products.
        """
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(type(self).render(serialize(self), builder))


class CReturnMacro(CFluentMacro, abstract):
    """
    Base of the ``DEFINE_*`` macros whose function returns a value the
    interface never shows (``DEFINE_SOURCE`` follows the same convention,
    see ``kits.fluent.model``): the compilation picks an available identifier
    for the value itself and declares it zero-initialized at the body top.
    The body stores the returned value through the macro's "set" statement
    and ends with the macro's "end" statement (see ``CMacroStatement``), so
    non-programmer users never name the quantity nor write the return
    themselves. Legacy archives kept the expression in a result field:
    ``restore`` migrates it into those two statements.
    """

    # Base of the identifier the compilation picks for the returned value
    value_base: ClassVar[string] = 'value'
    # Role the auto-named value enters the compilation context under
    value_role: ClassVar[string] = 'return_value'
    # Component name (inside this kit) of the statement storing the value
    set_component: ClassVar[string] = ''
    # Component name (inside this kit) of the statement ending the macro
    end_component: ClassVar[string] = ''

    @classmethod
    def context_roles(cls) -> frozenset[string]:
        # On top of the roles the parameters declare, the macro opens the role
        # its own rendering introduces (the auto-named value to return)
        return super().context_roles() | frozenset((cls.value_role,))

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the archive of this macro into UDF source. Unlike the plain
        macros, the header carries an identifier the compilation picks itself
        (an available name for the value to return, ``value``, ``value_1``...),
        which a zero-initializing declaration introduces at the body top. The
        body renders under a context providing the value's role.
        """
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        require_member(data, 'name', 'args', 'body')
        require_type(data['name'], string, 'name')
        require_type(data['args'], list, 'args')
        provided = iter(cls._normalized_args(data))
        parts = [data['name'].strip()]
        context: IDictionary[string, string] = {}
        for argument in cls.arguments():
            # Hidden parameters keep their conventional identifier in the header
            value = argument.identifier if argument.hidden else string(next(provided)).strip()
            parts.append(value)
            if argument.role:
                context[argument.role] = value
        name = data['name'].strip()
        occupied: HashSet[string] = builder.products.setdefault(udf.OccupiedKey, HashSet[string]())
        returned = udf.fresh_name(cls.value_base, occupied | {name} | set(parts))
        context[cls.value_role] = returned
        # The identifiers the parameters declare (plus the auto-named value)
        # enter the compilation context while the body renders
        udf.enter_context(builder, context)
        occupied.add(returned)
        try:
            # The body is a fresh block: declarations lifted into it precede its
            # contents; the declaration of the value to return leads the body itself
            body = udf._hoist_prefix(builder, data['body']) \
                   + f'real {returned} = 0.;\n' + udf.render_edit(data['body'], builder)
        finally:
            udf.exit_context(builder)
            occupied.discard(returned)
        return f'{cls.macro}({", ".join(parts)})\n{udf._block(body)}'

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a returning macro from its serialization.

        Legacy archives kept the returned expression in a result field the
        interface no longer carries: it migrates into the body as the macro's
        "set" statement followed by its "end" statement, preserving the
        expression the archive compiled to ``return`` before the redesign.
        """
        result = data.get('result')
        if isinstance(result, dict) and (result.get('text', '').strip() or result.get('components')):
            body = dict(data['body'])
            text = string(body.get('text', ''))
            if text.strip() and not text.endswith('\n'):
                text += '\n'
            components = list(body.get('components', []))
            components.append({'name': KitManager.merge_names('fluent', cls.set_component),
                               'data': {'value': result}})
            components.append({'name': KitManager.merge_names('fluent', cls.end_component),
                               'data': {}})
            migrated = dict(data)
            migrated['body'] = {'text': text + '\uFFFC\n\uFFFC', 'components': components}
            return super(CReturnMacro, cls).restore(migrated, parent, graphics)
        return super(CReturnMacro, cls).restore(data, parent, graphics)


class CMacroStatement(Component, abstract):
    """
    Base of the statement-level components exclusive to the body of one
    particular ``DEFINE_*`` macro (or one particular context).

    Subclasses declare the metadata, the semantic roles the compilation
    context must provide (``required_roles``) and where the statement may
    appear (``host``: the phrase the context-missing error reads); the
    interface shows the localized display name alone unless a subclass swaps
    in a richer one through ``_interface_cls``, and the archive carries
    nothing by default, since every argument the rendering emits comes from
    the context the enclosing component opens. They stay out of the global
    completion registry: the analyzer suggests them where the hosting
    components provide the roles only (see ``register_context_completion``).
    """

    # Semantic roles the compilation context must provide for the rendering
    requires: ClassVar[tuple[string, ...]] = ()
    # Where the statement may appear, phrased for the context-missing error
    host: ClassVar[string] = ''

    class FMacroStatementInterface(IComponentInterface):
        def __init__(self, owner: typeof['CMacroStatement'], graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_statement = graphics.create_native_label(owner.meta().display_name, self.font)
            graphics.label_metric_width(self.label_statement, modify=True)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_statement, null, null, null)
            self.color = graphics.alloc_color()

        def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:
            # Locate figures and widgets at the UI origin of this interface
            graphics.push_anchor(self.origin)
            try:
                self.layout.update(graphics)

                if painting:
                    size = self.layout.size(graphics)
                    # Box size includes one margin on each side; deduct 2*2.5 so the frame insets 2.5px into margins
                    graphics.disp_draw_rect(QRectF(2.5, 2.5, size.width() - 5, size.height() - 5),
                                            self.color, round_radius=5)
            finally:
                graphics.pop_anchor()

    # The interface class the constructor instantiates: subclasses with extra
    # fields swap it instead of reassigning ``_interface`` after the base
    # construction (the widgets a replaced interface created would leak)
    _interface_cls = FMacroStatementInterface

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        super().__init__(parent, graphics)
        self._interface = type(self)._interface_cls(type(self), graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return null  # No field to enter (or the subclass overrides)

    def editableWidgets(self) -> IList[QWidget]:
        return []

    def __serialize__(self) -> dict:
        return {}

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a macro statement from its serialization (nothing to load by
        default: every argument the rendering emits comes from the compilation
        context).
        """
        maybe_unused(data)
        return cls(parent, graphics)

    @classmethod
    def required_roles(cls) -> tuple[string, ...]:
        """:return: the semantic roles the compilation context must provide."""
        return cls.requires

    @final
    @classmethod
    def _require_context(cls, builder: Compiler) -> void:
        """
        :raise Compiler.CompileError: raise when the compilation context
            provides not every role the statement requires (the statement sits
            outside the body it belongs to)
        """
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        if any(not udf.context_role(builder, role) for role in cls.required_roles()):
            raise Compiler.CompileError(Compiler.B1006,
                                        _('ctx_missing_macro').format(cls.meta().display_name, cls.host))

    def compile(self, builder: Compiler) -> void:
        """
        Emit the statement into the UDF products.
        """
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(type(self).render(serialize(self), builder))


class CSetValueStatement(CMacroStatement, abstract):
    """
    Base of the statements storing the value their host macro returns: the
    interface captions one expression field and the compilation assigns it to
    the auto-named value the host macro opens (``value_role``), without
    returning yet (the host's "end" statement does).
    """

    # Role of the auto-named value the host macro opens
    value_role: ClassVar[string] = ''
    # Caption of the value field
    lt_value: ClassVar[string] = ''

    class FSetValueInterface(CMacroStatement.FMacroStatementInterface):
        def __init__(self, owner: typeof['CSetValueStatement'], graphics: IComponentGraphics):
            super().__init__(owner, graphics)
            label_value = graphics.create_native_label(owner.lt_value, self.font)
            graphics.label_metric_width(label_value, modify=True)
            # The value is an expression context: operators nest, statements never do
            self.edit_value = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 24))
            self.edit_value.filter(ComponentMetadata.Level.Expression)
            self.layout.add_element(label_value, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_value, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)

    _interface_cls = FSetValueInterface

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_value  # The value is the only field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_value]

    def __serialize__(self) -> dict:
        return {
            'value': serialize(self._interface.edit_value)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        require_member(data, 'value')
        component = cls(parent, graphics)
        component._interface.edit_value.load(data['value'])
        return component

    @classmethod
    def required_roles(cls) -> tuple[string, ...]:
        return (cls.value_role,)

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        cls._require_context(builder)
        require_member(data, 'value')
        value = udf.render_edit(data['value'], builder).strip()
        return f'{udf.context_role(builder, cls.value_role)} = {value};'


class CEndMacroStatement(CMacroStatement, abstract):
    """
    Base of the statements ending a returning macro: the compilation returns
    the auto-named value the host macro opens (``value_role``), the one its
    "set" statement stored.
    """

    # Role of the auto-named value the host macro opens
    value_role: ClassVar[string] = ''

    @classmethod
    def required_roles(cls) -> tuple[string, ...]:
        return (cls.value_role,)

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        maybe_unused(data)
        cls._require_context(builder)
        return f'return {udf.context_role(builder, cls.value_role)};'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('adjust', _('adjust_display_name'), _('adjust_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CAdjust(CFluentMacro):
    """``DEFINE_ADJUST(name, d)``: general-purpose UDF called by Fluent at the
    end of every iteration; ``d`` names the ``Domain *`` parameter."""
    macro = 'DEFINE_ADJUST'
    args_spec = (MacroArgument(_('label_domain'), 'd', role='domain'), )
    completion_keyword = 'adjust'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('init', _('init_display_name'), _('init_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CInit(CFluentMacro):
    """``DEFINE_INIT(name, d)``: UDF called once right after the flow field is
    initialized; ``d`` names the ``Domain *`` parameter."""
    macro = 'DEFINE_INIT'
    args_spec = (MacroArgument(_('label_domain'), 'd', role='domain'), )
    completion_keyword = 'init'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('execute_at_end', _('execute_at_end_display_name'), _('execute_at_end_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CExecuteAtEnd(CFluentMacro):
    """``DEFINE_EXECUTE_AT_END(name)``: UDF called after the calculation
    (or each time step) completes; it takes no parameters."""
    macro = 'DEFINE_EXECUTE_AT_END'
    completion_keyword = 'at_end'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('on_demand', _('on_demand_display_name'), _('on_demand_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class COnDemand(CFluentMacro):
    """``DEFINE_ON_DEMAND(name)``: UDF invoked manually by the user through
    Execute on Demand; it takes no parameters."""
    macro = 'DEFINE_ON_DEMAND'
    completion_keyword = 'on_demand'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('rw_file', _('rw_file_display_name'), _('rw_file_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CRwFile(CFluentMacro):
    """``DEFINE_RW_FILE(name, fp)``: UDF writing user data to, or reading it
    back from, case/data files; ``fp`` names the ``FILE *`` parameter."""
    macro = 'DEFINE_RW_FILE'
    args_spec = ((_('label_fp'), 'fp'), )
    completion_keyword = 'rw_file'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('deltat', _('deltat_display_name'), _('deltat_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDeltaT(CReturnMacro):
    """``DEFINE_DELTAT(name, d)``: UDF supplying the adaptive time step size
    for the next time step; ``d`` names the ``Domain *`` parameter.

    The value the function returns stays out of the interface: the
    compilation picks an available identifier for it and declares it
    zero-initialized. The body stores it through "set deltat" and ends with
    "end DEFINE_DELTAT" (see the statements below), so non-programmer users
    never name the quantity nor write the return themselves."""
    macro = 'DEFINE_DELTAT'
    args_spec = (MacroArgument(_('label_domain'), 'd', role='domain'), )
    completion_keyword = 'deltat'
    value_base = 'deltat'
    value_role = 'deltat_value'
    set_component = 'set_deltat'
    end_component = 'end_deltat'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('set_deltat', _('set_deltat_display_name'), _('set_deltat_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CSetDeltat(CSetValueStatement):
    """Store the adaptive time step size ``DEFINE_DELTAT`` returns: compiles
    into an assignment to the auto-named value the macro declares (no
    immediate ``return``)."""
    value_role = 'deltat_value'
    lt_value = _('label_deltat_value')
    host = _('ctx_inside_deltat')


@fluent.register
@Component.use__interface
@ComponentMetadata.create('end_deltat', _('end_deltat_display_name'), _('end_deltat_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CEndDeltat(CEndMacroStatement):
    """End the ``DEFINE_DELTAT`` body: compiles into ``return`` of the
    auto-named value the macro declares (the one "set deltat" stores)."""
    value_role = 'deltat_value'
    host = _('ctx_inside_deltat')


@fluent.register
@Component.use__interface
@ComponentMetadata.create('execute_from_gui', _('from_gui_display_name'), _('from_gui_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CExecuteFromGui(CFluentMacro):
    """``DEFINE_EXECUTE_FROM_GUI(name, msg)``: UDF invoked from a user-defined
    GUI panel; ``msg`` names the ``int`` message-code parameter."""
    macro = 'DEFINE_EXECUTE_FROM_GUI'
    args_spec = ((_('label_msg'), 'msg'), )
    completion_keyword = 'from_gui'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('translation_unit', _('translation_unit_display_name'), _('translation_unit_description'),
                          [UDF], level=ComponentMetadata.Level.Domain)
class CTranslationUnit(Component):
    """
    A C translation unit: the document root of a UDF script.

    The unit hosts the ``DEFINE_*`` macros and free C declarations (globals,
    ``typedef``s, helper functions) in one whole-page visual code edit, and
    compiles into one UDF source fragment starting with ``#include "udf.h"``.
    """

    # Margin left around the unit inside the canvas' client rectangle
    Margin: Final[float] = 10.

    class FUnitInterface(IComponentInterface):
        def __init__(self, owner: typeof['CTranslationUnit'], graphics: IComponentGraphics):
            super().__init__(graphics)
            maybe_unused(owner)
            margin = CTranslationUnit.Margin
            # Non-positive extents stretch the edit to the canvas edges minus the
            # margin (see EditionCanvas.translate_rect): the unit fills the client
            # rectangle of the canvas
            self.edit_body = graphics.create_visual_code_edit(QRectF(margin, margin, -margin, -margin))
            # A translation unit hosts the Domain-level DEFINE_* macros
            self.edit_body.filter(ComponentMetadata.Level.Domain)
            self.color = graphics.alloc_color()

        def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:
            # Locate figures and widgets at the UI origin of this interface
            graphics.push_anchor(self.origin)
            try:
                client = graphics.client_rect
                margin = CTranslationUnit.Margin
                # Never shrink below the client rectangle; growing contents still
                # extend the edit (and scroll the whole page)
                self.edit_body.setBasicHeight(int(max(client.height() - 2 * margin, 0.)))

                if painting:
                    graphics.disp_draw_frame(QRectF(margin, margin, client.width() - 2 * margin,
                                                    client.height() - 2 * margin),
                                             self.color, round_radius=5)
            finally:
                graphics.pop_anchor()

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        super().__init__(parent, graphics)
        self._interface = CTranslationUnit.FUnitInterface(type(self), graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_body

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_body]

    def __serialize__(self) -> dict:
        return {
            'body': serialize(self._interface.edit_body)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a translation unit from its serialization.

        The constructor reconstructs the interface (whose edit is empty); the
        archived contents are then loaded into that edit in place, since its
        reference is held by the interface.
        """
        require_member(data, 'body')
        component = cls(parent, graphics)
        component._interface.edit_body.load(data['body'])
        return component

    def compile(self, builder: Compiler) -> void:
        """
        Emit the whole UDF source file: the required ``#include "udf.h"``
        followed by the rendered contents of the unit (macros and free C),
        preserving their order in the document.
        """
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        data = serialize(self._interface.edit_body)
        # Reject illegal identifiers before any rendering happens, so the build
        # reports every problem the components carry (listed at the bottom)
        udf.validate_unit(data, builder)
        # Lift the declarations of the auto variables before rendering consumes
        # the very same archive (the analysis keys blocks by archive identity)
        udf.analyze_scope(data, builder)
        body = udf.render_unit(data, builder).strip()
        # The rendered body should survive a real C compilation against udf.h:
        # check it against the stub and record a B1007 warning when it does not
        udf.check_product(body, builder)
        source = '#include "udf.h"'
        if body:
            source += f'\n\n{body}'
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(source)


# Description of the macro parameters in the popup detail pane
lt_macro_param: Final[string] = _('desc_macro_param')


def _macro_parameters(component: Component) -> IList[Completion]:
    """The identifiers the macro's parameters declare: variables of the macro's
    own scope (they never leave the function the macro defines). Parameters
    conventionally subscripted (``index`` in the specification) contribute the
    subscripted form (``dS[eqn]``): the UDF guide only uses that form."""
    if not isinstance(component, CFluentMacro):
        return []
    introduced: IList[Completion] = []
    visible = [argument for argument in type(component).arguments() if not argument.hidden]
    for argument, edit in zip(visible, component.interface.arg_edits):
        name = edit.text().strip()
        if name:
            keyword = f'{name}[{argument.index}]' if argument.index else name
            introduced.append(Completion(keyword=keyword,
                                         kind=ComponentMetadata.Kind.Variable,
                                         visibility='scoped',
                                         description=lt_macro_param))
    return introduced


# Mark the DEFINE_* macro components as macro-kind (completion glyph) and contribute
# their completion keywords to the global registry, so any visual code edit picks
# them up (filtered by level)
for _comp in (CAdjust, CInit, CExecuteAtEnd, COnDemand, CRwFile, CDeltaT, CExecuteFromGui):
    _comp.meta().kind = ComponentMetadata.Kind.Macro
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))

# The deltat statements compile inside DEFINE_DELTAT bodies only: they never
# join the global completion registry; the analyzer suggests them where the
# hosting components provide the roles they require (see register_context_completion)
register_context_completion(Completion(keyword='set_deltat',
                                       component_name=KitManager.merge_names('fluent', 'set_deltat'),
                                       description=CSetDeltat.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CSetDeltat.required_roles())
register_context_completion(Completion(keyword='end_deltat',
                                       component_name=KitManager.merge_names('fluent', 'end_deltat'),
                                       description=CEndDeltat.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CEndDeltat.required_roles())

# Contribute the parameters the macros declare to the scope analysis, so the
# bodies of the macros complete them (the registration is idempotent, so the
# sibling macro modules sharing this import never double it)
register_scope_contributor(_macro_parameters)
