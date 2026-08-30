# -*- coding: utf-8 -*-

from alias import *
from core.kit import Kit, KitMetadata
from core.meta import AuthorInfo, SupportedLanguage, Version
from kits.fluent.localization import _

# UDF (user-defined function): the C dialect Ansys Fluent interprets for user customization;
# generated source files use the C extension
UDF = SupportedLanguage('Ansys Fluent UDF', 'udf',
                        'User-defined function language of Ansys Fluent, a dialect of C', 'c')

fluent = Kit.create_empty(KitMetadata('fluent', _('display_name'),
                                      _('description'),
                                      Version(0, 0, 0x01013), [UDF], null, Version(0, 0, 0x01001), ['clk', 'cbased'],
                                      [AuthorInfo('EngineerCoder Project', 'zzr4028@163.com',
                                                  'Official developer(s) of EngineerCoder')],
                                      []))

__all__ = ('UDF', 'fluent')
