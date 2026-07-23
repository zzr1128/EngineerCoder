# -*- coding: utf-8 -*-

from alias import *
import gettext


def init_translation() -> Callable[[string], string]:
    trans = gettext.translation(
        domain='messages',
        localedir='res/locale',
        languages=['en_US', 'zh_CN']
    )
    return trans.gettext


_: Callable[[string], string] = init_translation()
