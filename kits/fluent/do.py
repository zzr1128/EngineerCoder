# -*- coding: utf-8 -*-
"""
Discrete ordinates (DO) radiation model UDF macros of Ansys Fluent as native
UDF components.

Every macro component wraps one of the DO model ``DEFINE_*`` macros that
customize radiative transfer (directional sources, gray-band emissivity
weighting): the user supplies the function name, the identifiers the macro
parameters declare, and the function body; compilation emits the macro
invocation followed by the body block, e.g.::

    DEFINE_DOM_SOURCE(my_dom_source, c, t, s, xi, emission, in_scattering, abs_coeff, scat_coeff)
    {
        ...
    }

The interface, the serialization contract and the compilation are shared with
the general-purpose macros through ``CFluentMacro`` (see ``kits.fluent.general``);
this module only supplies the macro name, the parameter specification and the
completion keyword of each DO model macro. Like the general macros, these
define complete functions and therefore carry the ``Domain`` level.
"""

from alias import *
from core.component import Component, ComponentMetadata
from core.kit import KitManager
from kits.fluent.fluent import UDF, fluent
from kits.fluent.general import CFluentMacro
from kits.fluent.localization import _


@fluent.register
@Component.use__interface
@ComponentMetadata.create('dom_source', _('dom_source_display_name'), _('dom_source_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDomSource(CFluentMacro):
    """``DEFINE_DOM_SOURCE(name, c, t, s, xi, emission, in_scattering,
    abs_coeff, scat_coeff)``: UDF customizing radiative transfer of the
    discrete ordinates model; ``c`` and ``t`` name the cell and its thread,
    ``s`` the direction index, ``xi`` the direction vector; the body must set
    the emission, in-scattering and the absorption/scattering coefficients
    through the ``real *`` parameters."""
    macro = 'DEFINE_DOM_SOURCE'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'),
                 (_('label_direction_index'), 's'), (_('label_direction'), 'xi'),
                 (_('label_emission'), 'emission'), (_('label_in_scattering'), 'in_scattering'),
                 (_('label_absorption_coef'), 'abs_coeff'), (_('label_scattering_coef'), 'scat_coeff'))
    completion_keyword = 'dom_source'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('emissivity_weighting_factor', _('emissivity_weighting_factor_display_name'),
                          _('emissivity_weighting_factor_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CEmissivityWeightingFactor(CFluentMacro):
    """``DEFINE_EMISSIVITY_WEIGHTING_FACTOR(name, c, t, s, xi, weight)``: UDF
    defining the emissivity weighting factor for gray-band radiation of the
    discrete ordinates model; ``c`` and ``t`` name the cell and its thread,
    ``s`` the direction index, ``xi`` the direction vector; the body must set
    the factor through the ``real *`` parameter ``weight``."""
    macro = 'DEFINE_EMISSIVITY_WEIGHTING_FACTOR'
    args_spec = ((_('label_cell'), 'c'), (_('label_thread'), 't'),
                 (_('label_direction_index'), 's'), (_('label_direction'), 'xi'),
                 (_('label_weight'), 'weight'))
    completion_keyword = 'emissivity_weighting_factor'


# Contribute the completion keywords of the macro components to the global
# registry, so any visual code edit picks them up (filtered by level)
for _comp in (CDomSource, CEmissivityWeightingFactor):
    _comp.meta().kind = ComponentMetadata.Kind.Macro
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))
