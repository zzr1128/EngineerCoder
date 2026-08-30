# -*- coding: utf-8 -*-
"""
Model-specific UDF macros of Ansys Fluent as native UDF components.

Every macro component wraps one of the model ``DEFINE_*`` macros that register
a callback with a particular solver model (boundary profiles, source terms,
material properties, turbulence quantities, reaction and cavitation rates,
pollutant formation rates, composition PDF coefficients):
the user supplies the function name, the identifiers the macro parameters
declare, and the function body; compilation emits the macro invocation
followed by the body block, e.g.::

    DEFINE_PROPERTY(my_density, c, t)
    {
        ...
    }

The interface, the serialization contract and the compilation are shared with
the general-purpose macros through ``CFluentMacro`` (see ``kits.fluent.general``);
this module only supplies the macro name, the parameter specification and the
completion keyword of each model macro. Like the general macros, these define
complete functions and therefore carry the ``Domain`` level.

``DEFINE_SOURCE`` and ``DEFINE_PROPERTY`` follow a convention tailored to
non-programmer users: the return value (and the source's derivative array)
stays out of the interface, the compilation names it itself, and the body
hosts statement-level components that store the value to return, set extra
quantities and end the macro (``CReturnMacro`` and ``CMacroStatement`` in
``kits.fluent.general``). They compile inside the body of their host macro
only, so they stay out of the global completion registry and the analyzer
suggests them through the context gating (see ``register_context_completion``).
"""

from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QWidget

from alias import *
from core.build import Compiler
from core.completer import Completion
from core.component import Component, ComponentMetadata
from core.graphics import IComponentGraphics
from core.kit import KitManager
from kits.common.library import CLLibrary
from kits.fluent.analyzer import register_context_completion
from kits.fluent.fluent import UDF, fluent
from kits.fluent.general import (
    CEndMacroStatement,
    CFluentMacro,
    CMacroStatement,
    CReturnMacro,
    CSetValueStatement,
    MacroArgument,
)
from kits.fluent.localization import _


@fluent.register
@Component.use__interface
@ComponentMetadata.create('profile', _('profile_display_name'), _('profile_description'), [UDF],
                          level=ComponentMetadata.Level.Domain,
                          icon='DPMprof.svg')
