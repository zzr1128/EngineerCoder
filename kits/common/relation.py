# -*- coding: utf-8 -*-
"""
Comparison (relational and equality) operator components of the Common
Language Kit.

Like the arithmetic operators (see ``kits.common.arithmetic``), a comparison
operator embeds its two operands around its symbol ("xx > xx"); the operands
are expression-level visual code edits. The components stay language-neutral:
language support arrives through delegations, which emit the C-style symbol
between the rendered operands.
"""

from alias import *
from core.component import Component, ComponentMetadata
from kits.common.arithmetic import CBinaryOperator
from kits.common.clk import clk
from kits.common.localization import _


@clk.register
@Component.use__interface
@ComponentMetadata.create('greater', _('greater_display_name'), _('greater_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CGreater(CBinaryOperator):
    symbol = '>'


@clk.register
@Component.use__interface
@ComponentMetadata.create('less', _('less_display_name'), _('less_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CLess(CBinaryOperator):
    symbol = '<'


@clk.register
@Component.use__interface
@ComponentMetadata.create('greater_equal', _('greater_equal_display_name'), _('greater_equal_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CGreaterEqual(CBinaryOperator):
    symbol = '>='


@clk.register
@Component.use__interface
@ComponentMetadata.create('less_equal', _('less_equal_display_name'), _('less_equal_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CLessEqual(CBinaryOperator):
    symbol = '<='


@clk.register
@Component.use__interface
@ComponentMetadata.create('equal', _('equal_display_name'), _('equal_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CEqual(CBinaryOperator):
    symbol = '=='


@clk.register
@Component.use__interface
@ComponentMetadata.create('not_equal', _('not_equal_display_name'), _('not_equal_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CNotEqual(CBinaryOperator):
    symbol = '!='
