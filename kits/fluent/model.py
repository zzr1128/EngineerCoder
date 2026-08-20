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
"""

from alias import *
from core.component import Component, ComponentMetadata
from core.kit import KitManager
from kits.fluent.fluent import UDF, fluent
from kits.fluent.general import CFluentMacro
from kits.fluent.localization import _


@fluent.register
@Component.use__interface
@ComponentMetadata.create('profile', _('profile_display_name'), _('profile_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
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
class CSource(CFluentMacro):
    """``DEFINE_SOURCE(name, c, t, dS, eqn)``: UDF defining the source term of
    a transport equation; ``c`` and ``t`` name the cell and its thread, ``dS``
    the array of linearization derivatives and ``eqn`` the solved equation
    index. The body must return a ``real``."""
    macro = 'DEFINE_SOURCE'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'),
                 (_('label_derivative'), 'dS'), (_('label_equation'), 'eqn'))
    completion_keyword = 'source'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('property', _('property_display_name'), _('property_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CProperty(CFluentMacro):
    """``DEFINE_PROPERTY(name, c, t)``: UDF defining a cell-wise material
    property (density, viscosity, ...); ``c`` and ``t`` name the cell and its
    thread. The body must return a ``real``."""
    macro = 'DEFINE_PROPERTY'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'))
    completion_keyword = 'property'


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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'), (_('label_index'), 'i'))
    completion_keyword = 'diffusivity'


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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'))
    completion_keyword = 'turbulent_viscosity'


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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'))
    completion_keyword = 'prandtl'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('turb_schmidt', _('turb_schmidt_display_name'), _('turb_schmidt_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CTurbSchmidt(CFluentMacro):
    """``DEFINE_TURB_SCHMIDT(name, c, t, i)``: UDF defining the turbulent
    Schmidt number of a species; ``c`` and ``t`` name the cell and its thread,
    ``i`` the species index. The body must return a ``real``."""
    macro = 'DEFINE_TURB_SCHMIDT'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'), (_('label_index'), 'i'))
    completion_keyword = 'turb_schmidt'


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
    args_spec = ((_('label_face'), 'f'), (_('label_thread'), 't'),
                 (_('label_cell0'), 'c0'), (_('label_thread0'), 't0'),
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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'), (_('label_reaction'), 'r'),
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
    args_spec = ((_('label_face'), 'f'), (_('label_thread'), 't'), (_('label_reaction'), 'r'),
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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'), (_('label_pressure'), 'p'),
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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'),
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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'),
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
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'))
    completion_keyword = 'cphi'


# Mark the DEFINE_* macro components as macro-kind (completion glyph) and contribute
# their completion keywords to the global registry, so any visual code edit picks
# them up (filtered by level)
for _comp in (CProfile, CSource, CProperty, CDiffusivity, CTurbulentViscosity, CPrandtl,
              CTurbSchmidt, CSpecificHeat, CHeatFlux, CVrRate, CSrRate, CCavitationRate,
              CNoxRate, CSoxRate, CCphi):
    _comp.meta().kind = ComponentMetadata.Kind.Macro
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))
