# -*- coding: utf-8 -*-
"""
Dynamic mesh UDF macros of Ansys Fluent as native UDF components.

Every macro component wraps one of the dynamic mesh ``DEFINE_*`` macros that
prescribe the motion of the mesh (node-based deformation of dynamic zones,
rigid body motion of the center of gravity): the user supplies the function
name, the identifiers the macro parameters declare, and the function body;
compilation emits the macro invocation followed by the body block, e.g.::

    DEFINE_CG_MOTION(my_motion, dt, cg_velocity, cg_omega, time, dtime)
    {
        ...
    }

The interface, the serialization contract and the compilation are shared with
the general-purpose macros through ``CFluentMacro`` (see ``kits.fluent.general``);
this module only supplies the macro name, the parameter specification and the
completion keyword of each dynamic mesh macro. Like the general macros, these
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
@ComponentMetadata.create('grid_motion', _('grid_motion_display_name'), _('grid_motion_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CGridMotion(CFluentMacro):
    """``DEFINE_GRID_MOTION(name, d, dt, time, dtime)``: UDF defining the
    motion of the nodes of a dynamic mesh zone; ``d`` names the ``Domain *``,
    ``dt`` the ``Dynamic_Thread *`` of the zone, ``time``/``dtime`` the
    current time and the time step size."""
    macro = 'DEFINE_GRID_MOTION'
    args_spec = ((_('label_domain'), 'd'), (_('label_dynamic_thread'), 'dt'),
                 (_('label_time'), 'time'), (_('label_time_step'), 'dtime'))
    completion_keyword = 'grid_motion'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('cg_motion', _('cg_motion_display_name'), _('cg_motion_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CCgMotion(CFluentMacro):
    """``DEFINE_CG_MOTION(name, dt, cg_velocity, cg_omega, time, dtime)``:
    UDF defining the translational and rotational velocities of a rigid body
    of the dynamic mesh; ``dt`` names the ``Dynamic_Thread *`` of the zone;
    the body must set the velocities through the ``real`` arrays
    ``cg_velocity``/``cg_omega``."""
    macro = 'DEFINE_CG_MOTION'
    args_spec = ((_('label_dynamic_thread'), 'dt'), (_('label_cg_velocity'), 'cg_velocity'),
                 (_('label_cg_omega'), 'cg_omega'), (_('label_time'), 'time'),
                 (_('label_time_step'), 'dtime'))
    completion_keyword = 'cg_motion'


# Contribute the completion keywords of the macro components to the global
# registry, so any visual code edit picks them up (filtered by level)
for _comp in (CGridMotion, CCgMotion):
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))
