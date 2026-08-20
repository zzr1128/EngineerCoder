# -*- coding: utf-8 -*-
"""
Discrete phase model (DPM) UDF macros of Ansys Fluent as native UDF components.

Every macro component wraps one of the DPM ``DEFINE_*`` macros that customize
the tracking of the discrete phase (injection initialization, integration
laws, drag and body forces, interphase source terms, boundary behavior): the
user supplies the function name, the identifiers the macro parameters declare,
and the function body; compilation emits the macro invocation followed by the
body block, e.g.::

    DEFINE_DPM_DRAG(my_drag, p, Re)
    {
        ...
    }

The interface, the serialization contract and the compilation are shared with
the general-purpose macros through ``CFluentMacro`` (see ``kits.fluent.general``);
this module only supplies the macro name, the parameter specification and the
completion keyword of each DPM macro. Like the general macros, these define
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
@ComponentMetadata.create('dpm_injection_init', _('dpm_injection_init_display_name'),
                          _('dpm_injection_init_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDpmInjectionInit(CFluentMacro):
    """``DEFINE_DPM_INJECTION_INIT(name, I)``: UDF called when a discrete
    phase injection is initialized; ``I`` names the ``Injection *`` parameter
    describing the injection."""
    macro = 'DEFINE_DPM_INJECTION_INIT'
    args_spec = ((_('label_injection'), 'I'), )
    completion_keyword = 'dpm_injection_init'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('dpm_law', _('dpm_law_display_name'), _('dpm_law_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDpmLaw(CFluentMacro):
    """``DEFINE_DPM_LAW(name, p, ci)``: UDF defining a custom integration law
    for the discrete phase; ``p`` names the tracked particle (``Tracked_Part *``)
    and ``ci`` the integration state."""
    macro = 'DEFINE_DPM_LAW'
    args_spec = ((_('label_particle'), 'p'), (_('label_integration_state'), 'ci'))
    completion_keyword = 'dpm_law'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('dpm_drag', _('dpm_drag_display_name'), _('dpm_drag_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDpmDrag(CFluentMacro):
    """``DEFINE_DPM_DRAG(name, p, Re)``: UDF defining a custom drag
    coefficient for discrete phase particles; ``p`` names the tracked particle
    (``Tracked_Part *``), ``Re`` the particle Reynolds number; the body must
    return the multiplier of the standard drag coefficient as a ``real``."""
    macro = 'DEFINE_DPM_DRAG'
    args_spec = ((_('label_particle'), 'p'), (_('label_reynolds_number'), 'Re'))
    completion_keyword = 'dpm_drag'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('dpm_body_force', _('dpm_body_force_display_name'), _('dpm_body_force_description'),
                          [UDF], level=ComponentMetadata.Level.Domain)
class CDpmBodyForce(CFluentMacro):
    """``DEFINE_DPM_BODY_FORCE(name, p, mass, F, Fd)``: UDF defining an
    additional body force on discrete phase particles; ``p`` names the tracked
    particle (``Tracked_Part *``), ``mass`` the particle mass; the body must
    set the force through the ``real`` array ``F`` and its derivative through
    ``Fd``."""
    macro = 'DEFINE_DPM_BODY_FORCE'
    args_spec = ((_('label_particle'), 'p'), (_('label_particle_mass'), 'mass'),
                 (_('label_body_force'), 'F'), (_('label_force_derivative'), 'Fd'))
    completion_keyword = 'dpm_body_force'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('dpm_source', _('dpm_source_display_name'), _('dpm_source_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDpmSource(CFluentMacro):
    """``DEFINE_DPM_SOURCE(name, cell, thread, S, strength, p)``: UDF adding
    discrete phase source terms to the continuous phase equations; ``cell``
    and ``thread`` name the cell and its thread, ``S`` the source array,
    ``strength`` the particle source strength, ``p`` the tracked particle
    (``Tracked_Part *``)."""
    macro = 'DEFINE_DPM_SOURCE'
    args_spec = ((_('label_cell'), 'cell'), (_('label_thread'), 'thread'), (_('label_source'), 'S'),
                 (_('label_strength'), 'strength'), (_('label_particle'), 'p'))
    completion_keyword = 'dpm_source'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('dpm_bc', _('dpm_bc_display_name'), _('dpm_bc_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDpmBc(CFluentMacro):
    """``DEFINE_DPM_BC(name, p, t, f, f_normal, dim)``: UDF customizing the
    behavior of discrete phase particles at a boundary; ``p`` names the tracked
    particle (``Tracked_Part *``), ``t`` and ``f`` the boundary thread and
    face, ``f_normal`` the face normal array, ``dim`` the dimension; the body
    must return a particle boundary condition."""
    macro = 'DEFINE_DPM_BC'
    args_spec = ((_('label_particle'), 'p'), (_('label_thread'), 't'), (_('label_face'), 'f'),
                 (_('label_face_normal'), 'f_normal'), (_('label_dimension'), 'dim'))
    completion_keyword = 'dpm_bc'


# Contribute the completion keywords of the macro components to the global
# registry, so any visual code edit picks them up (filtered by level)
for _comp in (CDpmInjectionInit, CDpmLaw, CDpmDrag, CDpmBodyForce, CDpmSource, CDpmBc):
    _comp.meta().kind = ComponentMetadata.Kind.Macro
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))
