# -*- coding: utf-8 -*-
"""
General (solver-wide) UDF macros of Ansys Fluent as native UDF components, and
the translation unit that collects them into a UDF source file.

Every macro component wraps one of the ``DEFINE_*`` macros that register a
callback with the Fluent solver: the user supplies the function name, the
identifiers the macro parameters declare, and the function body; compilation
emits the macro invocation followed by the body block, e.g.::

    DEFINE_ADJUST(my_adjust, d)
    {
        ...
    }

These macros define complete functions, so the components carry the ``Domain``
level: they may appear in top-level (file) contexts only, never nested inside
statement blocks (see ``VisualCodeEdit.filter``). The body edit therefore
filters at the ``Statement`` level.

``CTranslationUnit`` is the document root of a UDF script: a whole-page visual
code edit hosting the macros (and free C declarations), which compiles into
one C translation unit starting with ``#include "udf.h"``.
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from alias import *
from core.build import Compiler
from core.component import Component, ComponentMetadata, IComponentInterface
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.kit import KitManager
from kits.common.library import CLLibrary
from kits.fluent.fluent import UDF, fluent
from kits.fluent.localization import _


class CFluentMacro(Component, abstract):
    """
    Base of the ``DEFINE_*`` macro components.

    Subclasses declare, besides the metadata, the macro name emitted to the
    source (``macro``), the identifiers of the parameters the macro declares
    after the function name (``args_spec``, empty for parameterless macros)
    and the completion keyword (``completion_keyword``). The interface, the
    serialization contract and the compilation are shared by the base.
    """

    # Name of the DEFINE_* macro as it appears in the generated source
    macro: ClassVar[string] = ''
    # (label, identifier) pairs of the macro parameters following the name
    args_spec: ClassVar[tuple[tuple[string, string], ...]] = ()
    # Keyword that inserts this component through code completion
    completion_keyword: ClassVar[string] = ''

    class FMacroInterface(IComponentInterface):
        lt_name: Final[string] = _('label_name')
        lt_body: Final[string] = _('label_body')

        def __init__(self, owner: typeof['CFluentMacro'], graphics: IComponentGraphics):
            super().__init__(graphics)
            self.font = QFont("Arial", 10)
            macro_font = QFont("Courier New", 10, QFont.Weight.Bold)
            self.label_macro = graphics.create_native_label(owner.macro, macro_font)
            graphics.label_metric_width(self.label_macro, modify=True)
            # Every DEFINE_* macro names the function it declares, so the name
            # field is always captioned with the identifier label
            self.label_name = graphics.create_native_label(self.lt_name, self.font)
            graphics.label_metric_width(self.label_name, modify=True)
            self.label_body = graphics.create_native_label(self.lt_body, self.font)
            graphics.label_metric_width(self.label_body, modify=True)
            # A short caption restating what the macro is for in plain words (the
            # localized component description), so non-programmer users can tell
            # the macros apart; drop the macro-name prefix the description carries
            brief = owner.meta().description
            for separator in ('：', ': '):  # Punctuation of both locale languages
                if brief.startswith(owner.macro + separator):
                    brief = brief[len(owner.macro) + len(separator):]
                    break
            self.label_brief = graphics.create_native_label(brief, self.font)
            graphics.label_metric_width(self.label_brief, modify=True)
            try:
                colors = Environment.instance().theme.colors
                subdued = QColor.fromRgb(colors.foreground.rgb() // 2 + colors.background.rgb() // 2)
            except Exception:  # Headless contexts without a loaded theme
                subdued = QColor('#808080')
            self.label_brief.setStyleSheet(f'color: {subdued.name()};')
            # The function name and the parameter identifiers are plain names:
            # single-line edits never embed components
            self.edit_name = graphics.create_lineedit(QRectF(0, 0, 140, 24))
            self.arg_labels: IList[QLabel] = []
            self.arg_edits: IList[QLineEdit] = []
            for label_text, arg_name in owner.args_spec:
                label = graphics.create_native_label(label_text, self.font)
                graphics.label_metric_width(label, modify=True)
                self.arg_labels.append(label)
                # Pre-fill the identifier the macro parameter conventionally uses
                edit = graphics.create_lineedit(QRectF(0, 0, 100, 24))
                edit.setText(arg_name)
                self.arg_edits.append(edit)
            # Visual code edits accept code snippets and components inserted via completion
            self.edit_body = graphics.create_visual_code_edit(
                QRectF(0, 0, CLLibrary.GLinearLayout.FillWidth - 10, 60))
            # A function body is a statement context; Domain-level macros never nest in it
            self.edit_body.filter(ComponentMetadata.Level.Statement)
            self.layout = CLLibrary.GLinearLayout()
            self.layout.add_element(self.label_macro, null, null, null)
            if self.arg_labels:
                # Reserve the identifier label, the argument labels and identifier
                # edits plus the paddings before them, so the header row ends at
                # the right margin while it fits the container
                reserved = self.label_name.width() + self.layout.horizonal_padding \
                           + sum(label.width() for label in self.arg_labels) \
                           + sum(edit.width() for edit in self.arg_edits) \
                           + 2 * len(self.arg_labels) * self.layout.horizonal_padding
                self.layout.add_element(self.label_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        null, null)
                # The name edit never shrinks below its natural width: when the
                # header is too long for the container (many parameters), the
                # argument pairs wrap below it instead of spilling past the edge
                self.layout.add_element(self.edit_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        CLLibrary.GLinearLayout.FillWidth - reserved,
                                        null, min_width=self.edit_name.width())
                for label, edit in zip(self.arg_labels, self.arg_edits):
                    # A label may start a new row; its edit glues to it (NoBreak),
                    # so the layout wraps the pair as a whole
                    self.layout.add_element(label, CLLibrary.GLinearLayout.ElementRowPolicy.Default, null, null)
                    self.layout.add_element(edit, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak, null, null)
            else:
                self.layout.add_element(self.label_name, CLLibrary.GLinearLayout.ElementRowPolicy.NoBreak,
                                        null, null)
                self.layout.add_element(self.edit_name, CLLibrary.GLinearLayout.ElementRowPolicy.Break, null, null)
            self.layout.add_element(self.label_brief, CLLibrary.GLinearLayout.ElementRowPolicy.New, null, null)
            self.layout.add_element(self.label_body, null, null, null)
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
        self._interface = CFluentMacro.FMacroInterface(type(self), graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_name  # The function name is the first required field

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_name, *self._interface.arg_edits, self._interface.edit_body]

    def __serialize__(self) -> dict:
        return {
            'name': self._interface.edit_name.text(),
            'args': [edit.text() for edit in self._interface.arg_edits],
            'body': serialize(self._interface.edit_body)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a macro component from its serialization.

        The constructor reconstructs the interface (whose fields are empty);
        the archived contents are then loaded into those controls in place,
        since their references are held by the interface layout.
        """
        require_member(data, 'name', 'args', 'body')
        require_type(data['name'], string, 'name')
        require_type(data['args'], list, 'args')
        if len(data['args']) != len(cls.args_spec):
            raise SerializationError(f'{cls.meta().name} expects {len(cls.args_spec)} argument(s), '
                                     f'got {len(data["args"])}')
        component = cls(parent, graphics)
        component._interface.edit_name.setText(data['name'])
        for edit, arg in zip(component._interface.arg_edits, data['args']):
            require_type(arg, string, 'args')
            edit.setText(arg)
        component._interface.edit_body.load(data['body'])
        return component

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        """
        Render the archive of this macro into UDF source: the macro invocation
        followed by the body block.

        The UDF convention requires every macro parameter to stay on the same
        line as the macro name, hence the header is always a single line.
        """
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        require_member(data, 'name', 'args', 'body')
        require_type(data['name'], string, 'name')
        require_type(data['args'], list, 'args')
        if len(data['args']) != len(cls.args_spec):
            raise SerializationError(f'{cls.meta().name} expects {len(cls.args_spec)} argument(s), '
                                     f'got {len(data["args"])}')
        parts = [data['name'].strip()]
        parts.extend(string(arg).strip() for arg in data['args'])
        body = udf.render_edit(data['body'], builder)
        return f'{cls.macro}({", ".join(parts)})\n{udf._block(body)}'

    def compile(self, builder: Compiler) -> void:
        """
        Emit ``MACRO(name, args...) { body }`` into the UDF products.
        """
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(type(self).render(serialize(self), builder))


