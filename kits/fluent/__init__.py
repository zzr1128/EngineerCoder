# -*- coding: utf-8 -*-

from core.kit import Kit
from kits.fluent.fluent import UDF, fluent
from kits.fluent.udf import UdfNative, UdfBranch, UdfLoop, UdfFor, UdfAssign, UdfField  # statement delegations
from kits.fluent.udf import UdfPlus, UdfMinus, UdfMultiply, UdfDivide, UdfModulus  # operator delegations
# general UDF macro components and the translation unit
from kits.fluent.general import CAdjust, CInit, CExecuteAtEnd, COnDemand, CRwFile, CDeltaT, CExecuteFromGui
from kits.fluent.general import CTranslationUnit
# model-specific UDF macro components
from kits.fluent.model import CProfile, CSource, CProperty, CDiffusivity, CTurbulentViscosity, CPrandtl
from kits.fluent.model import CTurbSchmidt, CSpecificHeat, CHeatFlux, CVrRate, CSrRate, CCavitationRate
from kits.fluent.model import CNoxRate, CSoxRate, CCphi
# multiphase UDF macro components
from kits.fluent.mpf import CMassTransfer, CExchangeProperty, CVectorExchangeProperty
# discrete phase model (DPM) UDF macro components
from kits.fluent.dpm import CDpmInjectionInit, CDpmLaw, CDpmDrag, CDpmBodyForce, CDpmSource, CDpmBc
# dynamic mesh UDF macro components
from kits.fluent.dynm import CGridMotion, CCgMotion
# discrete ordinates (DO) radiation model UDF macro components
from kits.fluent.do import CDomSource, CEmissivityWeightingFactor


def kit_entry() -> Kit:
    return fluent
