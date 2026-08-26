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
from kits.common.validation import attach_identifier_check


def counter_name(occupied: ICollection[string]) -> string:
    """
    Pick an unoccupied counter name for a count loop.

    Candidates are tried in order: the conventional ``i``, ``j``, ``k`` first;
    when all of them are occupied, fall back to ``_ec_xxx`` with ``xxx`` counting
    up from 1. The caller occupies the returned name for the loop's scope.
    This naming scheme is the single extension point for loop counters: future
    features that need to address a loop iteration (e.g. "do something at the
    y-th repetition") should derive their identifiers here.
    :param occupied: identifiers already occupied by enclosing loop scopes
    :return: the first candidate that is not occupied yet
    """
    for candidate in ('i', 'j', 'k'):
        if candidate not in occupied:
            return candidate
    index = 1
    while f'_ec_{index}' in occupied:
        index += 1
    return f'_ec_{index}'


@clk.register
@Component.use__interface
@ComponentMetadata.create('loop', _('loop_display_name'), _('loop_description'), [],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Builtin,
                          icon='while.svg')
class CLoop(Component):
    class FLoopInterface(IComponentInterface):
        lt_while: Final[string] = _('label_while')
        lt_do: Final[string] = _('label_do')

        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_while = graphics.create_native_label(self.lt_while, self.font)
            graphics.label_metric_width(self.label_while, modify=True)
            self.label_do = graphics.create_native_label(self.lt_do, self.font)
            graphics.label_metric_width(self.label_do, modify=True)
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_cond = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            self.edit_body = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            # The condition is an expression context; the body is a statement block
            self.edit_cond.filter(ComponentMetadata.Level.Expression)
            self.edit_body.filter(ComponentMetadata.Level.Statement)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_while, null, null, null)
            # Reserve label_do plus the padding before it, so the row ends at the right margin
            self.layout.add_element(self.edit_cond, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    CLLibrary.GLinearLayout.FillWidth - self.label_do.width()
                                    - self.layout.horizonal_padding,
                                    null, graphics=graphics)
            self.layout.add_element(self.label_do, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_body, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
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
        self._interface = CLoop.FLoopInterface(graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_cond  # The condition is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_cond, self._interface.edit_body]

    def __serialize__(self) -> dict:
        return {
            'cond': serialize(self._interface.edit_cond),
            'body': serialize(self._interface.edit_body)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a loop from its serialization.

        The constructor reconstructs the interface (whose nested edits are empty);
        the archived contents are then loaded into those edits in place, since
        their references are held by the interface layout.
        """
        require_member(data, 'cond', 'body')
        component = cls(parent, graphics)
        component._interface.edit_cond.load(data['cond'])
        component._interface.edit_body.load(data['body'])
        return component


@clk.register
@Component.use__interface
@ComponentMetadata.create('for', _('for_display_name'), _('for_description'), [],
                          level=ComponentMetadata.Level.Statement,
                          kind=ComponentMetadata.Kind.Builtin,
                          icon='for.svg')
class CFor(Component):
    class FForInterface(IComponentInterface):
        lt_repeat: Final[string] = _('label_repeat')
        lt_times: Final[string] = _('label_times')
        lt_counter: Final[string] = _('label_counter')

        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_repeat = graphics.create_native_label(self.lt_repeat, self.font)
            graphics.label_metric_width(self.label_repeat, modify=True)
            self.label_times = graphics.create_native_label(self.lt_times, self.font)
            graphics.label_metric_width(self.label_times, modify=True)
            self.label_counter = graphics.create_native_label(self.lt_counter, self.font)
            graphics.label_metric_width(self.label_counter, modify=True)
            # The counter name is a plain identifier: a single-line edit never embeds
            # components; leaving it empty lets compilation name the counter itself
            self.edit_counter = graphics.create_lineedit(QRectF(0, 0, 120, 24))
            self.edit_counter.setPlaceholderText(_('placeholder_counter'))
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_count = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            self.edit_body = graphics.create_visual_code_edit(QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            # The repetition count is an expression context; the body is a statement block
            self.edit_count.filter(ComponentMetadata.Level.Expression)
            self.edit_body.filter(ComponentMetadata.Level.Statement)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_repeat, null, null, null)
            # Reserve label_times plus the padding before it, so the row ends at the right margin
            self.layout.add_element(self.edit_count, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                    CLLibrary.GLinearLayout.FillWidth - self.label_times.width()
                                    - self.layout.horizonal_padding,
                                    null, graphics=graphics)
            self.layout.add_element(self.label_times, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.label_counter, CLLibrary.GLinearLayout.ElementRowPolicy.New, null, null)
            self.layout.add_element(self.edit_counter, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.edit_body, CLLibrary.GLinearLayout.ElementRowPolicy.Exclusive,
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
        self._interface = CFor.FForInterface(graphics)
        # Immediate static checking: an invalid counter name marks the field red
        # while it is being written (see ``kits.common.validation``)
        attach_identifier_check(self._interface.edit_counter)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_count  # The repetition count is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_count, self._interface.edit_counter, self._interface.edit_body]

    def __serialize__(self) -> dict:
        return {
            'count': serialize(self._interface.edit_count),
            'counter': self._interface.edit_counter.text(),
            'body': serialize(self._interface.edit_body)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a count loop from its serialization.

        The constructor reconstructs the interface (whose nested edits are empty);
        the archived contents are then loaded into those edits in place, since
        their references are held by the interface layout.
        """
        require_member(data, 'count', 'body')
        component = cls(parent, graphics)
        component._interface.edit_count.load(data['count'])
        # 'counter' is absent in archives made before the counter field existed
        counter = data.get('counter', '')
        require_type(counter, string, 'counter')
        component._interface.edit_counter.setText(counter)
        component._interface.edit_body.load(data['body'])
        return component
