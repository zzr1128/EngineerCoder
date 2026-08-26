# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, QObject, QRectF
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget

from alias import *
from core.component import Component, ComponentMetadata, IComponentInterface
from core.environment import Environment
from core.graphics import IComponentGraphics
from kits.common.clk import clk
from kits.common.library import CLLibrary
from kits.common.localization import _
from kits.common.validation import attach_identifier_check, attach_source_lint


class _NameCommitWatcher(QObject):
    """Reports when the assignment target edit loses focus, so the component can
    commit the name (e.g. derive the type of externally defined variable)."""

    def __init__(self, on_commit: Callable[[], void]):
        super().__init__()
        self._on_commit = on_commit

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        maybe_unused(watched)
        if event.type() == QEvent.Type.FocusOut:
            self._on_commit()
        return False


# Type qualifiers a declared type may carry; the base type follows them
_TYPE_QUALIFIERS: Final[frozenset[string]] = frozenset(
    ('const', 'static', 'extern', 'unsigned', 'signed', 'volatile', 'struct'))
# Base C types mapped onto the type options of the assignment
_TYPE_OPTIONS: Final[IDictionary[string, string]] = {
    'real': 'real', 'float': 'real', 'double': 'real',
    'int': 'int', 'long': 'int', 'short': 'int', 'bool': 'int', 'size_t': 'int',
    'char': 'char',
}


@clk.register
@Component.use__interface
@ComponentMetadata.create('assign', _('assign_display_name'), _('assign_description'), [],
                          level=ComponentMetadata.Level.Statement,
                          icon='assign.svg')
