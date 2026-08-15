# -*- coding: utf-8 -*-

from alias import *
from core.kit import Kit, KitMetadata
from core.meta import Version, AuthorInfo

clk = Kit.create_empty(KitMetadata('clk', 'Common Language Kit', 'Kit of common language components and libraries.',
                                   Version(0, 0, 0x01001), [], null, Version(0, 0, 0x01001), [],
                                   [AuthorInfo('EngineerCoder Project', 'zzr4028@163.com', 'Official developer(s) of '
                                                                                          'EngineerCoder')],
                                   []))

__all__ = ('clk', )
