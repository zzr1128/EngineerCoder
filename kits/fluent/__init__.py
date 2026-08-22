# -*- coding: utf-8 -*-

from alias import *
from core.kit import Kit
from kits.fluent.fluent import UDF, fluent
from kits.fluent.udf import UdfNative, UdfBranch, UdfLoop, UdfFor, UdfAssign, UdfField  # statement delegations
from kits.fluent.udf import UdfPlus, UdfMinus, UdfMultiply, UdfDivide, UdfModulus  # arithmetic operator delegations
from kits.fluent.udf import UdfGreater, UdfLess, UdfGreaterEqual, UdfLessEqual, UdfEqual, UdfNotEqual  # comparison operator delegations
# general UDF macro components and the translation unit
from kits.fluent.general import CAdjust, CInit, CExecuteAtEnd, COnDemand, CRwFile, CDeltaT, CExecuteFromGui
from kits.fluent.general import CSetDeltat, CEndDeltat  # DEFINE_DELTAT local statements
from kits.fluent.general import CTranslationUnit
# model-specific UDF macro components
from kits.fluent.model import CProfile, CSource, CProperty, CDiffusivity, CTurbulentViscosity, CPrandtl
from kits.fluent.model import CTurbSchmidt, CSpecificHeat, CHeatFlux, CVrRate, CSrRate, CCavitationRate
from kits.fluent.model import CNoxRate, CSoxRate, CCphi
from kits.fluent.model import CSetSourceConst, CSetSourceDiff, CEndSource  # DEFINE_SOURCE local statements
from kits.fluent.model import CSetProperty, CEndProperty  # DEFINE_PROPERTY local statements
# multiphase UDF macro components
from kits.fluent.mpf import CMassTransfer, CExchangeProperty, CVectorExchangeProperty
# discrete phase model (DPM) UDF macro components
from kits.fluent.dpm import CDpmInjectionInit, CDpmLaw, CDpmDrag, CDpmBodyForce, CDpmSource, CDpmBc
# dynamic mesh UDF macro components
from kits.fluent.dynm import CGridMotion, CCgMotion
# discrete ordinates (DO) radiation model UDF macro components
from kits.fluent.do import CDomSource, CEmissivityWeightingFactor
# mesh traversal loop components (thread loops, cell/face/node loops)
from kits.fluent.traversal import CThreadCellLoop, CThreadFaceLoop, CCellLoop, CFaceLoop, CFaceOfCellLoop, CNodeOfCellLoop
# Fluent UDF API: every helper macro as a component (the constants, the
# context-bound accessors and calls, the phase index; register themselves)
from kits.fluent import api
from kits.fluent.api import CPhaseIndex  # the phase index of the enclosing source term
# completion analyzer (derives variable completions from assignments; registers itself)
from kits.fluent import analyzer

from kits.fluent.localization import _

# The palette groups this kit organizes its components into, in display order
# (see ``Kit.palette_groups``); the component metadata carries the group each
# component belongs to (see ``ComponentMetadata.group``)
_group_define: Final[string] = _('palette_define')
_group_cell: Final[string] = _('palette_cell')
_group_face: Final[string] = _('palette_face')
_group_math: Final[string] = _('palette_math')
_group_reduction: Final[string] = _('palette_reduction')
_group_traversal: Final[string] = _('palette_traversal')
_group_udm: Final[string] = _('palette_udm')
_group_physics: Final[string] = _('palette_physics')
fluent.palette_groups = (_group_define, _group_cell, _group_face, _group_math,
                         _group_reduction, _group_traversal, _group_udm, _group_physics)

# Component name -> palette group: assigned after every module registered its
# components, so the palette lists the kit in the domain sections above
_component_groups: IDictionary[string, string] = {}
for _name in ('adjust', 'init', 'execute_at_end', 'on_demand', 'rw_file', 'deltat',
              'set_deltat', 'end_deltat', 'execute_from_gui', 'translation_unit',
              'profile', 'source', 'set_source_const', 'set_source_diff', 'end_source',
              'property', 'set_property', 'end_property', 'diffusivity', 'turbulent_viscosity',
              'prandtl', 'turb_schmidt', 'specific_heat', 'heat_flux', 'vr_rate', 'sr_rate',
              'cavitation_rate', 'nox_rate', 'sox_rate', 'cphi',
              'mass_transfer', 'exchange_property', 'vector_exchange_property',
              'dpm_injection_init', 'dpm_law', 'dpm_drag', 'dpm_body_force', 'dpm_source',
              'dpm_bc', 'grid_motion', 'cg_motion', 'dom_source', 'emissivity_weighting_factor'):
    _component_groups[_name] = _group_define
for _name in ('c_t', 'c_p', 'c_u', 'c_v', 'c_w', 'c_r', 'c_mu_l', 'c_mu_t', 'c_k_l', 'c_k',
              'c_cp', 'c_t_g', 'c_p_g', 'c_eps', 'c_omega', 'c_volume', 'c_centroid',
              'c_face', 'c_face_thread', 'c_node', 'c_profile', 'c_vof', 'c_yi',
              'set_cell_profile', 'set_cell_volume_fraction', 'set_cell_temperature',
              'set_cell_pressure', 'set_cell_x_velocity', 'set_cell_y_velocity',
              'set_cell_z_velocity'):
    _component_groups[_name] = _group_cell
for _name in ('f_t', 'f_p', 'f_u', 'f_v', 'f_w', 'f_centroid', 'f_profile', 'f_area',
              'f_flux', 'f_flux_i', 'f_vof', 'f_yi', 'f_rho', 'f_c0', 'f_c1',
              'set_face_profile'):
    _component_groups[_name] = _group_face
for _name in ('nv_v', 'nv_vv', 'nv_mag', 'nv_dot', 'x_component', 'y_component', 'z_component'):
    _component_groups[_name] = _group_math
for _name in ('prf_gihigh1', 'prf_grsum1'):
    _component_groups[_name] = _group_reduction
for _name in ('thread_cell_loop', 'thread_face_loop', 'cell_loop', 'face_loop',
              'face_of_cell_loop', 'node_of_cell_loop'):
    _component_groups[_name] = _group_traversal
for _name in ('c_udmi', 'set_udmi', 'f_udmi', 'c_udsi', 'c_udsi_g',
              'set_cell_user_scalar', 'set_face_user_memory'):
    _component_groups[_name] = _group_udm
for _name in ('current_timestep', 'current_time', 'previous_time', 'rp_2d', 'rp_3d',
              'nd_nd', 'message', 'fl_malloc', 'fl_free', 'lookup_thread', 'thread_id',
              'thread_type', 'thread_sub_thread', 'phase_index'):
    _component_groups[_name] = _group_physics
for _name, _group in _component_groups.items():
    if _name in fluent.components:
        fluent.components[_name].group = _group


def kit_entry() -> Kit:
    return fluent