class CAssign(Component):
    class FAssignInterface(IComponentInterface):
        lt_value_of: Final[string] = _('label_value_of')
        lt_to: Final[string] = _('label_to')
        lt_constant: Final[string] = _('label_constant')
        lt_local: Final[string] = _('label_local')
        lt_type: Final[string] = _('label_type')
        lt_type_real: Final[string] = _('type_real')
        lt_type_int: Final[string] = _('type_int')
        lt_type_char: Final[string] = _('type_char')

        def __init__(self, graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            self.label_value_of = graphics.create_native_label(self.lt_value_of, self.font)
            graphics.label_metric_width(self.label_value_of, modify=True)
            self.label_to = graphics.create_native_label(self.lt_to, self.font)
            graphics.label_metric_width(self.label_to, modify=True)
            self.label_type = graphics.create_native_label(self.lt_type, self.font)
            graphics.label_metric_width(self.label_type, modify=True)
            # The assignment target is a name (or a member access): a derived-only
            # visual code edit completes the variable names the project introduces,
            # embedding nothing but member components
            self.edit_name = graphics.create_visual_code_edit(QRectF(0, 0, 120, 24))
            self.edit_name.setDerivedCompletionsEnabled(True, ('clk.field',))
            # A placeholder example keeps the field approachable for users without
            # a programming background
            self.edit_name.setPlaceholderText(_('placeholder_name'))
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_value = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 30))
            # The assigned value is an expression context
            self.edit_value.filter(ComponentMetadata.Level.Expression)
            self.edit_value.setPlaceholderText(_('placeholder_value'))
            self.check_constant = graphics.create_checkbox(self.lt_constant, self.font)
            self.check_local = graphics.create_checkbox(self.lt_local, self.font)
            # The type is chosen from the options the kit offers (see
            # ``CAssign._type_options``); each option carries the C type key it
            # stands for as its item data
            self.edit_type = graphics.create_combobox(QRectF(0, 0, 120, 24))
            self.edit_type.addItem('', '')
            for label, key in CAssign._type_options():
                self.edit_type.addItem(label, key)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_value_of, null, null, null)
            self.layout.add_element(self.edit_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null,
                                    graphics=graphics)
            self.layout.add_element(self.label_to, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            # Reserve both check boxes plus the paddings before them, so the row ends at the right margin
            self.layout.add_element(self.edit_value, CLLibrary.GLinearLayout.ElementRowPolicy.New,
                                    CLLibrary.GLinearLayout.FillWidth - self.check_constant.width()
                                    - self.check_local.width() - 2 * self.layout.horizonal_padding,
                                    null, graphics=graphics)
            self.layout.add_element(self.check_constant, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.check_local, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            self.layout.add_element(self.label_type, CLLibrary.GLinearLayout.ElementRowPolicy.New, null, null)
            self.layout.add_element(self.edit_type, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
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
        # Autofill state of the type field: manual input suppresses it until the
        # field becomes empty again; programmatic fills pass under the guard
        self._type_manual: bool = False
        self._type_guard: bool = False
        # noinspection bad-argument-type
        self._interface.edit_type.currentIndexChanged.connect(self._on_type_changed)
        self._name_watcher = _NameCommitWatcher(self._commit_name)
        self._interface.edit_name.installEventFilter(self._name_watcher)
        # Immediate static checking: an invalid assignment target marks the field
        # red while it is being written (see ``kits.common.validation``)
        attach_identifier_check(self._interface.edit_name)
        # The assigned value is hand-written code: the asynchronous lint checks
        # it gently (wrapped into a minimal translation unit)
        attach_source_lint(self._interface.edit_value, fragment=True)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_name  # The assignment target is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_name, self._interface.edit_value,
                self._interface.check_constant, self._interface.check_local,
                self._interface.edit_type]

    def _on_type_changed(self, index: int) -> void:
        """Track manual edits of the type field: once the user chose an option,
        autofilling stops until the field becomes empty again."""
        maybe_unused(index)
        if self._type_guard:
            return
        self._type_manual = bool(self._interface.edit_type.currentData())

    def _commit_name(self) -> void:
        """Commit the assignment target: when it names a variable the project
        defines, fill the type field unless the user edited it manually."""
        if self._type_manual:
            return
        name = self._interface.edit_name.toPlainText().strip()
        if not name or '\uFFFC' in name:  # A member access has no single type
            return
        declared = self._lookup_type(name)
        if not declared:
            return
        self._select_type(declared)

    def _select_type(self, declared: string) -> void:
        """Select the type option a declared type stands for; the selection stays
        untouched when no option matches."""
        combo = self._interface.edit_type
        index = combo.findData(declared)
        if index < 0:
            index = combo.findData(CAssign._type_key(declared))
        if index < 0:
            return
        self._type_guard = True
        try:
            combo.setCurrentIndex(index)
        finally:
            self._type_guard = False

    @staticmethod
    def _type_key(declared: string) -> string:
        """The C type key (the item data of the type options) a declared type
        stands for: qualifiers are skipped, the base type maps onto the options."""
        for token in reversed(declared.split()):
            token = token.rstrip('*')
            if token and token not in _TYPE_QUALIFIERS:
                return _TYPE_OPTIONS.get(token, '')
        return ''

    @staticmethod
    def _type_options() -> IList[tuple[string, string]]:
        """The options of the type field: the first registered completer that
        offers options decides (the kit customizes the selection, see
        ``Completer.type_options``); without one, the built-in C scalar types
        stay on offer."""
        environment = Environment.instance()
        if environment.project is not null:
            for completer_type in environment.completers:
                options = completer_type(environment.project).type_options()
                if options:
                    return options
        interface = CAssign.FAssignInterface
        return [(interface.lt_type_real, 'real'),
                (interface.lt_type_int, 'int'),
                (interface.lt_type_char, 'char')]

    @staticmethod
    def _lookup_type(name: string) -> string:
        """Ask the registered completers for the declared type of project variable."""
        environment = Environment.instance()
        if environment.project is null:
            return ''
        for completer_type in environment.completers:
            declared = completer_type(environment.project).lookup_type(name)
            if declared:
                return declared
        return ''

    def __serialize__(self) -> dict:
        return {
            'name': serialize(self._interface.edit_name),
            'value': serialize(self._interface.edit_value),
            'constant': self._interface.check_constant.isChecked(),
            'local_only': self._interface.check_local.isChecked(),
            'type': self._interface.edit_type.currentData() or ''
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore an assignment from its serialization.

        The constructor reconstructs the interface (whose edits are empty and
        whose check boxes are unchecked); the archived contents are then loaded
        into those controls in place, since their references are held by the
        interface layout.
        """
        require_member(data, 'name', 'value', 'constant')
        name = data['name']
        if isinstance(name, string):
            # Archives made before the target could embed components kept a plain name
            name = {'text': name, 'components': []}
        require_type(name, dict, 'name')
        require_type(data['constant'], bool, 'constant')
        component = cls(parent, graphics)
        component._interface.edit_name.load(name)
        component._interface.edit_value.load(data['value'])
        component._interface.check_constant.setChecked(data['constant'])
        # Archives evolved through three annotation shapes: none at all (the
        # assignment stayed local), the legacy ``visibility`` (``auto`` lifted
        # the declaration, so the inversion feeds the local-only check), and
        # the current ``local_only`` flag
        if 'local_only' in data:
            local_only = bool(data['local_only'])
        elif 'visibility' in data:
            require_type(data['visibility'], string, 'visibility')
            local_only = data['visibility'] != 'auto'
        else:
            local_only = True
        component._interface.check_local.setChecked(local_only)
        # 'type' is absent in archives made before the field existed; restore
        # under the guard so it does not count as a manual edit
        component._type_guard = True
        component._select_type(data.get('type', ''))
        component._type_guard = False
        return component
