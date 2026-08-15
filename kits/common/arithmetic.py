# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont

from alias import *
from core.component import Component, ComponentMetadata, IComponentInterface
from core.graphics import IComponentGraphics
from kits.common.library import CLLibrary
from kits.common.clk import clk
from kits.common.localization import _


class CArithmeticOperator(Component):
    """
    Base class of arithmetic operator components.

    An operator carries no fields: its interface consists solely of the operator
    symbol (the localized display name), so its serialization archive is empty.
    """
    class FOperatorInterface(IComponentInterface):
        def __init__(self, graphics: IComponentGraphics, symbol: string):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_symbol = graphics.create_native_label(symbol, self.font)
            graphics.label_metric_width(self.label_symbol, modify=True)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_symbol, null, null, null)
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
        self._interface = CArithmeticOperator.FOperatorInterface(graphics, self.meta().display_name)

    def __serialize__(self) -> dict:
        return {}

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore an operator from its serialization.

        Operators carry no fields, so the archive is empty and reconstructing
        the interface through the constructor suffices.
        """
        maybe_unused(data)
        return cls(parent, graphics)


@clk.register
@Component.use__interface
@ComponentMetadata.create('plus', _('plus_display_name'), _('plus_description'), [])
class CPlus(CArithmeticOperator):
    pass


@clk.register
@Component.use__interface
@ComponentMetadata.create('minus', _('minus_display_name'), _('minus_description'), [])
class CMinus(CArithmeticOperator):
    pass


@clk.register
@Component.use__interface
@ComponentMetadata.create('multiply', _('multiply_display_name'), _('multiply_description'), [])
class CMultiply(CArithmeticOperator):
    pass


@clk.register
@Component.use__interface
@ComponentMetadata.create('divide', _('divide_display_name'), _('divide_description'), [])
class CDivide(CArithmeticOperator):
    pass


@clk.register
@Component.use__interface
@ComponentMetadata.create('modulus', _('modulus_display_name'), _('modulus_description'), [])
class CModulus(CArithmeticOperator):
    pass
