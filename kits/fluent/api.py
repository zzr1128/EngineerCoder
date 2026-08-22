# -*- coding: utf-8 -*-
"""
The Ansys Fluent UDF API in the kit: every helper macro the solver offers
becomes a component (the solver constants, the context-aware field accessors,
and the remaining calls captioning the arguments the context cannot supply).

Field access in UDF happens through function-like macros (``C_T(c, t)``,
``F_U(f, t)``...) that no ``DEFINE_*`` macro wraps. The argument-less
quantities (``CURRENT_TIME``, ``ND_ND``...) become components
(``CFluentConstant``): the interface shows the localized quantity name alone
and the rendering emits the macro name verbatim, so they compile (and
complete) at any position.

The cell field accessors taking the cell and its thread alone (``C_T``,
``C_P``...) become components (``CFluentCellAccess``): the interface shows
the localized quantity name only, and the compilation resolves the cell and
the thread through the compilation context (see ``ContextKey`` in
``kits.fluent.udf``). They therefore complete inside components providing a
cell and a thread only (see ``register_context_completion``), never at a
contextless position. Every other helper macro becomes a component too (``CApiCall``): the
interface captions one expression field per argument the context cannot
supply (a vector to fill, an entry index, a message...), and the rendering
materializes the call resolving the remaining arguments through the
compilation context exactly like the field accessors do. Snippets therefore
no longer take part: the kit contributes components exclusively.

The last parameter a source term carries is the equation index, not the
phase the source applies to: the ``CPhaseIndex`` component retrieves the
phase index through the ``PHASE_INDEX`` macro (with the thread the
compilation context provides), completing where a thread is in scope.
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget

from alias import *
from core.build import Compiler
from core.completer import Completion
from core.component import Component, ComponentMetadata, IComponentInterface
from core.graphics import IComponentGraphics
from core.kit import KitManager
from kits.common.library import CLLibrary
from kits.fluent.analyzer import register_context_completion
from kits.fluent.fluent import UDF, fluent
from kits.fluent.general import CMacroStatement
from kits.fluent.localization import _

# The symbol kinds of the API categories: data access (variable reads,
# geometry info, dimensionality parameters) shows the type glyph, callable
# helpers (vector algebra, reductions, UDM, messaging, lookup) the function
# glyph, the solver state accessors the parameter glyph
_DataAccess: Final[ComponentMetadata.Kind] = ComponentMetadata.Kind.Type
_Function: Final[ComponentMetadata.Kind] = ComponentMetadata.Kind.Function
_Parameter: Final[ComponentMetadata.Kind] = ComponentMetadata.Kind.Parameter

class CFluentConstant(Component, abstract):
    """
    Base of the argument-less API quantity components (the solver constants:
    ``CURRENT_TIME``, ``ND_ND``...).

    The constants take no argument at all: the interface shows the localized
    quantity name alone and the rendering emits the macro name verbatim, so
    they compile at any position; the archive carries nothing. Subclasses
    needing extra fields swap in a richer interface through ``_interface_cls``.
    """

    # The API macro as it appears in the generated source
    macro: ClassVar[string] = ''

    class FConstantInterface(IComponentInterface):
        def __init__(self, owner: typeof['CFluentConstant'], graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            # The quantity name alone surfaces: the rendering emits it verbatim
            # (or resolves the remaining arguments through the context)
            self.label_quantity = graphics.create_native_label(owner.meta().display_name, self.font)
            graphics.label_metric_width(self.label_quantity, modify=True)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_quantity, null, null, null)
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
    _interface_cls = FConstantInterface

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        super().__init__(parent, graphics)
        self._interface = type(self)._interface_cls(type(self), graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return null  # No field to fill (or the subclass overrides)

    def editableWidgets(self) -> IList[QWidget]:
        return []

    def __serialize__(self) -> dict:
        return {}

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore an API quantity from its serialization (nothing to load by
        default: the rendering emits the macro name verbatim).
        """
        maybe_unused(data)
        return cls(parent, graphics)

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the quantity into the macro name itself (no argument to supply).
        """
        maybe_unused(data, builder)
        return cls.macro

    def compile(self, builder: Compiler) -> void:
        """
        Emit the quantity into the UDF products.
        """
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(type(self).render(serialize(self), builder))


class CApiCall(CFluentConstant, abstract):
    """
    Base of the API helper macros whose arguments the context cannot supply
    in full (a vector to fill, an entry index, a message...): the interface
    captions one expression field per field entry of ``arg_spec``, and the
    rendering materializes the call from it, resolving the role entries
    through the compilation context and emitting the literal entries verbatim.

    ``arg_spec`` entries are one of:

    - ``('field', caption, width)``: an expression field the user fills,
      captioned by the localized ``caption``; an optional fourth element
      names the locale key of a placeholder hint the empty field shows;
    - ``('role', role)``: an identifier the compilation context provides,
      missing ones raise like the plain cell accessors do;
    - ``('literal', text)``: fixed text emitted verbatim.

    Subclasses declare the metadata, the macro name, the specification, and
    where the call may appear (``host``: the phrase the context-missing error
    reads); the archive carries the field contents under ``fields`` (absent
    when the specification carries no field entry).
    """

    # Declarative argument specification of the rendered call
    arg_spec: ClassVar[tuple[tuple, ...]] = ()
    # Where the call may appear, phrased for the context-missing error
    host: ClassVar[string] = ''

    class FCallInterface(CFluentConstant.FConstantInterface):
        def __init__(self, owner: typeof['CApiCall'], graphics: IComponentGraphics):
            super().__init__(owner, graphics)
            # Every field entry becomes one captioned expression edit; labels
            # and edits glue into the row the quantity name opens (NoBreak)
            self.field_edits: IList[Any] = []
            for entry in owner.arg_spec:
                if entry[0] != 'field':
                    continue
                label = graphics.create_native_label(_(entry[1]), self.font)
                graphics.label_metric_width(label, modify=True)
                edit = graphics.create_visual_code_edit(QRectF(0, 0, entry[2], 24))
                # A call argument is an expression context: operators nest, statements never do
                edit.filter(ComponentMetadata.Level.Expression)
                if len(entry) > 3:
                    edit.setPlaceholderText(_(entry[3]))
                self.layout.add_element(label, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
                self.layout.add_element(edit, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        null, null, graphics=graphics)
                self.field_edits.append(edit)

    _interface_cls = FCallInterface

    def autoFocusWidget(self) -> Nullable[QWidget]:
        edits = self._interface.field_edits
        return edits[0] if edits else null

    def editableWidgets(self) -> IList[QWidget]:
        return list(self._interface.field_edits)

    @classmethod
    def _field_count(cls) -> int:
        """:return: how many field entries the argument specification carries."""
        return sum(1 for entry in cls.arg_spec if entry[0] == 'field')

    @classmethod
    def required_roles(cls) -> tuple[string, ...]:
        """:return: the semantic roles the compilation context must provide."""
        return tuple(entry[1] for entry in cls.arg_spec if entry[0] == 'role')

    def __serialize__(self) -> dict:
        count = type(self)._field_count()
        return {'fields': [serialize(edit) for edit in self._interface.field_edits]} if count else {}

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        count = cls._field_count()
        component = cls(parent, graphics)
        if count:
            require_member(data, 'fields')
            require_type(data['fields'], list, 'fields')
            if len(data['fields']) != count:
                raise SerializationError(f'{cls.meta().name} expects {count} field(s), '
                                         f'got {len(data["fields"])}')
            for edit, field in zip(component._interface.field_edits, data['fields']):
                edit.load(field)
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the call into the macro invocation: field entries render their
        archived contents, role entries resolve through the compilation
        context, literal entries emit verbatim.
        :raise Compiler.CompileError: raise when the context provides not
            every role the specification requires (the call sits outside any
            matching context)
        """
        from kits.fluent import udf  # Deferred: udf.py and api.py share the kit entry chain

        count = cls._field_count()
        fields = data.get('fields', []) if count else []
        parts: IList[string] = []
        index = 0
        for entry in cls.arg_spec:
            if entry[0] == 'field':
                parts.append(udf.render_edit(fields[index], builder).strip())
                index += 1
            elif entry[0] == 'role':
                identifier = udf.context_role(builder, entry[1])
                if not identifier:
                    raise Compiler.CompileError(Compiler.B1006,
                                                _('ctx_missing_macro').format(cls.meta().display_name, cls.host))
                parts.append(identifier)
            else:
                parts.append(entry[1])
        return f'{cls.macro}({", ".join(parts)})'


