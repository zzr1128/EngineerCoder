# -*- coding: utf-8 -*-

"""
Multiphase UDF macros of Ansys Fluent as native UDF components.

Every macro component wraps one of the multiphase ``DEFINE_*`` macros that
customize the interaction between the phases of a multiphase flow (interphase
mass transfer, interphase exchange properties): the user supplies the function
name, the identifiers the macro parameters declare, and the function body;
compilation emits the macro invocation followed by the body block, e.g.::

    DEFINE_MASS_TRANSFER(my_transfer, from, from_t, to, to_t)
    {
        ...
    }

The interface, the serialization contract and the compilation are shared with
the general-purpose macros through ``CFluentMacro`` (see ``kits.fluent.general``);
this module only supplies the macro name, the parameter specification and the
completion keyword of each multiphase macro. Like the general macros, these
define complete functions and therefore carry the ``Domain`` level.
"""

from core.component import Component, ComponentMetadata
from core.kit import KitManager
from kits.fluent.fluent import UDF, fluent
from kits.fluent.general import CFluentMacro
from kits.fluent.localization import _


@fluent.register
@Component.use__interface
@ComponentMetadata.create('mass_transfer', _('mass_transfer_display_name'), _('mass_transfer_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CMassTransfer(CFluentMacro):
    """``DEFINE_MASS_TRANSFER(name, from, from_t, to, to_t)``: UDF defining
    the mass transfer rate between two phases of a multiphase flow; ``from``
    and ``to`` name the source and the target ``Phase*``, ``from_t`` and
    ``to_t`` their threads. The body must return the rate as a ``real``."""
    macro = 'DEFINE_MASS_TRANSFER'
    args_spec = ((_('label_from_phase'), 'from'), (_('label_thread'), 'from_t'),
                 (_('label_to_phase'), 'to'), (_('label_thread'), 'to_t'))
    completion_keyword = 'mass_transfer'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('exchange_property', _('exchange_property_display_name'), _('exchange_property_description'),
                          [UDF], level=ComponentMetadata.Level.Domain)
class CExchangeProperty(CFluentMacro):
    """``DEFINE_EXCHANGE_PROPERTY(name, from, from_t, to, to_t)``: UDF
    defining the exchange property (interphase exchange coefficient) between
    two phases of a multiphase flow; ``from`` and ``to`` name the two
    ``Phase *`` parameters, ``from_t`` and ``to_t`` their threads. The body
    must return a ``real``."""
    macro = 'DEFINE_EXCHANGE_PROPERTY'
    args_spec = ((_('label_from_phase'), 'from'), (_('label_thread'), 'from_t'),
                 (_('label_to_phase'), 'to'), (_('label_thread'), 'to_t'))
    completion_keyword = 'exchange_property'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('vector_exchange_property', _('vector_exchange_property_display_name'),
                          _('vector_exchange_property_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CVectorExchangeProperty(CFluentMacro):
    """``DEFINE_VECTOR_EXCHANGE_PROPERTY(name, from, from_t, to, to_t)``: UDF
    defining the vector exchange property between two phases of a multiphase
    flow; ``from`` and ``to`` name the two ``Phase *`` parameters, ``from_t``
    and ``to_t`` their threads. The body must return a ``real``."""
    macro = 'DEFINE_VECTOR_EXCHANGE_PROPERTY'
    args_spec = ((_('label_from_phase'), 'from'), (_('label_thread'), 'from_t'),
                 (_('label_to_phase'), 'to'), (_('label_thread'), 'to_t'))
    completion_keyword = 'vector_exchange_property'


# Contribute the completion keywords of the macro components to the global
# registry, so any visual code edit picks them up (filtered by level)
for _comp in (CMassTransfer, CExchangeProperty, CVectorExchangeProperty):
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))
