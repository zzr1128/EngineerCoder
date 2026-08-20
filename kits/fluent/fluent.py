# -*- coding: utf-8 -*-

from alias import *
from core.kit import Kit, KitMetadata
from core.meta import Version, AuthorInfo, SupportedLanguage

# UDF (user-defined function): the C dialect Ansys Fluent interprets for user customization;
# generated source files use the C extension
UDF = SupportedLanguage('Ansys Fluent UDF', 'udf',
                        'User-defined function language of Ansys Fluent, a dialect of C', 'c')

fluent = Kit.create_empty(KitMetadata('fluent', 'Ansys Fluent Kit',
                                      'The translation unit and components of the general and model-specific Ansys '
                                      'Fluent UDF macros, and delegating implementations of common components for the '
                                      'Ansys Fluent UDF language.',
                                      Version(0, 0, 0x01009), [UDF], null, Version(0, 0, 0x01001), ['clk'],
                                      [AuthorInfo('EngineerCoder Project', 'zzr4028@163.com',
                                                  'Official developer(s) of EngineerCoder')],
                                      []))

__all__ = ('UDF', 'fluent')
