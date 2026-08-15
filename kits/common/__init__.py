# -*- coding: utf-8 -*-

from core.kit import Kit
from kits.common.clk import clk
from kits.common.branch import CBranch  # br(if)


def kit_entry() -> Kit:
    return clk