class CFluentCellAccess(CFluentConstant, abstract):
    """
    Base of the context-aware cell field accessors (``C_T``, ``C_P``...).

    The accessors free non-programmer users from the arguments the field
    access macros take: the interface shows the localized quantity name alone
    (no cell, no thread), and the compilation resolves both through the
    compilation context the enclosing components open (see ``ContextKey`` in
    ``kits.fluent.udf``). They therefore compile inside components providing
    the 'cell' and 'thread' roles only, and the analyzer suggests them there
    exclusively (see ``register_context_completion``); the archive carries
    nothing.
    """

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the accessor into the macro call with the cell and the thread
        the compilation context provides (``MACRO(cell, thread)``).
        :raise Compiler.CompileError: raise when the context provides no cell
            or no thread (the accessor sits outside any cell context)
        """
        from kits.fluent import udf  # Deferred: udf.py and api.py share the kit entry chain

        maybe_unused(data)
        cell = udf.context_role(builder, 'cell')
        thread = udf.context_role(builder, 'thread')
        if not cell or not thread:
            raise Compiler.CompileError(Compiler.B1006,
                                        _('ctx_missing_macro').format(cls.meta().display_name,
                                                                      _('ctx_cell_thread_place')))
        return f'{cls.macro}({cell}, {thread})'


class CFluentIndexedAccess(CFluentConstant, abstract):
    """
    Base of the context-aware accessors subscripted with an index the context
    cannot supply (``C_UDMI``): the interface carries one index field on top
    of the quantity name; the cell and the thread resolve through the
    compilation context as the plain cell accessors do.
    """

    class FIndexedAccessInterface(CFluentConstant.FConstantInterface):
        lt_index: Final[string] = _('label_index')

        def __init__(self, owner: typeof['CFluentIndexedAccess'], graphics: IComponentGraphics):
            super().__init__(owner, graphics)
            label_index = graphics.create_native_label(self.lt_index, self.font)
            graphics.label_metric_width(label_index, modify=True)
            # The index is an expression context: operators nest, statements never do
            self.edit_index = graphics.create_visual_code_edit(QRectF(0, 0, 60, 24))
            self.edit_index.filter(ComponentMetadata.Level.Expression)
            self.layout.add_element(label_index, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_index, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    null, null, graphics=graphics)

    _interface_cls = FIndexedAccessInterface

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_index  # The index is the only field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_index]

    def __serialize__(self) -> dict:
        return {
            'index': serialize(self._interface.edit_index)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        require_member(data, 'index')
        component = cls(parent, graphics)
        component._interface.edit_index.load(data['index'])
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the accessor into the macro call with the cell and the thread
        the compilation context provides and the index the field carries
        (``MACRO(cell, thread, index)``).
        :raise Compiler.CompileError: raise when the context provides no cell
            or no thread (the accessor sits outside any cell context)
        """
        from kits.fluent import udf  # Deferred: udf.py and api.py share the kit entry chain

        require_member(data, 'index')
        cell = udf.context_role(builder, 'cell')
        thread = udf.context_role(builder, 'thread')
        if not cell or not thread:
            raise Compiler.CompileError(Compiler.B1006,
                                        _('ctx_missing_macro').format(cls.meta().display_name,
                                                                      _('ctx_cell_thread_place')))
        index = udf.render_edit(data['index'], builder).strip()
        return f'{cls.macro}({cell}, {thread}, {index})'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('c_udmi', _('c_udmi_display'), _('api_c_udmi'), [UDF],
                          level=ComponentMetadata.Level.Expression,
                          kind=ComponentMetadata.Kind.Function)
