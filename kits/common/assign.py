# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget

from alias import *
from core.component import Component, ComponentMetadata, IComponentInterface
from core.graphics import IComponentGraphics
from kits.common.library import CLLibrary
from kits.common.clk import clk
from kits.common.localization import _


@clk.register
@Component.use__interface
@ComponentMetadata.create('assign', _('assign_display_name'), _('assign_description'), [],
                          level=ComponentMetadata.Level.Statement)
class CAssign(Component):
    class FAssignInterface(IComponentInterface):
        lt_value_of: Final[string] = _('label_value_of')
        lt_to: Final[string] = _('label_to')
        lt_constant: Final[string] = _('label_constant')

        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_value_of = graphics.create_native_label(self.lt_value_of, self.font)
            graphics.label_metric_width(self.label_value_of, modify=True)
            self.label_to = graphics.create_native_label(self.lt_to, self.font)
            graphics.label_metric_width(self.label_to, modify=True)
            # The assignment target is a plain name: a single-line edit never embeds components
            self.edit_name = graphics.create_lineedit(QRectF(0, 0, 120, 24))
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_value = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            # The assigned value is an expression context
            self.edit_value.filter(ComponentMetadata.Level.Expression)
            self.check_constant = graphics.create_checkbox(self.lt_constant, self.font)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_value_of, null, null, null)
            self.layout.add_element(self.edit_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.label_to, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            # Reserve the check box plus the padding before it, so the row ends at the right margin
            self.layout.add_element(self.edit_value, CLLibrary.GLinearLayout.ElementRowPolicy.New,
                                    CLLibrary.GLinearLayout.FillWidth - self.check_constant.width()
                                    - self.layout.horizonal_padding,
                                    null, graphics=graphics)
            self.layout.add_element(self.check_constant, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
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
        self._interface = CAssign.FAssignInterface(graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_name  # The assignment target is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_name, self._interface.edit_value, self._interface.check_constant]

    def __serialize__(self) -> dict:
        return {
            'name': self._interface.edit_name.text(),
            'value': serialize(self._interface.edit_value),
            'constant': self._interface.check_constant.isChecked()
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore an assignment from its serialization.

        The constructor reconstructs the interface (whose value edit is empty and
        whose check box is unchecked); the archived contents are then loaded into
        those controls in place, since their references are held by the interface layout.
        """
        require_member(data, 'name', 'value', 'constant')
        require_type(data['name'], string, 'name')
        require_type(data['constant'], bool, 'constant')
        component = cls(parent, graphics)
        component._interface.edit_name.setText(data['name'])
        component._interface.edit_value.load(data['value'])
        component._interface.check_constant.setChecked(data['constant'])
        return component
