# -*- coding: utf-8 -*-

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
from kits.fluent.traversal import CThreadCellLoop, CThreadFaceLoop, CCellLoop, CFaceOfCellLoop, CNodeOfCellLoop
# Fluent UDF API: every helper macro as a component (the constants, the
# context-bound accessors and calls, the phase index; register themselves)
from kits.fluent import api
from kits.fluent.api import CPhaseIndex  # the phase index of the enclosing source term
# completion analyzer (derives variable completions from assignments; registers itself)
from kits.fluent import analyzer


def kit_entry() -> Kit:
    return fluent
