# -*- coding: utf-8 -*-

from alias import *
from core.kit import Kit, KitMetadata
from core.meta import AuthorInfo, Version

# The C-based kit contributes no components and no target language of its own:
# it is the shared C-language foundation other kits depend on (the fluent kit
# depends on it), providing the static checking of identifiers and free C
# source against the C standard the project selects
cbased = Kit.create_empty(KitMetadata('cbased', 'C-Based Kit',
                                      'C language support shared by C-based kits: static checking of identifiers and '
                                      'free C source against the C standard the project selects, backed by the '
                                      'bundled clang toolchain when it is available.',
                                      Version(0, 0, 0x01001), [], null, Version(0, 0, 0x01001), [],
                                      [AuthorInfo('EngineerCoder Project', 'zzr4028@163.com',
                                                  'Official developer(s) of EngineerCoder')],
                                      []))

__all__ = ('cbased',)
