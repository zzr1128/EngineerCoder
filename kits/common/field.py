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
@ComponentMetadata.create('field', _('field_display_name'), _('field_description'), [],
                          level=ComponentMetadata.Level.Expression)
class CField(Component):
    class FFieldInterface(IComponentInterface):
        lt_possessive: Final[string] = _('label_possessive')

        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_possessive = graphics.create_native_label(self.lt_possessive, self.font)
            graphics.label_metric_width(self.label_possessive, modify=True)
            # The owner and the member are plain names: auto-width edits grow with the entered
            # text (never below the declared width); completion is restricted to the suggestions
            # completers derive from the project (variables) so names never embed components
            self.edit_owner = graphics.create_visual_code_edit(QRectF(0, 0, 120, 24))
            self.edit_owner.setDerivedCompletionsEnabled(True)
            self.edit_owner.setAutoWidthEnabled(True)
            self.edit_member = graphics.create_visual_code_edit(QRectF(0, 0, 120, 24))
            self.edit_member.setDerivedCompletionsEnabled(True)
            self.edit_member.setAutoWidthEnabled(True)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.edit_owner, null, null, null, graphics=graphics)
            self.layout.add_element(self.label_possessive, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_member, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null,
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
        self._interface = CField.FFieldInterface(graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_owner  # The owner is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_owner, self._interface.edit_member]

    def __serialize__(self) -> dict:
        return {
            'owner': self._interface.edit_owner.toPlainText(),
            'member': self._interface.edit_member.toPlainText()
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a member-access component from its serialization.

        The constructor reconstructs the interface (whose name edits are empty);
        the archived texts are then loaded into those edits in place, since their
        references are held by the interface layout.
        """
        require_member(data, 'owner', 'member')
        require_type(data['owner'], string, 'owner')
        require_type(data['member'], string, 'member')
        component = cls(parent, graphics)
        component._interface.edit_owner.setPlainText(data['owner'])
        component._interface.edit_member.setPlainText(data['member'])
        return component
