# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QWidget

from alias import *
from core.component import Component, ComponentMetadata, IComponentInterface
from core.graphics import IComponentGraphics
from kits.common.library import CLLibrary
from kits.common.clk import clk
from kits.common.localization import _
from kits.common.validation import attach_source_check, attach_source_lint


@clk.register
@Component.use__interface
@ComponentMetadata.create('native', _('native_display_name'), _('native_description'), [],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Builtin)
class CNative(Component):
    class FNativeInterface(IComponentInterface):
        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            # A plain hyper-text edit accepts only text code: unlike a visual code edit,
            # it offers no completion, so components can never be embedded inside
            self.edit_code = graphics.create_hypertext_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 60))
            self.edit_code.setPlaceholderText(_('placeholder_code'))
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.edit_code, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
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
        self._interface = CNative.FNativeInterface(graphics)
        # Immediate static checking of the hand-written code: the registered
        # checkers validate the text while it is being written and mark the
        # edit red when it cannot compile (see ``kits.common.validation``);
        # the asynchronous lint then reports deeper problems gently
        attach_source_check(self._interface.edit_code)
        attach_source_lint(self._interface.edit_code)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_code  # The code body is the only required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_code]

    def __serialize__(self) -> dict:
        return {
            'code': self._interface.edit_code.toPlainText()
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a native-code component from its serialization.

        The constructor reconstructs the interface (whose code edit is empty);
        the archived text is then loaded into that edit in place, since its
        reference is held by the interface layout.
        """
        require_member(data, 'code')
        require_type(data['code'], string, 'code')
        component = cls(parent, graphics)
        component._interface.edit_code.setPlainText(data['code'])
        return component
