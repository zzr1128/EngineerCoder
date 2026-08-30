# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget

from alias import *
from core.component import Component, ComponentMetadata, IComponentInterface
from core.graphics import IComponentGraphics
from kits.common.clk import clk
from kits.common.library import CLLibrary
from kits.common.localization import _


class CBinaryOperator(Component):
    """
    Base class of binary operator components.

    An operator embeds its two operands around the operator symbol ("xx + xx"):
    both are expression-level visual code edits, so they accept plain text and
    nested expression components alike. Archives made before the operands
    existed carry no keys and restore with both operands blank.
    """

    # The operator symbol shown between the operands (and emitted to the source)
    symbol: ClassVar[string] = ''

    class FOperatorInterface(IComponentInterface):
        def __init__(self, graphics: IComponentGraphics, symbol: string):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_symbol = graphics.create_native_label(symbol, self.font)
            graphics.label_metric_width(self.label_symbol, modify=True)
            # The operands are expression contexts: operators and member accesses
            # nest inside them, statement-level components never do; the edits own
            # their width, growing with the entered contents (never below the
            # declared width)
            self.edit_left = graphics.create_visual_code_edit(QRectF(0, 0, 100, 24))
            self.edit_left.filter(ComponentMetadata.Level.Expression)
            self.edit_left.setAutoWidthEnabled(True)
            self.edit_right = graphics.create_visual_code_edit(QRectF(0, 0, 100, 24))
            self.edit_right.filter(ComponentMetadata.Level.Expression)
            self.edit_right.setAutoWidthEnabled(True)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.edit_left, null, null, null, graphics=graphics)
            self.layout.add_element(self.label_symbol, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_right, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null,
                                    graphics=graphics)
            self.color = graphics.alloc_color()

        def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:
            # Locate figures and widgets at the UI origin of this interface
            graphics.push_anchor(self.origin)
            try:
                self.layout.update(graphics)

                if painting:
                    size = self.layout.size(graphics)
                    # Box size includes one margin on each side; deduct 2*2.5 so the frame insets 2.5px into margins
                    graphics.disp_draw_rect(QRectF(2.5, 2.5, size.width() - 5, size.height() - 5), self.color, round_radius=5)
            finally:
                graphics.pop_anchor()

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        super().__init__(parent, graphics)
        self._interface = CBinaryOperator.FOperatorInterface(graphics, type(self).symbol)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_left  # The left operand is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_left, self._interface.edit_right]

    def __serialize__(self) -> dict:
        return {
            'left': serialize(self._interface.edit_left),
            'right': serialize(self._interface.edit_right)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore an operator from its serialization.

        The constructor reconstructs the interface (whose operand edits are
        empty); the archived operands are then loaded into those edits in
        place, since their references are held by the interface layout.
        """
        component = cls(parent, graphics)
        # Archives made before the operands existed carry neither key
        if 'left' in data:
            component._interface.edit_left.load(data['left'])
        if 'right' in data:
            component._interface.edit_right.load(data['right'])
        return component


class CArithmeticOperator(CBinaryOperator):
    """Base class of arithmetic operator components."""


@clk.register
@Component.use__interface
@ComponentMetadata.create('plus', _('plus_display_name'), _('plus_description'), [],
                          level=ComponentMetadata.Level.Expression, icon='plus.svg')
class CPlus(CArithmeticOperator):
    symbol = '+'


@clk.register
@Component.use__interface
@ComponentMetadata.create('minus', _('minus_display_name'), _('minus_description'), [],
                          level=ComponentMetadata.Level.Expression, icon='minus.svg')
class CMinus(CArithmeticOperator):
    symbol = '-'


@clk.register
@Component.use__interface
@ComponentMetadata.create('multiply', _('multiply_display_name'), _('multiply_description'), [],
                          level=ComponentMetadata.Level.Expression, icon='multiply.svg')
class CMultiply(CArithmeticOperator):
    symbol = '*'


@clk.register
@Component.use__interface
@ComponentMetadata.create('divide', _('divide_display_name'), _('divide_description'), [],
                          level=ComponentMetadata.Level.Expression, icon='divide.svg')
class CDivide(CArithmeticOperator):
    symbol = '/'


@clk.register
@Component.use__interface
@ComponentMetadata.create('modulus', _('modulus_display_name'), _('modulus_description'), [],
                          level=ComponentMetadata.Level.Expression, icon='modulus.svg')
class CModulus(CArithmeticOperator):
    symbol = '%'