class CUdmi(CFluentIndexedAccess):
    """Read one entry of the cell user-defined memory: ``C_UDMI(c, t, i)``
    with the cell and the thread the compilation context provides; the index
    of the entry is the only field the interface carries."""
    macro = 'C_UDMI'


class CSetAccessAssignment(CMacroStatement, abstract):
    """
    Base of the statements writing a quantity through its accessor macro: the
    accessors that serve as lvalues (``C_PROFILE``, ``F_UDMI``, ``C_T``...)
    become assignment statements the body of a matching context hosts. The
    interface captions the value field (plus the entry index when the macro
    takes one), and the compilation renders ``MACRO(context..., index) =
    value;`` resolving the context roles exactly like the reading accessors
    do; the archive carries the value (and the index when present).
    """

    # The accessor macro the statement assigns through, as it appears in the
    # generated source
    macro: ClassVar[string] = ''
    # Whether the macro takes the entry index the interface captions
    indexed: ClassVar[bool] = False

    class FSetAccessInterface(CMacroStatement.FMacroStatementInterface):
        lt_index: Final[string] = _('label_index')
        lt_value: Final[string] = _('label_value')

        def __init__(self, owner: typeof['CSetAccessAssignment'], graphics: IComponentGraphics):
            super().__init__(owner, graphics)
            if owner.indexed:
                label_index = graphics.create_native_label(self.lt_index, self.font)
                graphics.label_metric_width(label_index, modify=True)
                # The index is an expression context: operators nest, statements never do
                self.edit_index = graphics.create_visual_code_edit(QRectF(0, 0, 60, 24))
                self.edit_index.filter(ComponentMetadata.Level.Expression)
                self.layout.add_element(label_index, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
                self.layout.add_element(self.edit_index, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        null, null, graphics=graphics)
            label_value = graphics.create_native_label(self.lt_value, self.font)
            graphics.label_metric_width(label_value, modify=True)
            # The value is an expression context: operators nest, statements never do
            self.edit_value = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 24))
            self.edit_value.filter(ComponentMetadata.Level.Expression)
            self.layout.add_element(label_value, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_value, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)

    _interface_cls = FSetAccessInterface

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_index if type(self).indexed else self._interface.edit_value

    def editableWidgets(self) -> IList[QWidget]:
        if type(self).indexed:
            return [self._interface.edit_index, self._interface.edit_value]
        return [self._interface.edit_value]

    def __serialize__(self) -> dict:
        data: IDictionary[string, Any] = {}
        if type(self).indexed:
            data['index'] = serialize(self._interface.edit_index)
        data['value'] = serialize(self._interface.edit_value)
        return data

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        if cls.indexed:
            require_member(data, 'index', 'value')
        else:
            require_member(data, 'value')
        component = cls(parent, graphics)
        if cls.indexed:
            component._interface.edit_index.load(data['index'])
        component._interface.edit_value.load(data['value'])
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the statement into the assignment through the accessor macro,
        resolving the context roles the reading accessor resolves too.
        :raise Compiler.CompileError: raise when the context provides not
            every role the statement requires
        """
        from kits.fluent import udf  # Deferred: udf.py and api.py share the kit entry chain

        cls._require_context(builder)
        require_member(data, 'value')
        parts: IList[string] = [udf.context_role(builder, role) for role in cls.requires]
        if cls.indexed:
            require_member(data, 'index')
            parts.append(udf.render_edit(data['index'], builder).strip())
        value = udf.render_edit(data['value'], builder).strip()
        return f'{cls.macro}({", ".join(parts)}) = {value};'


# The accessors that serve as lvalues: each becomes an assignment statement
# the body of a matching context hosts (C_UDMI keeps its historical name
# 'set_udmi'). The completion keywords read as the setting counterpart of the
# reading accessor (the macro name stays the rendered source).
# (keyword, meta name, macro, indexed, required roles, host phrase key)
_SetAccessors: Final[tuple[tuple[string, string, string, bool, tuple, string], ...]] = (
    ('set_udmi', 'set_udmi', 'C_UDMI', True, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_user_scalar', 'set_cell_user_scalar', 'C_UDSI', True, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_profile', 'set_cell_profile', 'C_PROFILE', True, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_face_profile', 'set_face_profile', 'F_PROFILE', True, ('face', 'thread'), 'ctx_face_thread_place'),
    ('set_face_user_memory', 'set_face_user_memory', 'F_UDMI', True, ('face', 'thread'), 'ctx_face_thread_place'),
    ('set_cell_volume_fraction', 'set_cell_volume_fraction', 'C_VOF', True, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_temperature', 'set_cell_temperature', 'C_T', False, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_pressure', 'set_cell_pressure', 'C_P', False, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_x_velocity', 'set_cell_x_velocity', 'C_U', False, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_y_velocity', 'set_cell_y_velocity', 'C_V', False, ('cell', 'thread'), 'ctx_cell_thread_place'),
    ('set_cell_z_velocity', 'set_cell_z_velocity', 'C_W', False, ('cell', 'thread'), 'ctx_cell_thread_place'),
)

for _keyword, _name, _macro, _indexed, _requires, _host_key in _SetAccessors:
    # The base carries ABCMeta (the ``abstract`` marker): the derived classes
    # must be created through it, or the metaclasses conflict
    _assignment = type(CSetAccessAssignment)(f'C{_name.replace("_", " ").title().replace(" ", "")}Assignment',
                                             (CSetAccessAssignment,),
                                             {'macro': _macro, 'indexed': _indexed,
                                              'requires': _requires, 'host': _(_host_key)})
    _assignment = ComponentMetadata.create(_name, _(f'{_name}_display_name'), _(f'{_name}_description'), [UDF],
                                           level=ComponentMetadata.Level.Statement,
                                           kind=ComponentMetadata.Kind.Function)(_assignment)
    _assignment = Component.use__interface(_assignment)
    fluent.register(_assignment)
    # Context-gated completion: the assignment completes where the context
    # provides every role it resolves, and never elsewhere
    register_context_completion(Completion(keyword=_keyword,
                                           component_name=KitManager.merge_names('fluent', _name),
                                           description=_(f'{_name}_description'),
                                           kind=ComponentMetadata.Kind.Function),
                                _requires)


# The cell field accessors taking the cell and its thread alone: they become
# context-aware components so non-programmer users never touch the arguments.
# The completion keywords read as self-explanatory names of the quantities
# (the macro names stay the rendered source and the archive names).
# (keyword, meta name, locale key of the display name, macro)
_CellAccessors: Final[tuple[tuple[string, string, string, string], ...]] = (
    ('cell_temperature', 'c_t', 'c_t_display', 'C_T'),
    ('cell_pressure', 'c_p', 'c_p_display', 'C_P'),
    ('cell_x_velocity', 'c_u', 'c_u_display', 'C_U'),
    ('cell_y_velocity', 'c_v', 'c_v_display', 'C_V'),
    ('cell_z_velocity', 'c_w', 'c_w_display', 'C_W'),
    ('cell_density', 'c_r', 'c_r_display', 'C_R'),
    ('cell_laminar_viscosity', 'c_mu_l', 'c_mu_l_display', 'C_MU_L'),
    ('cell_turbulent_viscosity', 'c_mu_t', 'c_mu_t_display', 'C_MU_T'),
    ('cell_laminar_conductivity', 'c_k_l', 'c_k_l_display', 'C_K_L'),
    ('cell_thermal_conductivity', 'c_k', 'c_k_display', 'C_K'),
    ('cell_specific_heat', 'c_cp', 'c_cp_display', 'C_CP'),
    ('cell_temperature_gradient', 'c_t_g', 'c_t_g_display', 'C_T_G'),
    ('cell_pressure_gradient', 'c_p_g', 'c_p_g_display', 'C_P_G'),
    ('cell_turbulence_dissipation', 'c_eps', 'c_eps_display', 'C_EPS'),
    ('cell_specific_dissipation', 'c_omega', 'c_omega_display', 'C_OMEGA'),
    ('cell_volume', 'c_volume', 'c_volume_display', 'C_VOLUME'),
)

for _keyword, _name, _display_key, _macro in _CellAccessors:
    # The base carries ABCMeta (the ``abstract`` marker): the derived classes
    # must be created through it, or the metaclasses conflict
    _accessor = type(CFluentCellAccess)(f'C{_name.replace("_", " ").title().replace(" ", "")}CellAccess',
                                        (CFluentCellAccess,), {'macro': _macro})
    _accessor = ComponentMetadata.create(_name, _(_display_key), _(f'api_{_name}'), [UDF],
                                         level=ComponentMetadata.Level.Expression,
                                         kind=ComponentMetadata.Kind.Type)(_accessor)
    _accessor = Component.use__interface(_accessor)
    fluent.register(_accessor)
    # Context-gated completion: the accessor completes where a cell and its
    # thread are in scope, and never elsewhere
    register_context_completion(Completion(keyword=_keyword,
                                           component_name=KitManager.merge_names('fluent', _name),
                                           description=_(f'api_{_name}'),
                                           kind=ComponentMetadata.Kind.Type),
                                ('cell', 'thread'))

# The solver constants take no argument at all: they become components whose
# rendering emits the macro name verbatim, completing at any position.
# (keyword, meta name, locale key of the description, macro, symbol kind)
_Constants: Final[tuple[tuple[string, string, string, string, ComponentMetadata.Kind], ...]] = (
    ('CURRENT_TIMESTEP', 'current_timestep', 'api_current_timestep', 'CURRENT_TIMESTEP', _Parameter),
    ('CURRENT_TIME', 'current_time', 'api_current_time', 'CURRENT_TIME', _Parameter),
    ('PREVIOUS_TIME', 'previous_time', 'api_previous_time', 'PREVIOUS_TIME', _Parameter),
    ('RP_2D', 'rp_2d', 'api_rp_2d', 'RP_2D', _DataAccess),
    ('RP_3D', 'rp_3d', 'api_rp_3d', 'RP_3D', _DataAccess),
    ('ND_ND', 'nd_nd', 'api_nd_nd', 'ND_ND', _DataAccess),
)

for _keyword, _name, _desc_key, _macro, _kind in _Constants:
    # The base carries ABCMeta (the ``abstract`` marker): the derived classes
    # must be created through it, or the metaclasses conflict
    _constant = type(CFluentConstant)(f'C{_name.replace("_", " ").title().replace(" ", "")}Constant',
                                      (CFluentConstant,), {'macro': _macro})
    _constant = ComponentMetadata.create(_name, _(f'{_name}_display'), _(_desc_key), [UDF],
                                         level=ComponentMetadata.Level.Expression,
                                         kind=_kind)(_constant)
    _constant = Component.use__interface(_constant)
    fluent.register(_constant)
    # The constants take no argument: they complete at any position (the level
    # filter of each edit decides where they surface)
    KitManager.instance().add_completion(_keyword, KitManager.merge_names('fluent', _name))

# The helper macros taking arguments the context cannot supply: they become
# components captioning one expression field per such argument. The ones whose
# remaining arguments the context resolves complete where those roles are in
# scope only; the rest complete at any position.
# (keyword, meta name, macro, symbol kind, argument specification, host phrase
#  key for the context-missing error)
_ApiCalls: Final[tuple[tuple[string, string, string, ComponentMetadata.Kind, tuple, string], ...]] = (
    # Cell-based helpers taking a vector to fill on top of the cell and its thread
    ('cell_centroid', 'c_centroid', 'C_CENTROID', _DataAccess,
     (('field', 'label_vector', 60), ('role', 'cell'), ('role', 'thread')), 'ctx_cell_thread_place'),
    # Faces and nodes of a cell (inside c_face_loop/c_node_loop)
    ('cell_face', 'c_face', 'C_FACE', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    ('cell_face_thread', 'c_face_thread', 'C_FACE_THREAD', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    ('cell_node', 'c_node', 'C_NODE', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    # Cell-based indexed access (user scalars, phase fraction, species fraction)
    ('cell_user_scalar', 'c_udsi', 'C_UDSI', _Function,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    ('cell_user_scalar_gradient', 'c_udsi_g', 'C_UDSI_G', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    ('cell_volume_fraction', 'c_vof', 'C_VOF', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    ('cell_mass_fraction', 'c_yi', 'C_YI', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    # Face-based field access (the keywords read as self-explanatory names of
    # the quantities, like the cell accessors do)
    ('face_temperature', 'f_t', 'F_T', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_pressure', 'f_p', 'F_P', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_x_velocity', 'f_u', 'F_U', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_y_velocity', 'f_v', 'F_V', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_z_velocity', 'f_w', 'F_W', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_centroid', 'f_centroid', 'F_CENTROID', _DataAccess,
     (('field', 'label_vector', 60, 'placeholder_symbol'), ('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_user_memory', 'f_udmi', 'F_UDMI', _Function,
     (('role', 'face'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_face_thread_place'),
    ('face_profile', 'f_profile', 'F_PROFILE', _DataAccess,
     (('role', 'face'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_face_thread_place'),
    ('cell_profile', 'c_profile', 'C_PROFILE', _DataAccess,
     (('role', 'cell'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_cell_thread_place'),
    ('face_area', 'f_area', 'F_AREA', _DataAccess,
     (('field', 'label_vector', 60), ('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_flux', 'f_flux', 'F_FLUX', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_phase_mass_flux', 'f_flux_i', 'F_FLUX_I', _DataAccess,
     (('role', 'face'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_face_thread_place'),
    ('face_volume_fraction', 'f_vof', 'F_VOF', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_mass_fraction', 'f_yi', 'F_YI', _DataAccess,
     (('role', 'face'), ('role', 'thread'), ('field', 'label_index', 60)), 'ctx_face_thread_place'),
    ('face_density', 'f_rho', 'F_RHO', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_cell_below', 'f_c0', 'F_C0', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    ('face_cell_above', 'f_c1', 'F_C1', _DataAccess, (('role', 'face'), ('role', 'thread')), 'ctx_face_thread_place'),
    # Vector algebra helpers (context-free: the operands are plain expressions)
    ('NV_V', 'nv_v', 'NV_V', _Function,
     (('field', 'label_vector', 60), ('field', 'label_expression', 90)), ''),
    ('NV_VV', 'nv_vv', 'NV_VV', _Function,
     (('field', 'label_vec_a', 60), ('literal', '='), ('field', 'label_vec_b', 60),
      ('literal', '+'), ('field', 'label_vec_c', 60)), ''),
    ('NV_MAG', 'nv_mag', 'NV_MAG', _Function, (('field', 'label_vector', 60),), ''),
    ('NV_DOT', 'nv_dot', 'NV_DOT', _Function,
     (('field', 'label_vec_a', 60), ('field', 'label_vec_b', 60)), ''),
    # Parallel reductions (host/node communication)
    ('PRF_GIHIGH1', 'prf_gihigh1', 'PRF_GIHIGH1', _Function, (('field', 'label_value', 60),), ''),
    ('PRF_GRSUM1', 'prf_grsum1', 'PRF_GRSUM1', _Function, (('field', 'label_value', 60),), ''),
    # User memory management
    ('FL_MALLOC', 'fl_malloc', 'FL_MALLOC', _Function, (('field', 'label_size', 60),), ''),
    ('FL_FREE', 'fl_free', 'FL_FREE', _Function, (('field', 'label_ptr', 60),), ''),
    # Solver interaction
    ('Message', 'message', 'Message', _Function, (('field', 'label_message', 120),), ''),
    ('Lookup_Thread', 'lookup_thread', 'Lookup_Thread', _Function,
     (('role', 'domain'), ('field', 'label_thread_id', 60)), 'ctx_domain_place'),
    ('THREAD_ID', 'thread_id', 'THREAD_ID', _Parameter, (('role', 'thread'),), 'ctx_thread_place'),
    ('THREAD_TYPE', 'thread_type', 'THREAD_TYPE', _Parameter, (('role', 'thread'),), 'ctx_thread_place'),
    ('thread_sub_thread', 'thread_sub_thread', 'THREAD_SUB_THREAD', _DataAccess,
     (('role', 'thread'), ('field', 'label_index', 60)), 'ctx_thread_place'),
)

for _keyword, _name, _macro, _kind, _spec, _host_key in _ApiCalls:
    # The base carries ABCMeta (the ``abstract`` marker): the derived classes
    # must be created through it, or the metaclasses conflict
    _attributes = {'macro': _macro, 'arg_spec': _spec}
    if _host_key:
        _attributes['host'] = _(_host_key)
    _call = type(CApiCall)(f'C{_name.replace("_", " ").title().replace(" ", "")}Call',
                           (CApiCall,), _attributes)
    _call = ComponentMetadata.create(_name, _(f'{_name}_display'), _(f'api_{_name}'), [UDF],
                                     level=ComponentMetadata.Level.Expression,
                                     kind=_kind)(_call)
    _call = Component.use__interface(_call)
    fluent.register(_call)
    if _call.required_roles():
        # Context-gated completion: the call completes where the context
        # provides every role its specification resolves, and never elsewhere
        register_context_completion(Completion(keyword=_keyword,
                                               component_name=KitManager.merge_names('fluent', _name),
                                               description=_(f'api_{_name}'),
                                               kind=_kind),
                                    _call.required_roles())
    else:
        # Context-free helpers complete at any position (the level filter of
        # each edit decides where they surface)
        KitManager.instance().add_completion(_keyword, KitManager.merge_names('fluent', _name))

# The phase index a multiphase setup numbers its phases with is not the
# equation index a source term carries: the component retrieves it through
# the PHASE_INDEX macro with the thread the compilation context provides,
# completing where a thread is in scope
@fluent.register
@Component.use__interface
@ComponentMetadata.create('phase_index', _('phase_index_display'), _('api_phase_index'), [UDF],
                          level=ComponentMetadata.Level.Expression,
                          kind=_Parameter)
class CPhaseIndex(CFluentConstant):
    """The index of the phase the current thread belongs to (``0`` for the
    primary phase): renders ``PHASE_INDEX(thread)`` with the thread the
    compilation context provides; the equation index a ``DEFINE_SOURCE``
    carries is not it."""
    macro = 'PHASE_INDEX'

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the phase index into the ``PHASE_INDEX`` macro call carrying
        the thread the compilation context provides.
        :raise Compiler.CompileError: raise when the context provides no
            thread (the quantity sits outside any thread context)
        """
        from kits.fluent import udf  # Deferred: udf.py and api.py share the kit entry chain

        maybe_unused(data)
        thread = udf.context_role(builder, 'thread')
        if not thread:
            raise Compiler.CompileError(Compiler.B1006,
                                        _('ctx_missing_macro').format(cls.meta().display_name,
                                                                      _('ctx_thread_place')))
        return f'PHASE_INDEX({thread})'


