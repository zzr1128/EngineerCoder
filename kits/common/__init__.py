# -*- coding: utf-8 -*-

from core.kit import Kit
from kits.common.clk import clk
from kits.common.branch import CBranch  # br(if)
from kits.common.native import CNative  # native(native code)
from kits.common.loop import CLoop, CFor  # loop(while), for(count loop)
from kits.common.assign import CAssign  # assign(set)
from kits.common.arithmetic import CPlus, CMinus, CMultiply, CDivide, CModulus  # arithmetic operators
from kits.common.relation import CGreater, CLess, CGreaterEqual, CLessEqual, CEqual, CNotEqual  # comparison operators
from kits.common.field import CField  # field(member)


def kit_entry() -> Kit:
    return clk