@fluent.register
@Component.use__interface
@ComponentMetadata.create('adjust', _('adjust_display_name'), _('adjust_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CAdjust(CFluentMacro):
    """``DEFINE_ADJUST(name, d)``: general-purpose UDF called by Fluent at the
    end of every iteration; ``d`` names the ``Domain *`` parameter."""
    macro = 'DEFINE_ADJUST'
    args_spec = ((_('label_domain'), 'd'), )
    completion_keyword = 'adjust'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('init', _('init_display_name'), _('init_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CInit(CFluentMacro):
    """``DEFINE_INIT(name, d)``: UDF called once right after the flow field is
    initialized; ``d`` names the ``Domain *`` parameter."""
    macro = 'DEFINE_INIT'
    args_spec = ((_('label_domain'), 'd'), )
    completion_keyword = 'init'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('execute_at_end', _('execute_at_end_display_name'), _('execute_at_end_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CExecuteAtEnd(CFluentMacro):
    """``DEFINE_EXECUTE_AT_END(name)``: UDF called after the calculation
    (or each time step) completes; it takes no parameters."""
    macro = 'DEFINE_EXECUTE_AT_END'
    completion_keyword = 'at_end'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('on_demand', _('on_demand_display_name'), _('on_demand_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class COnDemand(CFluentMacro):
    """``DEFINE_ON_DEMAND(name)``: UDF invoked manually by the user through
    Execute on Demand; it takes no parameters."""
    macro = 'DEFINE_ON_DEMAND'
    completion_keyword = 'on_demand'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('rw_file', _('rw_file_display_name'), _('rw_file_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CRwFile(CFluentMacro):
    """``DEFINE_RW_FILE(name, fp)``: UDF writing user data to, or reading it
    back from, case/data files; ``fp`` names the ``FILE *`` parameter."""
    macro = 'DEFINE_RW_FILE'
    args_spec = ((_('label_fp'), 'fp'), )
    completion_keyword = 'rw_file'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('deltat', _('deltat_display_name'), _('deltat_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CDeltaT(CFluentMacro):
    """``DEFINE_DELTAT(name, d)``: UDF returning the adaptive time step size
    for the next time step; ``d`` names the ``Domain *`` parameter and the
    body must return a ``real``."""
    macro = 'DEFINE_DELTAT'
    args_spec = ((_('label_domain'), 'd'), )
    completion_keyword = 'deltat'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('execute_from_gui', _('from_gui_display_name'), _('from_gui_description'), [UDF],
                          level=ComponentMetadata.Level.Domain)
class CExecuteFromGui(CFluentMacro):
    """``DEFINE_EXECUTE_FROM_GUI(name, msg)``: UDF invoked from a user-defined
    GUI panel; ``msg`` names the ``int`` message-code parameter."""
    macro = 'DEFINE_EXECUTE_FROM_GUI'
    args_spec = ((_('label_msg'), 'msg'), )
    completion_keyword = 'from_gui'


@fluent.register
@Component.use__interface
@ComponentMetadata.create('translation_unit', _('translation_unit_display_name'), _('translation_unit_description'),
                          [UDF], level=ComponentMetadata.Level.Domain)
class CTranslationUnit(Component):
    """
    A C translation unit: the document root of a UDF script.

    The unit hosts the ``DEFINE_*`` macros and free C declarations (globals,
    ``typedef``s, helper functions) in one whole-page visual code edit, and
    compiles into one UDF source fragment starting with ``#include "udf.h"``.
    """

    # Margin left around the unit inside the canvas' client rectangle
    Margin: Final[float] = 10.

    class FUnitInterface(IComponentInterface):
        def __init__(self, owner: typeof['CTranslationUnit'], graphics: IComponentGraphics):
            super().__init__(graphics)
            maybe_unused(owner)
            margin = CTranslationUnit.Margin
            # Non-positive extents stretch the edit to the canvas edges minus the
            # margin (see EditionCanvas.translate_rect): the unit fills the client
            # rectangle of the canvas
            self.edit_body = graphics.create_visual_code_edit(QRectF(margin, margin, -margin, -margin))
            # A translation unit hosts the Domain-level DEFINE_* macros
            self.edit_body.filter(ComponentMetadata.Level.Domain)
            self.color = graphics.alloc_color()

        def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:
            # Locate figures and widgets at the UI origin of this interface
            graphics.push_anchor(self.origin)
            try:
                client = graphics.client_rect
                margin = CTranslationUnit.Margin
                # Never shrink below the client rectangle; growing contents still
                # extend the edit (and scroll the whole page)
                self.edit_body.setBasicHeight(int(max(client.height() - 2 * margin, 0.)))

                if painting:
                    graphics.disp_draw_frame(QRectF(margin, margin, client.width() - 2 * margin,
                                                    client.height() - 2 * margin),
                                             self.color, round_radius=5)
            finally:
                graphics.pop_anchor()

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        super().__init__(parent, graphics)
        self._interface = CTranslationUnit.FUnitInterface(type(self), graphics)

    def autoFocusWidget(self) -> Nullable[QWidget]:
        return self._interface.edit_body

    def editableWidgets(self) -> IList[QWidget]:
        return [self._interface.edit_body]

    def __serialize__(self) -> dict:
        return {
            'body': serialize(self._interface.edit_body)
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], parent: Nullable['Component'],
                graphics: IComponentGraphics) -> Self:
        """
        Restore a translation unit from its serialization.

        The constructor reconstructs the interface (whose edit is empty); the
        archived contents are then loaded into that edit in place, since its
        reference is held by the interface.
        """
        require_member(data, 'body')
        component = cls(parent, graphics)
        component._interface.edit_body.load(data['body'])
        return component

    def compile(self, builder: Compiler) -> void:
        """
        Emit the whole UDF source file: the required ``#include "udf.h"``
        followed by the rendered contents of the unit (macros and free C),
        preserving their order in the document.
        """
        from kits.fluent import udf  # Deferred: udf.py and general.py share the kit entry chain

        body = udf.render_unit(serialize(self._interface.edit_body), builder).strip()
        source = '#include "udf.h"'
        if body:
            source += f'\n\n{body}'
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(source)


# Contribute the completion keywords of the macro components to the global
# registry, so any visual code edit picks them up (filtered by level)
for _comp in (CAdjust, CInit, CExecuteAtEnd, COnDemand, CRwFile, CDeltaT, CExecuteFromGui):
    KitManager.instance().add_completion(_comp.completion_keyword,
                                         KitManager.merge_names('fluent', _comp.meta().name))