register_context_completion(Completion(keyword='phase_index',
                                       component_name=KitManager.merge_names('fluent', 'phase_index'),
                                       description=_('api_phase_index'),
                                       kind=_Parameter),
                            ('thread',))

# The user-defined-memory read accessor completes where a cell and its thread
# are in scope, like the plain cell accessors (the write statement registers
# with the assignment accessors above)
register_context_completion(Completion(keyword='cell_user_memory',
                                       component_name=KitManager.merge_names('fluent', 'c_udmi'),
                                       description=_('api_c_udmi'),
                                       kind=ComponentMetadata.Kind.Function),
                            ('cell', 'thread'))


class CVectorComponent(CFluentConstant, abstract):
    """
    Base of the spatial-direction components of a vector: one component per
    direction, rendering the direction subscript of the vector expression the
    field carries (``expr[0]`` for the x direction, ``expr[1]`` for the y
    direction, ``expr[2]`` for the z direction), so non-programmer users never
    write the index themselves. The vector expression is the only field the
    interface carries; the archive carries it under ``vector``.
    """

    # The zero-based index of the spatial direction the component reads
    index: ClassVar[int] = 0

    class FVectorComponentInterface(CFluentConstant.FConstantInterface):
        lt_vector: Final[string] = _('label_vector')

        def __init__(self, owner: typeof['CVectorComponent'], graphics: IComponentGraphics):
            super().__init__(owner, graphics)
            label_vector = graphics.create_native_label(self.lt_vector, self.font)
            graphics.label_metric_width(label_vector, modify=True)
            # The vector is an expression context: operators nest, statements never do
            self.edit_vector = graphics.create_visual_code_edit(QRectF(0, 0, 90, 24))
            self.edit_vector.filter(ComponentMetadata.Level.Expression)
            self.layout.add_element(label_vector, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_vector, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    null, null, graphics=graphics)

    _interface_cls = FVectorComponentInterface

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_vector  # The vector is the only field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_vector]

    def __serialize__(self) -> dict:
        return {
            'vector': serialize(self._interface.edit_vector)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        require_member(data, 'vector')
        component = cls(parent, graphics)
        component._interface.edit_vector.load(data['vector'])
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the component into the direction subscript of the vector the
        field carries (``expr[i]``); a composed expression is parenthesized so
        the subscript binds the whole of it.
        """
        from kits.fluent import udf  # Deferred: udf.py and api.py share the kit entry chain

        require_member(data, 'vector')
        vector = udf.render_edit(data['vector'], builder).strip()
        if vector and not vector.isidentifier():
            vector = f'({vector})'
        return f'{vector}[{cls.index}]'


# The spatial directions of a vector: each becomes a component subscripting the
# vector expression its field carries ([0] for x, [1] for y, [2] for z); they
# take no context role, so they complete at any position
# (keyword, meta name, locale key of the display name, direction index)
_VectorComponents: Final[tuple[tuple[string, string, string, int], ...]] = (
    ('x_component', 'x_component', 'x_component_display', 0),
    ('y_component', 'y_component', 'y_component_display', 1),
    ('z_component', 'z_component', 'z_component_display', 2),
)

for _keyword, _name, _display_key, _index in _VectorComponents:
    # The base carries ABCMeta (the ``abstract`` marker): the derived classes
    # must be created through it, or the metaclasses conflict
    _component = type(CVectorComponent)(f'C{_name.replace("_", " ").title().replace(" ", "")}VectorComponent',
                                        (CVectorComponent,), {'index': _index})
    _component = ComponentMetadata.create(_name, _(_display_key), _(f'api_{_name}'), [UDF],
                                          level=ComponentMetadata.Level.Expression,
                                          kind=_DataAccess)(_component)
    _component = Component.use__interface(_component)
    fluent.register(_component)
    KitManager.instance().add_completion(_keyword, KitManager.merge_names('fluent', _name))