class CProfile(CFluentMacro):
    """``DEFINE_PROFILE(name, t, i)``: UDF specifying a boundary condition
    profile; ``t`` names the boundary thread and ``i`` the index that
    identifies the variable being defined."""
    macro = 'DEFINE_PROFILE'
    args_spec = ((_('label_thread'), 't'), (_('label_index'), 'i'))
    completion_keyword = 'profile'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('source', _('source_display_name'), _('source_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CSource(CReturnMacro):
    """``DEFINE_SOURCE(name, c, t, dS, eqn)``: UDF defining the source term of
    a transport equation; ``c`` and ``t`` name the cell and its thread.

    The derivative array, the equation index and the value the function
    returns stay out of the interface: the compilation picks available
    identifiers for the array and the value itself, declares the value
    zero-initialized and closes the body with ``return`` of the value unless
    the body already ends with a return (the "end DEFINE_SOURCE" statement
    supplies it). The body stores the returned value through "set source
    const", sets the derivative entry through "set source diff" and may end
    with "end DEFINE_SOURCE" (see the source statements below), so
    non-programmer users never name the quantities nor write the return
    themselves. The phase index a multiphase source applies to is not the
    equation index: the phase index component retrieves it through the
    ``PHASE_INDEX`` macro instead."""
    macro = 'DEFINE_SOURCE'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'))
    completion_keyword = 'source'
    value_base = 'source'
    value_role = 'source_value'
    set_component = 'set_source_const'
    end_component = 'end_source'

    @classmethod
    def context_roles(cls) -> frozenset[string]:
        # On top of the cell, the thread and the auto-named value to return,
        # the source opens the roles its own rendering introduces (the
        # auto-named derivative, the equation index the header carries)
        return super().context_roles() | frozenset(('ds', 'eqn'))

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the archive of this source term into UDF source. Unlike the
        other macros, the header carries identifiers the compilation picks
        itself: an available name for the derivative array (``dS``, ``dS_1``...)
        and one for the value to return (``source``, ``source_1``...), which a
        zero-initializing declaration introduces at the body top; the equation
        index keeps its conventional identifier (``eqn``). The body renders
        under a context providing every role the source opens, and the
        compilation closes it with ``return`` of the value when the body does
        not end with a return statement already (the "end DEFINE_SOURCE"
        statement supplies it).
        """
        from kits.fluent import (
            udf,  # Deferred: udf.py and model.py share the kit entry chain
        )

        require_member(data, 'name', 'args', 'body')
        require_type(data['name'], string, 'name')
        require_type(data['args'], list, 'args')
        args = [string(arg).strip() for arg in cls._normalized_args(data)]
        name = data['name'].strip()
        cell, thread = args
        occupied: HashSet[string] = builder.products.setdefault(udf.OccupiedKey, HashSet[string]())
        taken = occupied | {name, cell, thread}
        derivative = udf.fresh_name('dS', taken)
        value = udf.fresh_name(cls.value_base, taken)
        udf.enter_context(builder, {'cell': cell, 'thread': thread, 'ds': derivative,
                                    'eqn': 'eqn', 'source_value': value})
        occupied.add(derivative)
        occupied.add(value)
        try:
            # The body is a fresh block: declarations lifted into it precede its
            # contents; the declaration of the value to return leads the body itself
            body = udf._hoist_prefix(builder, data['body']) \
                   + f'real {value} = 0.;\n' + udf.render_edit(data['body'], builder)
        finally:
            udf.exit_context(builder)
            occupied.discard(derivative)
            occupied.discard(value)
        # The function returns a real: close the body with the value unless it
        # already ends with a return (the "end DEFINE_SOURCE" statement, or a
        # return the user wrote, supplies it)
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not (lines and lines[-1].startswith('return')):
            if body.strip() and not body.endswith('\n'):
                body += '\n'
            body += f'return {value};\n'
        return f'{cls.macro}({name}, {cell}, {thread}, {derivative}, eqn)\n{udf._block(body)}'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('set_source_const', _('set_source_const_display_name'),
                          _('set_source_const_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CSetSourceConst(CSetValueStatement):
    """Store the constant (zero-order) part of the source term, the value
    ``DEFINE_SOURCE`` returns: compiles into an assignment to the auto-named
    value the source declares (no immediate ``return``), so the body may still
    set the derivative before the source ends."""
    value_role = 'source_value'
    lt_value = _('label_source_const')
    host = _('ctx_inside_source')


@fluent.register
@Component.use__interface
@ComponentMetadata.create('set_source_diff', _('set_source_diff_display_name'),
                          _('set_source_diff_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CSetSourceDiff(CMacroStatement):
    """Set the derivative entry of the source term: compiles into
    ``dS[eqn] = ...`` with the derivative array and the equation index
    the enclosing ``DEFINE_SOURCE`` carries."""
    requires = ('ds', 'eqn')
    host = _('ctx_inside_source')

    class FSetDiffInterface(CMacroStatement.FMacroStatementInterface):
        lt_derivative: Final[string] = _('label_source_diff')

        def __init__(self, owner: typeof['CSetSourceDiff'], graphics: IComponentGraphics):
            super().__init__(owner, graphics)
            label_derivative = graphics.create_native_label(self.lt_derivative, self.font)
            graphics.label_metric_width(label_derivative, modify=True)
            # The derivative is an expression context: operators nest, statements never do
            self.edit_derivative = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 24))
            self.edit_derivative.filter(ComponentMetadata.Level.Expression)
            self.layout.add_element(label_derivative, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_derivative, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)

    _interface_cls = FSetDiffInterface

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_derivative  # The derivative is the only field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_derivative]

    def __serialize__(self) -> dict:
        return {
            'derivative': serialize(self._interface.edit_derivative)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        require_member(data, 'derivative')
        component = cls(parent, graphics)
        component._interface.edit_derivative.load(data['derivative'])
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        from kits.fluent import (
            udf,  # Deferred: udf.py and model.py share the kit entry chain
        )

        cls._require_context(builder)
        require_member(data, 'derivative')
        value = udf.render_edit(data['derivative'], builder).strip()
        return f'{udf.context_role(builder, "ds")}[{udf.context_role(builder, "eqn")}] = {value};'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('end_source', _('end_source_display_name'), _('end_source_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CEndSource(CEndMacroStatement):
    """End the ``DEFINE_SOURCE`` body: compiles into ``return`` of the
    auto-named value the source declares (the one "set source const" stores)."""
    value_role = 'source_value'
    host = _('ctx_inside_source')


@fluent.register
@Component.use__interface
@ComponentMetadata.create('property', _('property_display_name'), _('property_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CProperty(CReturnMacro):
    """``DEFINE_PROPERTY(name, c, t)``: UDF defining a cell-wise material
    property (density, viscosity, ...); ``c`` and ``t`` name the cell and its
    thread.

    The value the function returns stays out of the interface: the
    compilation picks an available identifier for it and declares it
    zero-initialized. The body stores it through "set property" and ends with
    "end DEFINE_PROPERTY" (see the property statements below), so
    non-programmer users never name the quantity nor write the return
    themselves."""
    macro = 'DEFINE_PROPERTY'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'))
    completion_keyword = 'property'
    value_base = 'property'
    value_role = 'property_value'
    set_component = 'set_property'
    end_component = 'end_property'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('set_property', _('set_property_display_name'), _('set_property_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CSetProperty(CSetValueStatement):
    """Store the material property value ``DEFINE_PROPERTY`` returns: compiles
    into an assignment to the auto-named value the macro declares (no
    immediate ``return``)."""
    value_role = 'property_value'
    lt_value = _('label_property_value')
    host = _('ctx_inside_property')


@fluent.register
@Component.use__interface
@ComponentMetadata.create('end_property', _('end_property_display_name'), _('end_property_description'), [UDF],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Function)
class CEndProperty(CEndMacroStatement):
    """End the ``DEFINE_PROPERTY`` body: compiles into ``return`` of the
    auto-named value the macro declares (the one "set property" stores)."""
    value_role = 'property_value'
    host = _('ctx_inside_property')


@fluent.register
@Component.use__interface
@ComponentMetadata.create('diffusivity', _('diffusivity_display_name'), _('diffusivity_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDiffusivity(CFluentMacro):
    """``DEFINE_DIFFUSIVITY(name, c, t, i)``: UDF defining the diffusivity of a
    species or user-defined scalar transport equation; ``c`` and ``t`` name the
    cell and its thread, ``i`` the species or scalar index. The body must
    return a ``real``."""
    macro = 'DEFINE_DIFFUSIVITY'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'), (_('label_index'), 'i'))
    completion_keyword = 'diffusivity'
    return_type = 'real'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('turbulent_viscosity', _('turbulent_viscosity_display_name'),
                          _('turbulent_viscosity_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CTurbulentViscosity(CFluentMacro):
    """``DEFINE_TURBULENT_VISCOSITY(name, c, t)``: UDF computing the turbulent
    viscosity in place of the built-in turbulence models; ``c`` and ``t`` name
    the cell and its thread. The body must return a ``real``."""
    macro = 'DEFINE_TURBULENT_VISCOSITY'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'))
    completion_keyword = 'turbulent_viscosity'
    return_type = 'real'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('prandtl', _('prandtl_display_name'), _('prandtl_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CPrandtl(CFluentMacro):
    """``DEFINE_PRANDTL(name, c, t)``: UDF defining a local Prandtl number;
    ``c`` and ``t`` name the cell and its thread. The body must return a
    ``real``. (Recent Fluent releases split this into the ``DEFINE_PRANDTL_*``
    family, which shares the same parameter list.)"""
    macro = 'DEFINE_PRANDTL'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'))
    completion_keyword = 'prandtl'
    return_type = 'real'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('turb_schmidt', _('turb_schmidt_display_name'), _('turb_schmidt_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CTurbSchmidt(CFluentMacro):
    """``DEFINE_TURB_SCHMIDT(name, c, t, i)``: UDF defining the turbulent
    Schmidt number of a species; ``c`` and ``t`` name the cell and its thread,
    ``i`` the species index. The body must return a ``real``."""
    macro = 'DEFINE_TURB_SCHMIDT'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'), (_('label_index'), 'i'))
    completion_keyword = 'turb_schmidt'
    return_type = 'real'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('specific_heat', _('specific_heat_display_name'), _('specific_heat_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CSpecificHeat(CFluentMacro):
    """``DEFINE_SPECIFIC_HEAT(name, T, Tref, h, yi)``: UDF returning the
    specific heat of a material at the temperature ``T`` (relative to the
    reference temperature ``Tref``); it must also set the sensible enthalpy
    through the ``real *`` parameter ``h``; ``yi`` names the array of gas
    phase mass fractions."""
    macro = 'DEFINE_SPECIFIC_HEAT'
    args_spec = ((_('label_temperature'), 'T'), (_('label_ref_temperature'), 'Tref'),
                 (_('label_enthalpy'), 'h'), (_('label_mass_fractions'), 'yi'))
    completion_keyword = 'specific_heat'
    return_type = 'real'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('heat_flux', _('heat_flux_display_name'), _('heat_flux_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CHeatFlux(CFluentMacro):
    """``DEFINE_HEAT_FLUX(name, f, t, c0, t0, cid, cir)``: UDF modifying the
    modeling of the wall heat flux; ``f`` and ``t`` name the wall face and its
    thread, ``c0`` and ``t0`` the adjacent cell and its thread, and the
    coefficient arrays ``cid``/``cir`` linearize the diffusive/radiative flux."""
    macro = 'DEFINE_HEAT_FLUX'
    args_spec = (MacroArgument(_('label_face'), 'f', role='face'),
                 MacroArgument(_('label_thread'), 't', role='thread'),
                 MacroArgument(_('label_cell0'), 'c0', role='cell'),
                 MacroArgument(_('label_thread0'), 't0', role='thread'),
                 (_('label_diffusive_coef'), 'cid'), (_('label_radiative_coef'), 'cir'))
    completion_keyword = 'heat_flux'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('vr_rate', _('vr_rate_display_name'), _('vr_rate_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CVrRate(CFluentMacro):
    """``DEFINE_VR_RATE(name, c, t, r, mw, yi, rr, rr_t)``: UDF defining the
    rate of a volumetric reaction; ``c`` and ``t`` name the cell and its
    thread, ``r`` the reaction structure, ``mw``/``yi`` the molecular weight
    and mass fraction arrays; the body must set the laminar/turbulent rates
    through the ``real *`` parameters ``rr``/``rr_t``."""
    macro = 'DEFINE_VR_RATE'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'), (_('label_reaction'), 'r'),
                 (_('label_molecular_weights'), 'mw'), (_('label_mass_fractions'), 'yi'),
                 (_('label_laminar_rate'), 'rr'), (_('label_turbulent_rate'), 'rr_t'))
    completion_keyword = 'vr_rate'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('sr_rate', _('sr_rate_display_name'), _('sr_rate_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CSrRate(CFluentMacro):
    """``DEFINE_SR_RATE(name, f, t, r, mw, yi, rr)``: UDF defining the rate of
    a surface reaction; ``f`` and ``t`` name the face and its thread, ``r`` the
    reaction structure, ``mw``/``yi`` the molecular weight and mass fraction
    arrays; the body must set the rate through the ``real *`` parameter ``rr``."""
    macro = 'DEFINE_SR_RATE'
    args_spec = (MacroArgument(_('label_face'), 'f', role='face'),
                 MacroArgument(_('label_thread'), 't', role='thread'), (_('label_reaction'), 'r'),
                 (_('label_molecular_weights'), 'mw'), (_('label_mass_fractions'), 'yi'),
                 (_('label_laminar_rate'), 'rr'))
    completion_keyword = 'sr_rate'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('cavitation_rate', _('cavitation_rate_display_name'), _('cavitation_rate_description'),
                          [UDF], level=ComponentMetadata.Level.Domain)
class CCavitationRate(CFluentMacro):
    """``DEFINE_CAVITATION_RATE(name, c, t, p, rhoV, rhoL, mafV, p_v, cigma, f_gas, m_dot)``:
    UDF defining the cavitation mass transfer rate of the mixture model; ``c``
    and ``t`` name the cell and the mixture-level thread; the body must set the
    rate through the ``real *`` parameter ``m_dot``."""
    macro = 'DEFINE_CAVITATION_RATE'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'), (_('label_pressure'), 'p'),
                 (_('label_vapor_density'), 'rhoV'), (_('label_liquid_density'), 'rhoL'),
                 (_('label_vapor_fraction'), 'mafV'), (_('label_vaporization_pressure'), 'p_v'),
                 (_('label_surface_tension'), 'cigma'), (_('label_gas_fraction'), 'f_gas'),
                 (_('label_transfer_rate'), 'm_dot'))
    completion_keyword = 'cavitation_rate'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('nox_rate', _('nox_rate_display_name'), _('nox_rate_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CNoxRate(CFluentMacro):
    """``DEFINE_NOX_RATE(name, c, t, Pollut, Pollut_Par, NOx)``: UDF defining
    the NOx formation rate that can replace, or be added to, the internally
    calculated rate; ``c`` and ``t`` name the cell and its thread, ``Pollut``
    and ``Pollut_Par`` the pollutant cell and parameter structures, ``NOx``
    the NOx model structure; the rates are returned through the ``Pollut``
    structure (``POLLUT_FRATE``/``POLLUT_RRATE``)."""
    macro = 'DEFINE_NOX_RATE'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'),
                 (_('label_pollut_cell'), 'Pollut'), (_('label_pollut_parameter'), 'Pollut_Par'),
                 (_('label_model_parameter'), 'NOx'))
    completion_keyword = 'nox_rate'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('sox_rate', _('sox_rate_display_name'), _('sox_rate_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CSoxRate(CFluentMacro):
    """``DEFINE_SOX_RATE(name, c, t, Pollut, Pollut_Par, SOx)``: UDF defining
    the SOx formation rate that can replace, or be added to, the internally
    calculated rate; ``c`` and ``t`` name the cell and its thread, ``Pollut``
    and ``Pollut_Par`` the pollutant cell and parameter structures, ``SOx``
    the SOx model structure; the rates are returned through the ``Pollut``
    structure (``POLLUT_FRATE``/``POLLUT_RRATE``)."""
    macro = 'DEFINE_SOX_RATE'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'),
                 (_('label_pollut_cell'), 'Pollut'), (_('label_pollut_parameter'), 'Pollut_Par'),
                 (_('label_model_parameter'), 'SOx'))
    completion_keyword = 'sox_rate'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('cphi', _('cphi_display_name'), _('cphi_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CCphi(CFluentMacro):
    """``DEFINE_CPHI(name, c, t)``: UDF defining the mixing coefficient
    ``C_phi`` of the composition PDF transport model; ``c`` and ``t`` name
    the cell and its thread. The body must return the coefficient as a
    ``real``."""
    macro = 'DEFINE_CPHI'
    args_spec = (MacroArgument(_('label_cell'), 'c', role='cell'),
                 MacroArgument(_('label_thread'), 't', role='thread'))
    completion_keyword = 'cphi'
    return_type = 'real'


# Mark the DEFINE_* macro components as macro-kind (completion glyph) and contribute
# their completion keywords to the global registry, so any visual code edit picks
# them up (filtered by level)
for _comp in (CProfile, CSource, CProperty, CDiffusivity, CTurbulentViscosity, CPrandtl,
              CTurbSchmidt, CSpecificHeat, CHeatFlux, CVrRate, CSrRate, CCavitationRate,
              CNoxRate, CSoxRate, CCphi):
    _comp.meta().kind = ComponentMetadata.Kind.Macro
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))

# The source statements compile inside DEFINE_SOURCE bodies only: they never
# join the global completion registry; the analyzer suggests them where the
# hosting components provide the roles they require (see register_context_completion)
register_context_completion(Completion(keyword='set_source_const',
                                       component_name=KitManager.merge_names('fluent', 'set_source_const'),
                                       description=CSetSourceConst.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CSetSourceConst.required_roles())
register_context_completion(Completion(keyword='set_source_diff',
                                       component_name=KitManager.merge_names('fluent', 'set_source_diff'),
                                       description=CSetSourceDiff.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CSetSourceDiff.required_roles())
register_context_completion(Completion(keyword='end_source',
                                       component_name=KitManager.merge_names('fluent', 'end_source'),
                                       description=CEndSource.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CEndSource.required_roles())

# The property statements compile inside DEFINE_PROPERTY bodies only, the same
# context gating as the source statements above
register_context_completion(Completion(keyword='set_property',
                                       component_name=KitManager.merge_names('fluent', 'set_property'),
                                       description=CSetProperty.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CSetProperty.required_roles())
register_context_completion(Completion(keyword='end_property',
                                       component_name=KitManager.merge_names('fluent', 'end_property'),
                                       description=CEndProperty.meta().description,
                                       kind=ComponentMetadata.Kind.Function),
                            CEndProperty.required_roles())
