# -*- coding: utf-8 -*-

from core.kit import Kit
from kits.fluent.fluent import UDF, fluent
from kits.fluent.udf import UdfNative, UdfBranch, UdfLoop, UdfFor, UdfAssign, UdfField  # statement delegations
from kits.fluent.udf import UdfPlus, UdfMinus, UdfMultiply, UdfDivide, UdfModulus  # operator delegations
# general UDF macro components and the translation unit
from kits.fluent.general import CAdjust, CInit, CExecuteAtEnd, COnDemand, CRwFile, CDeltaT, CExecuteFromGui
from kits.fluent.general import CTranslationUnit


def kit_entry() -> Kit:
    return fluent
