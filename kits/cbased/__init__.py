# -*- coding: utf-8 -*-

from core.kit import Kit
from kits.cbased.cbased import cbased
# C language checker (validates identifiers and free C source; registers itself)
from kits.cbased import checker


def kit_entry() -> Kit:
    return cbased
