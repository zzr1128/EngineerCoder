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


@clk.register
@Component.use__interface
@ComponentMetadata.create('br', _('display_name'), _('description'), [],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Builtin)
class CBranch(Component):
    class FBranchInterface(IComponentInterface):
        lt_if: Final[string] = _('label_if')
        lt_then: Final[string] = _('label_then')
        lt_else: Final[string] = _('label_else')

        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_if = graphics.create_native_label(self.lt_if, self.font)
            graphics.label_metric_width(self.label_if, modify=True)
            self.label_then = graphics.create_native_label(self.lt_then, self.font)
            graphics.label_metric_width(self.label_then, modify=True)
            self.label_else = graphics.create_native_label(self.lt_else, self.font)
            graphics.label_metric_width(self.label_else, modify=True)
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_cond = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            self.edit_then = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            self.edit_else = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            # The condition is an expression context; the branches are statement blocks
            self.edit_cond.filter(ComponentMetadata.Level.Expression)
            self.edit_then.filter(ComponentMetadata.Level.Statement)
            self.edit_else.filter(ComponentMetadata.Level.Statement)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_if, null, null, null)
            # Reserve label_then plus the padding before it, so the row ends at the right margin
            self.layout.add_element(self.edit_cond, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    CLLibrary.GLinearLayout.FillWidth - self.label_then.width()
                                    - self.layout.horizonal_padding,
                                    null, graphics=graphics)
            self.layout.add_element(self.label_then, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_then, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)
            self.layout.add_element(self.label_else, null, null, null)
            self.layout.add_element(self.edit_else, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
                                    CLLibrary.GLinearLayout.FillWidth, null, graphics=graphics)
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
        self._interface = CBranch.FBranchInterface(graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_cond  # The condition is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_cond, self._interface.edit_then, self._interface.edit_else]

    def __serialize__(self) -> dict:
        return {
            'cond': serialize(self._interface.edit_cond),
            'then': serialize(self._interface.edit_then),
            'else': serialize(self._interface.edit_else)
        }
    
    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a branch from its serialization.
    
        The constructor reconstructs the interface (whose nested edits are empty);
        the archived contents are then loaded into those edits in place, since
        their references are held by the interface layout.
        """
        require_member(data, 'cond', 'then', 'else')
        component = cls(parent, graphics)
        component._interface.edit_cond.load(data['cond'])
        component._interface.edit_then.load(data['then'])
        component._interface.edit_else.load(data['else'])
        return component