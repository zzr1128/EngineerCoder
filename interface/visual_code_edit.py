# -*- coding: utf-8 -*-

from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QEvent, QObject, Qt, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, QTimer, Signal
from PySide6.QtGui import (QColor, QFocusEvent, QFontMetricsF, QKeyEvent, QMouseEvent, QMoveEvent, QPainter,
                           QResizeEvent, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QWidget)

from alias import *
from alias import Nullable
from core.component import Component, ComponentMetadata
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit, HyperTextObject


class _CompletionPopup(QFrame):
    """
    Top-level list popup of code completions.

    The popup never takes the input focus (``WA_ShowWithoutActivating``),
    so the editor keeps receiving key events while the popup is visible.

    The left pane lists the matching entries; the right pane details the
    description of the currently highlighted entry, like Visual Studio IntelliSense.
    """
    ListWidth: Final[int] = 280
    DetailWidth: Final[int] = 260
    MaxHeight: Final[int] = 240
    NoDescription: Final[string] = 'No description available.'

    def __init__(self):
        super().__init__(null, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.entries: IList['VisualCodeEdit.CompletionEntry'] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        self.list = QListWidget(self)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setFixedWidth(_CompletionPopup.ListWidth)
        layout.addWidget(self.list)

        # Detail pane showing the description of the highlighted entry
        self.detail = QLabel(self)
        self.detail.setFixedWidth(_CompletionPopup.DetailWidth)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self.detail)

        self.list.currentRowChanged.connect(self._refresh_detail)

    def set_entries(self, entries: IEnumerable['VisualCodeEdit.CompletionEntry']) -> void:
        """
        Refresh the popup contents with the specified completion entries.
        :param entries: completion entries to show
        """
        self.entries = list(entries)
        self.list.clear()
        for entry in self.entries:
            self.list.addItem(QListWidgetItem(f'{entry.keyword}    [{entry.component_name}]'))
        if self.entries:
            self.list.setCurrentRow(0)

        row_height = self.list.sizeHintForRow(0) if self.entries else 22
        row_height = max(row_height, 22)
        height = min(len(self.entries) * (row_height + 2) + 10, _CompletionPopup.MaxHeight)
        width = _CompletionPopup.ListWidth + _CompletionPopup.DetailWidth + 6
        self.setFixedSize(width, height)

    def current_entry(self) -> Nullable['VisualCodeEdit.CompletionEntry']:
        """
        :return: the currently highlighted entry, or null if there is none
        """
        row = self.list.currentRow()
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return null

    def entry_at(self, row: int) -> Nullable['VisualCodeEdit.CompletionEntry']:
        """
        :param row: row index in the list
        :return: the entry at the specified row, or null if out of range
        """
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return null

    def move_selection(self, delta: int) -> void:
        """
        Move the highlighted row by the specified delta (wrapping around).
        :param delta: rows to move (negative for moving upwards)
        """
        if not self.entries:
            return
        self.list.setCurrentRow((self.list.currentRow() + delta) % len(self.entries))

    @final
    def _refresh_detail(self, row: int) -> void:
        """
        Show the description of the entry at the specified row in the detail pane.
        :param row: row index of the highlighted entry
        """
        entry = self.entry_at(row)
        if entry is null:
            self.detail.clear()
            return
        description = entry.description.strip()
        self.detail.setText(description if description else _CompletionPopup.NoDescription)


class _ComponentInlineObject(HyperTextObject):
    """
    Inline placeholder of a component painted on the graphics canvas.

    The placeholder reserves the component's space in the text flow; every time the
    placeholder is drawn, the UI origin of the component on the canvas is synchronized
    with the placeholder position through the injected ``origin_sync`` callback.
    """

    def __init__(self, editor: HyperTextEdit, widget: QWidget, component: Component,
                 origin_sync: Callable[[Component, QPointF], void]):
        """
        :param editor: the edit the placeholder belongs to
        :param widget: placeholder widget reserving the component's space
        :param component: the component whose origin follows the placeholder
        :param origin_sync: callback invoked with the component and the new placeholder
            position (in viewport coordinates) each time the placeholder is drawn
        """
        super().__init__(editor, widget)
        self.component: Component = component
        self._origin_sync: Callable[[Component, QPointF], void] = origin_sync

    def intrinsicSize(self, doc: QTextDocument, posInDocument: int, fmt: QTextFormat, /) -> QSizeF:
        # A plain placeholder widget has an invalid sizeHint; use its (fixed) size instead
        size = self.widget.size()
        if size.width() > 0 and size.height() > 0:
            return QSizeF(size)
        return QSizeF(self.widget.sizeHint())

    def drawObject(self, painter: QPainter, rect: QRect | QRectF, doc: QTextDocument,
                   posInDocument: int, fmt: QTextFormat, /) -> void:
        x = int(rect.x() - self.editor.horizontalScrollBar().value())
        y = int(rect.y() - self.editor.verticalScrollBar().value())
        self.widget.move(x, y)
        if self.widget.isHidden():
            self.widget.show()
            self.editor.inlineObjectRestored.emit(self.widget)  # Reattach after undo/redo
        self._origin_sync(self.component, QPointF(x, y))


class VisualCodeEdit(HyperTextEdit):
    """
    Code editor based on ``HyperTextEdit`` that provides IDE-style code completion.

    While the user types, a completion popup lists the keywords matching the word
    being typed (e.g. ``if``). Confirming a completion (Enter/Return/Tab or clicking
    an item) removes the typed prefix and inserts the corresponding component
    **inline into the text flow**: an invisible placeholder reserves the component's
    space in the document while the component itself is painted on the graphics
    canvas, tracking the placeholder position.

    The UI start point of the inserted component is set via ``IComponentGraphics.push_anchor``
    and its client area is given by ``IComponentGraphics.client_rect`` derived from that anchor,
    spanning the width of the text column. For the alignment to hold, this edit should
    extend to the right edge of the canvas (e.g. created with a non-positive width).

    The edit grows to fit its contents without any height limit; when the contents
    outgrow the visible area, the whole canvas scrolls (the edit itself never shows
    scrollbars, so that nested components do not scroll independently of the page).

    Optionally, the edit can own its width instead of keeping the declared one
    (see ``setAutoWidthEnabled``): the width then follows the contents — the ideal
    (unwrapped) width of the document, reserving the width of one character when the
    document is empty and never falling below the declared width, so that contents
    shorter than the declared row still fill it. The width is capped at the space
    available on the canvas (from the edit's left edge to the canvas' right edge),
    so long lines wrap instead of overflowing the canvas.

    The editor itself has a translucent background (styled by the application's theme
    stylesheet) so that the figures painted on the canvas show through.
    """

    @dataclass
    class CompletionEntry:
        keyword: string           # Keyword typed by the user (e.g. 'if')
        component_name: string    # Complete name of the component (e.g. 'clk.br')
        description: string = ''  # Description shown in the popup detail pane

    DefaultCompletions: ClassVar[IList[CompletionEntry]] = [
        CompletionEntry('if', 'clk.br'),
        CompletionEntry('native', 'clk.native'),
        CompletionEntry('loop', 'clk.loop'),
        CompletionEntry('for', 'clk.for'),
        CompletionEntry('set', 'clk.assign'),
        CompletionEntry('plus', 'clk.plus'),
        CompletionEntry('minus', 'clk.minus'),
        CompletionEntry('multiply', 'clk.multiply'),
        CompletionEntry('divide', 'clk.divide'),
        CompletionEntry('modulus', 'clk.modulus'),
        CompletionEntry('member', 'clk.field'),
    ]

    # Emitted with the component name after a component is inserted from a completion.
    componentInserted: ClassVar[Signal] = Signal(string)

    def __init__(self, parent: Nullable[QWidget], graphics: IComponentGraphics):
        """
        :param parent: parent widget
        :param graphics: graphics interface of the canvas this edit belongs to
        """
        super().__init__(parent)
        self.graphics: IComponentGraphics = graphics
        # Whether code completion takes part in this edit (see ``setCompletionsEnabled``);
        # must exist before ``_sync_kit_completions`` runs below
        self._completions_enabled: bool = True
        self.completions: IList[VisualCodeEdit.CompletionEntry] = [
            VisualCodeEdit.CompletionEntry(entry.keyword, entry.component_name,
                                           entry.description or self._entry_description(entry.component_name))
            for entry in VisualCodeEdit.DefaultCompletions
        ]
        self._sync_kit_completions()  # Absorb the keywords kits have contributed so far
        self.inserted_components: IList[Component] = []
        self._spacer_components: IDictionary[string, Component] = {}  # Placeholder name -> component
        self._component_spacers: IDictionary[Component, QWidget] = {}  # Component -> placeholder
        self._component_occupations: IDictionary[Component, float] = {}  # Component -> right occupation

        self._popup: Nullable[_CompletionPopup] = null

        # Completion filter criteria (see ``filter``); a null level disables filtering
        self._filter_level: Nullable[int] = null
        self._filter_block: set[string] = set()
        self._filter_bypass: set[string] = set()

        # The inserted component currently marked as selected (deletion pending confirmation)
        self._selected_component: Nullable[Component] = null
        # Interface widgets of the inserted components (event-filtered) -> owning component
        self._widget_components: IDictionary[QWidget, Component] = {}

        # Width declared at creation; negative means extending to the right edge of the canvas
        self.declared_width: float = 0.
        self._auto_width_enabled: bool = False
        # Space on the right of the canvas the fitting width must not enter (the right
        # occupation of the enclosing component plus its layout margin); 0 for top-level edits
        self._auto_width_right_inset: float = 0.

        # The edit grows to fit its contents without any height limit; the whole canvas
        # scrolls when the contents outgrow the visible area. Scrollbars stay off: text
        # wraps at the column width, keeping the inserted components aligned with it
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # No frame; the background comes from the application stylesheet (translucent,
        # so that components painted on the canvas underneath remain visible)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def add_completion(self, keyword: string, component_name: string, description: string = '') -> void:
        """
        Append a completion entry (keyword mapped to a component).
        :param keyword: keyword that triggers the completion
        :param component_name: complete name of the component to insert
        :param description: description shown in the popup detail pane;
            resolved from the component metadata when left empty
        """
        self.completions.append(VisualCodeEdit.CompletionEntry(
            keyword, component_name, description or self._entry_description(component_name)))

    def setCompletionsEnabled(self, enabled: bool) -> void:
        """
        Enable or disable code completion in this edit.

        When disabled, the completion popup never shows, no typed keyword is confirmed
        into a component, and the keywords kits contribute are never absorbed: the entries
        absorbed so far are dropped as well, and restored when completion is enabled again.
        Unlike merely clearing ``completions`` (which the kit synchronization on every
        keystroke refills), the disabled state is persistent. Intended for plain-name
        fields that must never embed components.
        :param enabled: whether code completion takes part
        """
        if enabled == self._completions_enabled:
            return
        self._completions_enabled = enabled
        if enabled:
            # Rebuild the default entries, then absorb whatever kits contributed meanwhile
            self.completions[:] = [
                VisualCodeEdit.CompletionEntry(entry.keyword, entry.component_name,
                                               entry.description or self._entry_description(entry.component_name))
                for entry in VisualCodeEdit.DefaultCompletions
            ]
            self._sync_kit_completions()
        else:
            self._hide_popup()
            self.completions.clear()  # Plain names never complete into any component

    def completionsEnabled(self) -> bool:
        """
        :return: whether code completion takes part in this edit
        """
        return self._completions_enabled

    def filter(self, level: int, block: IEnumerable[string] = (), bypass: IEnumerable[string] = ()) -> void:
        """
        Restrict the code completion by component level.

        Only the components whose ``ComponentMetadata.level`` is less than or equal
        to the given level (or listed in ``bypass``) take part in the completion
        popup; the components listed in ``block`` never do (blocking wins over
        bypassing). The criteria apply on the fly, so entries added afterwards are
        filtered as well.
        :param level: maximum level of the components that may take part
        :param block: complete names of the components excluded from the completion
        :param bypass: complete names of the components taking part regardless of level
        """
        self._filter_level = level
        self._filter_block = set(block)
        self._filter_bypass = set(bypass)

    def clear_filter(self) -> void:
        """
        Remove the completion filter, letting every completion entry take part again.
        """
        self._filter_level = null
        self._filter_block = set()
        self._filter_bypass = set()

    @final
    def _sync_kit_completions(self) -> void:
        """
        Absorb the completion keywords kits have contributed to the kit manager
        registry (``KitManager.completions``) but this edit does not know yet.
        The level filter still applies to the absorbed entries (see ``filter``).
        """
        if not self._completions_enabled:  # Disabled edits never absorb kit keywords
            return
        kit_manager = Environment.instance().kit_manager
        for keyword, component_name in kit_manager.completions.items():
            if any(entry.component_name == component_name for entry in self.completions):
                continue
            self.add_completion(keyword, component_name)

    @final
    def _entry_description(self, component_name: string) -> string:
        """
        Resolve the description of a component from its metadata.
        :param component_name: complete name of the component
        :return: the description, or empty string when it cannot be resolved
        """
        # noinspection broad-exception
        try:
            return Environment.instance().kit_manager.lookup(component_name).description
        except Exception:
            return ''

    @final
    def _entry_level(self, component_name: string) -> int:
        """
        Resolve the level of a component from its metadata.
        :param component_name: complete name of the component
        :return: the level, or ``ComponentMetadata.Level.Zero`` when it cannot be
            resolved (unresolved components stay available everywhere)
        """
        # noinspection broad-exception
        try:
            return Environment.instance().kit_manager.lookup(component_name).level
        except Exception:
            return ComponentMetadata.Level.Zero

    @final
    def _entry_participates(self, entry: CompletionEntry) -> bool:
        """
        Whether a completion entry takes part in the completion popup under the
        current filter criteria (see ``filter``).
        """
        if self._filter_level is null:
            return True
        if entry.component_name in self._filter_block:
            return False
        if entry.component_name in self._filter_bypass:
            return True
        return self._entry_level(entry.component_name) <= self._filter_level

    def insert_branch(self) -> Nullable[Component]:
        """
        Insert a Branch component (the one bound to keyword ``if``) inline
        at the current text cursor position.
        :return: the inserted component, or null on failure
        """
        entry: Nullable[VisualCodeEdit.CompletionEntry] = null
        for candidate in self.completions:
            if candidate.component_name == 'clk.br':
                entry = candidate
                break
        if entry is null:
            entry = VisualCodeEdit.DefaultCompletions[0]
        return self.insert_component(entry)  # type: ignore

    def insert_component(self, entry: CompletionEntry) -> Nullable[Component]:
        """
        Insert the component bound to a completion entry inline into the text flow.

        An invisible placeholder reserving the component's space is inserted into the
        document at the text cursor; the component itself is painted on the graphics
        canvas. The UI start point of the component is set by pushing a graphics anchor
        whose client area (``IComponentGraphics.client_rect``) spans the width of the
        text column; the anchor is popped afterward (the component interface remembers
        its origin and re-pushes it in ``paint``). The placeholder keeps the component's
        canvas origin synchronized every time it is drawn.

        :param entry: the completion entry whose component is inserted
        :return: the inserted component, or null when the component cannot be resolved
        """
        canvas = self._canvas_widget()
        if canvas is null:
            return null
        try:
            meta = Environment.instance().kit_manager.lookup(entry.component_name)
        except LookupError:
            return null

        content_width = self._content_width()
        content_left = self._content_left()
        # noinspection unresolved-references
        occupation = max(canvas.width() - content_left - content_width, 0.)

        # Set the UI start point; the client area is given by graphics.client_rect,
        # spanning the text column width (narrowed by the right occupation)
        self.graphics.push_anchor(QPointF(content_left, 0.))
        self.graphics.push_right_occupation(occupation)
        try:
            component = meta.component_type(null, self.graphics)
            size = self._interface_size(component)
        finally:
            self.graphics.pop_occupation()
            self.graphics.pop_anchor()

        # Inline placeholder reserving the component's space in the text flow
        spacer = QWidget()
        spacer.setObjectName(f'vce.inline.{id(component)}')
        spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._spacer_components[spacer.objectName()] = component
        self._component_spacers[component] = spacer
        self._component_occupations[component] = occupation
        self._apply_auto_width_inset(component)
        self._insert_inline_component(spacer, component, QSize(int(size.width()), int(size.height())))
        spacer.show()  # Avoid taking the undo/redo restore path on the first draw

        self.graphics.add_interface(component.interface, occupation)
        self.inserted_components.append(component)

        # Refit the placeholder whenever the component (or its descendants) changes size;
        # watch the fields to route their Backspace/Delete through the selection
        for widget in self._interface_widgets(component):
            self._widget_components[widget] = component
            widget.installEventFilter(self)
            if isinstance(widget, HyperTextEdit):
                widget.layoutSpaceChanged.connect(lambda c=component: self._refit_component(c))

        # The layout is stale during contentsChange; force it and re-fit the edit height,
        # so the whole inline component becomes visible inside the edit
        self.document().documentLayout().documentSize()
        self.fitSize()

        # Locate the component at the placeholder immediately
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
        self._sync_component_origin(component, QPointF(self.cursorRect(cursor).topLeft()))

        # Let the component's first required field take the focus; otherwise the text
        # cursor already sits right after the inserted placeholder
        focus_widget = component.autoFocusWidget()
        if focus_widget is not null:
            focus_widget.setFocus()

        self.componentInserted.emit(entry.component_name)
        return component

    @final
    def _insert_inline_component(self, spacer: QWidget, component: Component, size: QSize) -> void:
        """
        Insert the placeholder of a component as inline object into the document.
        Similar to ``HyperTextEdit.insertObject`` but binds a ``_ComponentInlineObject``.

        The fixed size is applied after reparenting, because reparenting a top-level
        widget may drop its size constraints.
        """
        spacer.setParent(self.viewport())
        spacer.setFixedSize(size)

        interface = _ComponentInlineObject(self, spacer, component, self._sync_component_origin)
        doc_layout = self.document().documentLayout()
        doc_layout.registerHandler(interface.format_id, interface)

        fmt = QTextCharFormat()
        fmt.setObjectType(interface.format_id)
        fmt.setProperty(interface.property_id, spacer)

        cursor = self.textCursor()
        pos = cursor.position()
        # Insert the placeholder first: the emitted contentsChange shifts the recorded
        # positions of the objects at or after the insertion point; the new object is
        # recorded afterwards so that it is not shifted itself
        cursor.insertText('\uFFFC', fmt)
        obj = HyperTextEdit._InlineObject(interface, spacer, pos)
        self.objects[spacer.objectName()] = obj
        self.displaying_objects.insert(obj)
        self.setTextCursor(cursor)
        self.viewport().update()

    @final
    def _sync_component_origin(self, component: Component, viewport_point: QPointF) -> void:
        """
        Synchronize the UI origin of a component with the position of its inline placeholder.
        :param component: the component to synchronize
        :param viewport_point: position of the placeholder in viewport coordinates
        """
        canvas = self._canvas_widget()
        if canvas is null:
            return
        # noinspection bad-argument-type
        top_left = self.viewport().mapTo(canvas, viewport_point.toPoint())
        # The origin follows the placeholder itself: a component may sit mid-line after
        # preceding text, and pinning it to the column's left edge would paint over that text
        origin = QPointF(top_left)
        if component.interface.origin == origin:
            return
        if component.interface.origin.x() != origin.x():
            layout = getattr(component.interface, 'layout', null)
            if layout is not null and hasattr(layout, 'invalidate'):
                layout.invalidate()
        component.interface.origin = origin
        self.graphics.refresh()

    @final
    def _content_width(self) -> float:
        """
        :return: width of the available text column (viewport width minus document margins);
            using the real layout width (instead of ``document().textWidth()``) prevents
            inline placeholders from overrunning the viewport when the document width is stale
        """
        return float(max(self.viewport().width() - 2 * self.document().documentMargin(), 0.))

    @final
    def _content_left(self) -> float:
        """
        :return: x-coordination of the left edge of the text column in canvas coordinates
        """
        canvas = self._canvas_widget()
        if canvas is null:
            return 0.
        # noinspection bad-argument-type
        return float(self.viewport().mapTo(canvas, QPoint(0, 0)).x())

    @final
    def _refit_component(self, component: Component) -> void:
        """
        Recompute the size of an inserted component and resize its inline placeholder
        accordingly, e.g. when contents inside the component make it grow or shrink.
        """
        spacer = self._component_spacers.get(component, null)
        if spacer is null or component not in self.inserted_components:
            return

        self.graphics.push_anchor(component.interface.origin)
        self.graphics.push_right_occupation(self._component_occupations.get(component, 0.))
        try:
            size = self._interface_size(component)
        finally:
            self.graphics.pop_occupation()
            self.graphics.pop_anchor()

        width, height = int(size.width()), int(size.height())
        # noinspection unresolved-references
        if spacer.width() == width and spacer.height() == height:
            return

        # noinspection unresolved-references
        spacer.setFixedSize(width, height)
        self._update_occupation(component)
        self.document().adjustSize()  # Relayout the document with the new placeholder size
        self.fitSize()
        self.viewport().update()
        self.graphics.refresh()

    @final
    def _refit_after_resize(self) -> void:
        """
        Refit this edit and all inserted components after the geometry of this edit
        (or of the canvas) has changed horizontally, updating the right occupation
        and placeholder size of each component.
        """
        self.fitSize()
        for component in list(self.inserted_components):
            self._update_occupation(component)
            self._refit_component(component)

    @final
    def _update_occupation(self, component: Component) -> void:
        """
        Recompute and apply the right occupation of an inserted component,
        e.g. after this edit (or the canvas) has been resized horizontally.
        """
        canvas = self._canvas_widget()
        if canvas is null:
            return
        # noinspection unresolved-references
        occupation = max(canvas.width() - self._content_left() - self._content_width(), 0.)
        if self._component_occupations.get(component, 0.) == occupation:
            return
        self._component_occupations[component] = occupation
        occupations = getattr(self.graphics, 'interface_occupations', null)
        if occupations is not null and component.interface in occupations:
            occupations[component.interface] = occupation
        self._apply_auto_width_inset(component)

    @final
    def _interface_size(self, component: Component) -> QSizeF:
        """
        Size occupied by the interface of a component.

        Requires the anchor to be pushed at the UI origin of the component when called.
        """
        layout = getattr(component.interface, 'layout', null)
        if layout is not null and hasattr(layout, 'size'):
            # noinspection broad-exception
            try:
                return QSizeF(layout.size(self.graphics))
            except Exception:
                pass
        return QSizeF(200., 60.)

    @final
    def _interface_widgets(self, component: Component) -> IList[QWidget]:
        """
        :return: the widgets contained in the interface of a component
        """
        widgets: IList[QWidget] = []
        layout = getattr(component.interface, 'layout', null)
        if layout is not null and hasattr(layout, 'elements'):
            for element in layout.elements:
                widget = getattr(element, 'widget', null)
                if isinstance(widget, QWidget):
                    widgets.append(widget)
        return widgets

    @final
    def _detach_component(self, object_name: string) -> void:
        """
        Detach the component whose placeholder has the specified object name from the canvas.

        Components nested inside the edits of the interface are registered flatly on the
        same graphics, so they are routed through their own edits' regular removal
        machinery recursively; otherwise their interfaces would keep being painted after
        the enclosing component is gone. Their placeholders stay in the nested documents
        (hidden), so undo cascades the reattachment through the usual repaint path of
        hidden placeholders.
        """
        component = self._spacer_components.get(object_name, null)
        if component is null:
            return
        # noinspection bad-argument-type
        for widget in self._interface_widgets(component):
            if isinstance(widget, VisualCodeEdit):
                for nested in list(widget.inserted_components):
                    spacer = widget._component_spacers.get(nested, null)
                    if spacer is not null:
                        widget.removeObject(spacer)
        components = getattr(self.graphics, 'components', null)
        # noinspection unresolved-references
        if components is not null and component.interface in components:
            # noinspection unresolved-references
            self.graphics.remove_interface(component.interface)
        if component in self.inserted_components:
            # noinspection bad-argument-type
            self.inserted_components.remove(component)
        # noinspection bad-argument-type
        for widget in self._interface_widgets(component):
            widget.hide()
        self.graphics.refresh()

    @final
    def _attach_component(self, object_name: string) -> void:
        """
        Reattach the component whose placeholder has the specified object name to the canvas.
        """
        component = self._spacer_components.get(object_name, null)
        if component is null:
            return
        components = getattr(self.graphics, 'components', null)
        # noinspection unresolved-references
        if components is not null and component.interface not in components:
            # noinspection unresolved-references,bad-argument-type
            self.graphics.add_interface(component.interface, self._component_occupations.get(component, 0.))
        if component not in self.inserted_components:
            # noinspection bad-argument-type
            self.inserted_components.append(component)
        # noinspection bad-argument-type
        for widget in self._interface_widgets(component):
            widget.show()
        self.graphics.refresh()

    def removeObject(self, widget: QWidget) -> void:
        component = self._spacer_components.get(widget.objectName(), null)
        if component is not null and self._selected_component is component:
            self._selected_component = null  # The placeholder is being removed; drop the state
            widget.setStyleSheet('')
        self._detach_component(widget.objectName())
        super().removeObject(widget)

    def _restoreObject(self, widget: QWidget) -> void:
        super()._restoreObject(widget)
        self._attach_component(widget.objectName())

    # ---------------------------------------------------------- Selection

    def selectedComponent(self) -> Nullable[Component]:
        """
        :return: the inserted component currently marked as selected, or null when
            there is none
        """
        return self._selected_component

    def select_component(self, component: Component) -> void:
        """
        Mark an inserted component as selected: its inline placeholder shows the
        theme's ``selected`` highlight. A second Backspace/Delete confirms the
        deletion of the component; clicking elsewhere clears the selection.
        :param component: the component to select
        """
        if self._selected_component is component:
            return
        self.clear_selection()
        if component not in self.inserted_components:
            return
        spacer = self._component_spacers.get(component, null)
        if spacer is null:
            return
        self._selected_component = component
        # The placeholder overlaps the component exactly; styling it draws the
        # highlight right over the component without touching the canvas figures
        spacer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        spacer.setStyleSheet(self._selection_style())

    def clear_selection(self) -> void:
        """
        Clear the component selection, removing the highlight from its placeholder.
        """
        if self._selected_component is null:
            return
        spacer = self._component_spacers.get(self._selected_component, null)
        if spacer is not null:
            spacer.setStyleSheet('')
        self._selected_component = null

    @final
    def _selection_style(self) -> string:
        """
        :return: the stylesheet applied to the placeholder of the selected component;
            a translucent tint plus a frame in the theme's ``selected`` color
        """
        # noinspection broad-exception
        try:
            color = Environment.instance().theme.colors.selected
        except Exception:
            color = QColor('#F2994A')
        tint = QColor(color)
        tint.setAlpha(40)
        return (f'background-color: {tint.name(QColor.NameFormat.HexArgb)};'
                f'border: 2px solid {color.name()};'
                f'border-radius: 4px;')

    @final
    def _adjacent_component(self, before: bool) -> Nullable[Component]:
        """
        :param before: when true, look behind the text cursor (the Backspace side);
            otherwise look ahead of it (the Delete side)
        :return: the component whose inline placeholder is directly adjacent to the
            text cursor, or null when there is none (or the cursor has a selection)
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            return null
        pos = cursor.position() - 1 if before else cursor.position()
        if pos < 0 or self.document().characterAt(pos) != '\uFFFC':
            return null
        for obj in self.displaying_objects.query_by_value(pos, pos):
            component = self._spacer_components.get(NotNull(obj.widget).objectName(), null)
            if component is not null:
                return component
        return null

    @final
    def _remove_component(self, component: Component) -> void:
        """
        Remove the inline placeholder of a component from the document, detaching the
        component from the canvas through the regular contents-change machinery.

        The removal is a plain document edit (one object-replacement character), so it
        participates in undo/redo: undoing restores the placeholder, and repainting
        reattaches the component (see ``_restoreObject``).
        """
        self.clear_selection()
        spacer = self._component_spacers.get(component, null)
        if spacer is null:
            return
        obj = self.objects.get(spacer.objectName(), null)
        if obj is null:
            return
        pos = int(obj.position)
        # The placeholder may already be gone (e.g. removed through a wider text
        # selection); never delete a character that is not the placeholder
        if self.document().characterAt(pos) != '\uFFFC':
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        # The focus may have been inside a field of the removed component; move it
        # here, right where the placeholder used to be
        self.setFocus()
        self.setTextCursor(cursor)

    # ---------------------------------------------------------- Editable navigation

    @final
    def _at_editable_edge(self, widget: QWidget, forward: bool) -> bool:
        """
        :param widget: an editable widget of an inserted component
        :param forward: when true, check the trailing edge (the Right key);
            otherwise check the leading edge (the Left key)
        :return: whether the caret of the widget sits at the specified edge; widgets
            without a caret (e.g. check boxes) count as being at both edges
        """
        if isinstance(widget, HyperTextEdit):
            cursor = widget.textCursor()
            if cursor.hasSelection():
                return False
            if forward:
                return cursor.position() == widget.document().characterCount() - 1
            return cursor.position() == 0
        if isinstance(widget, QLineEdit):
            if widget.hasSelectedText():
                return False
            if forward:
                return widget.cursorPosition() == len(widget.text())
            return widget.cursorPosition() == 0
        return True

    @final
    def _navigate_editable(self, component: Component, current: QWidget, forward: bool) -> bool:
        """
        Move the focus from an editable widget of a component to the adjacent one
        (``Component.editableWidgets``); when there is no widget on the specified
        side, the focus escapes right behind/in front of the placeholder of the
        component in this edit.
        :param component: the component owning the current widget
        :param current: the editable widget holding the focus
        :param forward: when true move rightwards, otherwise leftwards
        :return: whether the navigation consumed the key
        """
        widgets = component.editableWidgets()
        if current not in widgets:
            return False
        index = widgets.index(current)
        neighbor = index + 1 if forward else index - 1
        if 0 <= neighbor < len(widgets):
            self._focus_editable(widgets[neighbor], at_start=forward)
            return True
        self._focus_beside_component(component, after=forward)
        return True

    @final
    def _focus_editable(self, widget: QWidget, at_start: bool) -> void:
        """
        Focus an editable widget placing its caret at the beginning (when entering
        from the left) or at the end (when entering from the right).
        """
        widget.setFocus()
        if isinstance(widget, HyperTextEdit):
            cursor = widget.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start if at_start
                                else QTextCursor.MoveOperation.End)
            widget.setTextCursor(cursor)
        elif isinstance(widget, QLineEdit):
            widget.setCursorPosition(0 if at_start else len(widget.text()))

    @final
    def _focus_beside_component(self, component: Component, after: bool) -> void:
        """
        Move the focus and the text cursor of this edit right behind/in front of the
        inline placeholder of the specified component, so the navigation continues
        in the surrounding text.
        """
        spacer = self._component_spacers.get(component, null)
        if spacer is null:
            return
        obj = self.objects.get(spacer.objectName(), null)
        if obj is null:
            return
        cursor = self.textCursor()
        cursor.setPosition(int(obj.position) + (1 if after else 0))
        self.setFocus()
        self.setTextCursor(cursor)

    def eventFilter(self, watched: QObject, event: QEvent, /) -> bool:
        """
        Route the key interactions of the fields of the inserted components:

        - Backspace/Delete of a text field go through the two-step selection:
          Backspace at the very beginning of a field selects the component that owns
          the field instead of doing nothing; a further Backspace/Delete confirms the
          deletion.
        - Left/Right at the caret edge of an editable widget (or on a caret-less one,
          e.g. a check box) moves the focus along ``Component.editableWidgets``;
          leaving the list escapes before/behind the component in this edit.

        Any click or other key press clears an ongoing selection.
        """
        # noinspection bad-argument-type
        component = self._widget_components.get(watched, null)
        if component is not null and component in self.inserted_components:
            if event.type() == QEvent.Type.MouseButtonPress:
                self.clear_selection()
            elif event.type() == QEvent.Type.KeyPress:
                # noinspection unresolved-references
                key = event.key()
                if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) \
                        and event.modifiers() == Qt.KeyboardModifier.NoModifier \
                        and self._at_editable_edge(watched, key == Qt.Key.Key_Right):
                    self.clear_selection()
                    return self._navigate_editable(component, watched, key == Qt.Key.Key_Right)
                if isinstance(watched, HyperTextEdit):
                    cursor = watched.textCursor()
                    if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not cursor.hasSelection():
                        if self._selected_component is component:
                            self._remove_component(component)  # A second press confirms the deletion
                            return True
                        if key == Qt.Key.Key_Backspace and cursor.position() == 0:
                            self.select_component(component)
                            return True
                if self._selected_component is not null:
                    self.clear_selection()
        return super().eventFilter(watched, event)

    @final
    def _canvas_widget(self) -> Nullable[QWidget]:
        """
        :return: the canvas widget (the graphics interface when it is a widget,
                 otherwise the nearest ancestor implementing ``add_interface``)
        """
        graphics: Any = self.graphics
        if isinstance(graphics, QWidget):
            return graphics
        widget = self.parentWidget()
        while widget is not null:
            if hasattr(widget, 'add_interface'):
                return widget
            # noinspection unresolved-references
            widget = widget.parentWidget()
        return null

    # ---------------------------------------------------------- Auto width

    def setAutoWidthEnabled(self, enabled: bool) -> void:
        """
        Enable or disable adapting the width of this edit to its contents.

        When enabled, the width becomes the wider of the contents' ideal width
        (the width of one character when the document is empty) and the declared
        width, so that contents shorter than the declared row still fill it; the
        width follows every contents change afterwards, capped at the space available
        on the canvas (contents hitting the cap wrap instead of overflowing).
        Disabling restores the declared width.
        :param enabled: whether the width adapts to the contents
        :raise ValueError: raise when enabling while the declared width is negative
            (a negative declared width extends the edit to the right edge of the
            canvas, which conflicts with contents-driven widths)
        """
        if enabled == self._auto_width_enabled:
            return
        if enabled and self.declared_width < 0:
            raise ValueError('Auto width requires a non-negative declared width')
        self._auto_width_enabled = enabled
        if enabled:
            self._update_auto_width()
        elif self.declared_width > 0:
            self.setFixedWidth(ceil(self.declared_width))
            self.layoutSpaceChanged.emit()

    def autoWidthEnabled(self) -> bool:
        """
        :return: whether the width of this edit adapts to its contents
        """
        return self._auto_width_enabled

    @final
    def _auto_width(self) -> int:
        """
        :return: width this edit needs to show its contents without wrapping: the
            wider of the contents' ideal width and the declared width (empty contents
            reserve the width of one character), capped at the space available on the
            canvas so that overflowing contents wrap instead
        """
        doc = self.document()
        text_width = doc.textWidth()
        if text_width >= 0:  # Measure the unwrapped contents
            doc.setTextWidth(-1)
        ideal = doc.idealWidth()
        if text_width >= 0:
            doc.setTextWidth(text_width)
        if ideal <= 0:  # Empty contents: reserve the width of one character
            ideal = QFontMetricsF(doc.defaultFont()).averageCharWidth()
        margins = self.viewportMargins()
        width = max(ideal + 2 * doc.documentMargin() + margins.left() + margins.right(),
                    self.declared_width)
        available = self._available_width()
        if available > 0:  # Never overflow the canvas' right edge
            width = min(width, max(available, self.declared_width))
        return ceil(width)

    @final
    def _available_width(self) -> float:
        """
        :return: width available from the left edge of this edit to the right edge
            of the client area (the canvas' right edge minus the right inset); 0 when
            the canvas cannot be resolved
        """
        canvas = self._canvas_widget()
        if canvas is null:
            return 0.
        # noinspection bad-argument-type
        left = self.mapTo(canvas, QPoint(0, 0)).x()
        return float(max(canvas.width() - self._auto_width_right_inset - left, 0))

    @final
    def _apply_auto_width_inset(self, component: Component) -> void:
        """
        Bound the auto-width edits of a component at the right edge of its client area:
        the canvas' right edge narrowed by the component's right occupation and the
        layout margin, so the edits wrap inside the component instead of overflowing it.
        """
        layout = getattr(component.interface, 'layout', null)
        margin = getattr(layout, 'margin', 0.) if layout is not null else 0.
        inset = self._component_occupations.get(component, 0.) + margin
        for widget in self._interface_widgets(component):
            if isinstance(widget, VisualCodeEdit) and widget.autoWidthEnabled() \
                    and widget._auto_width_right_inset != inset:
                widget._auto_width_right_inset = inset
                widget._update_auto_width()

    @final
    def _update_auto_width(self) -> void:
        """
        Resize this edit to fit its contents; no-op when auto width is disabled
        or the fitting width is unchanged.
        """
        if not self._auto_width_enabled:
            return
        width = self._auto_width()
        if self.width() == width:
            return
        self.setFixedWidth(width)
        self.layoutSpaceChanged.emit()  # Let the enclosing layout follow the new width

    def _on_content_change(self, pos: int, removed_count: int, added_count: int) -> void:
        """
        Refit the width as well whenever the contents change. See the super method.
        """
        super()._on_content_change(pos, removed_count, added_count)
        self._update_auto_width()

    def changeEvent(self, event: QEvent, /) -> void:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._update_auto_width()

    def moveEvent(self, event: QMoveEvent, /) -> void:
        """
        Refit the width as well whenever the edit moves: the cap follows the edit's
        left edge (e.g. when an inline component is reflowed). See the super method.
        """
        super().moveEvent(event)
        self._update_auto_width()

    # ---------------------------------------------------------- Serialization

    def __serialize__(self) -> IDictionary[string, Any]:
        """
        Serialize this edit: the document text in which each inline component
        occupies one object-replacement character (``\\uFFFC``), together with
        the serialized components in the order their placeholders appear.
        :return: serialization of this edit
        """
        ordered = self.displaying_objects.query(minimum(HyperTextEdit._InlineObject),
                                                maximum(HyperTextEdit._InlineObject))
        components: IList[IDictionary[string, Any]] = []
        for inline in ordered:
            component = self._spacer_components.get(NotNull(inline.widget).objectName(), null)
            if component is not null:
                components.append({'name': Environment.instance().kit_manager.full_name(component),
                                   'data': serialize(component)})
        return {
            'text': self.toPlainText(),
            'components': components,
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], graphics: IComponentGraphics,
                parent: Nullable[QWidget] = null) -> 'VisualCodeEdit':
        """
        Restore a fresh edit from its serialization.
        Counterpart of ``__serialize__``; equivalent to constructing the edit
        and ``load``-ing the archive into it.
        :param data: serialization produced by ``__serialize__``
        :param graphics: graphics interface of the canvas the restored edit belongs to;
            it is supplied externally because widgets cannot be serialized
        :param parent: parent widget of the restored edit
        :return: the restored edit
        """
        edit = cls(parent, graphics)
        edit.load(data)
        return edit

    def load(self, data: IDictionary[string, Any]) -> void:
        """
        Load the contents of this edit from its serialization, reconstructing each
        inline component at its original placeholder position.
        :param data: serialization produced by ``__serialize__``
        :raise SerializationError: raise when required members are missing or the
            component count mismatches the placeholders in the text

        This edit must be empty: component interfaces hold references to their
        nested edits, which cannot be replaced after construction; therefore a
        restored archive is always loaded into a freshly constructed edit.
        """
        require_member(data, 'text', 'components')
        require_type(data['text'], string, 'text')
        require_type(data['components'], list, 'components')

        edit = self
        graphics = self.graphics
        kit_manager = Environment.instance().kit_manager
        text: string = data['text']
        segments = text.split('\uFFFC')
        if len(segments) - 1 != len(data['components']):
            raise SerializationError('Component count mismatches the placeholders in the text')

        # Rebuild the document in one pass: the treap positions are restored together
        # with the placeholders, so detach the contentsChange bookkeeping meanwhile
        # (its incremental position shifting would corrupt the freshly recorded positions)
        edit.document().contentsChange.disconnect(edit._on_content_change)
        try:
            cursor = edit.textCursor()
            for segment, serialized_component in zip(segments, data['components']):
                if segment:
                    cursor.insertText(segment)

                require_member(serialized_component, 'name', 'data')
                meta = kit_manager.lookup(serialized_component['name'])
                # Inline components are roots of their own tree; the UI context
                # mirrors insert_component (component_type(null, self.graphics))
                component = meta.component_type.restore(serialized_component['data'], null, graphics)

                canvas = edit._canvas_widget()
                occupation = 0.
                if canvas is not null:
                    occupation = max(canvas.width() - edit._content_left() - edit._content_width(), 0.)

                # Same anchor/occupation context as insert_component, so the placeholder
                # size matches what the component occupies on the canvas
                graphics.push_anchor(QPointF(edit._content_left(), 0.))
                graphics.push_right_occupation(occupation)
                try:
                    size = edit._interface_size(component)
                finally:
                    graphics.pop_occupation()
                    graphics.pop_anchor()

                spacer = QWidget()
                spacer.setObjectName(f'vce.inline.{id(component)}')
                spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                edit._spacer_components[spacer.objectName()] = component
                edit._component_spacers[component] = spacer
                edit._component_occupations[component] = occupation
                # _insert_inline_component reads the edit cursor to locate the placeholder
                edit.setTextCursor(cursor)
                edit._insert_inline_component(spacer, component, QSize(int(size.width()), int(size.height())))
                spacer.show()
                cursor = edit.textCursor()

                graphics.add_interface(component.interface, occupation)
                edit.inserted_components.append(component)
                edit._apply_auto_width_inset(component)

                # Refit the placeholder whenever the component (or its descendants) changes size;
                # watch the fields to route their Backspace/Delete through the selection
                for widget in edit._interface_widgets(component):
                    edit._widget_components[widget] = component
                    widget.installEventFilter(edit)
                    if isinstance(widget, HyperTextEdit):
                        widget.layoutSpaceChanged.connect(lambda c=component: edit._refit_component(c))

            if segments[-1]:
                cursor.insertText(segments[-1])
            edit.setTextCursor(cursor)

            edit.document().documentLayout().documentSize()  # Force layout before locating components
            edit.fitSize()

            # Locate each component at its placeholder
            position = 0
            for component in edit.inserted_components:
                position = text.index('\uFFFC', position)  # Placeholder positions in the original text
                sync_cursor = QTextCursor(edit.document())
                sync_cursor.setPosition(position)
                edit._sync_component_origin(component, QPointF(edit.cursorRect(sync_cursor).topLeft()))
                position += 1
        finally:
            edit.document().contentsChange.connect(edit._on_content_change)

        edit.viewport().update()
        edit._update_auto_width()  # No-op unless auto width is enabled
        graphics.refresh()

    # ---------------------------------------------------------- Completion

    @final
    def _current_word(self) -> string:
        """
        :return: the identifier ending at the text cursor; as identifiers cannot start
            with a digit, leading digits (e.g. the ``111`` of ``111m``) do not belong
            to the word
        """
        cursor = self.textCursor()
        text = cursor.block().text()[:cursor.positionInBlock()]
        i = len(text)
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == '_'):
            i -= 1
        word = text[i:]
        while word and word[0].isdigit():  # Identifiers cannot start with a digit
            word = word[1:]
        return word

    @final
    def _lookup_entry(self, keyword: string) -> Nullable[CompletionEntry]:
        """
        Lookup the completion entry whose keyword exactly matches (case-insensitively).
        """
        if not keyword:
            return null
        for entry in self.completions:
            if entry.keyword.lower() == keyword.lower():
                return entry
        return null

    @final
    def _update_completion(self) -> void:
        """
        Refresh the completion popup according to the word being typed.
        """
        if not self._completions_enabled:
            self._hide_popup()
            return
        self._sync_kit_completions()  # Kits imported after the edit construction still contribute
        prefix = self._current_word()
        if not prefix:
            self._hide_popup()
            return

        lowered = prefix.lower()
        matches = [entry for entry in self.completions
                   if entry.keyword.lower().startswith(lowered) and self._entry_participates(entry)]
        if not matches:
            self._hide_popup()
            return
        # Exact matches first, then shortest keywords
        matches.sort(key=lambda entry: (entry.keyword.lower() != lowered, len(entry.keyword)))
        self._show_popup(matches)

    @final
    def _show_popup(self, entries: IEnumerable[CompletionEntry]) -> void:
        if self._popup is null:
            self._popup = _CompletionPopup()
            # noinspection unresolved-references
            self._popup.list.itemClicked.connect(self._on_popup_click)
            # noinspection bad-argument-type
            self._style_popup(self._popup)

        # noinspection unresolved-references
        self._popup.set_entries(entries)

        rect = self.cursorRect()  # In viewport coordinates
        position = self.viewport().mapToGlobal(QPoint(rect.left(), rect.bottom() + 2))
        # noinspection unresolved-references
        self._popup.move(position)
        # noinspection unresolved-references
        self._popup.show()
        # noinspection unresolved-references
        self._popup.raise_()

    @final
    def _hide_popup(self) -> void:
        if self._popup is not null:
            # noinspection unresolved-references
            self._popup.hide()

    @final
    def _on_popup_click(self, item: QListWidgetItem) -> void:
        if self._popup is null:
            return
        # noinspection unresolved-references
        entry = self._popup.entry_at(self._popup.list.row(item))
        if entry is not null:
            # noinspection bad-argument-type
            self._confirm_completion(entry)

    @final
    def _confirm_completion(self, entry: CompletionEntry) -> void:
        """
        Confirm a completion: remove the typed prefix and insert the bound component.
        """
        self._hide_popup()

        prefix = self._current_word()
        if prefix:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter,
                                QTextCursor.MoveMode.KeepAnchor, len(prefix))
            cursor.removeSelectedText()
            self.setTextCursor(cursor)

        self.insert_component(entry)

    @final
    def _style_popup(self, popup: _CompletionPopup) -> void:
        # noinspection broad-exception
        try:
            colors = Environment.instance().theme.colors
        except Exception:
            return
        popup.setStyleSheet(f"""
            _CompletionPopup {{
                background-color: {colors.secondary.name()};
                border: 1px solid {colors.tertiary.name()};
                border-radius: 4px;
            }}
            _CompletionPopup QListWidget {{
                background: transparent;
                border: none;
                outline: none;
                color: {colors.foreground.name()};
            }}
            _CompletionPopup QListWidget::item {{
                padding: 3px 8px;
                border-radius: 3px;
            }}
            _CompletionPopup QListWidget::item:selected {{
                background-color: {colors.tertiary.name()};
                color: {colors.foreground.name()};
            }}
            _CompletionPopup QLabel {{
                background: transparent;
                border: none;
                border-left: 1px solid {colors.tertiary.name()};
                color: {colors.foreground.name()};
                padding: 3px 8px;
            }}
        """)

    # ---------------------------------------------------------- Events

    def keyPressEvent(self, event: QKeyEvent, /) -> void:
        # noinspection unresolved-references
        if self._popup is not null and self._popup.isVisible():
            key = event.key()
            if key == Qt.Key.Key_Down:
                # noinspection unresolved-references
                self._popup.move_selection(1)
                return
            if key == Qt.Key.Key_Up:
                # noinspection unresolved-references
                self._popup.move_selection(-1)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                # noinspection unresolved-references
                entry = self._popup.current_entry()
                if entry is not null:
                    # noinspection bad-argument-type
                    self._confirm_completion(entry)
                    return
            if key == Qt.Key.Key_Escape:
                self._hide_popup()
                return
        else:
            key = event.key()
            if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                # A second Backspace/Delete confirms the deletion of the selected
                # component; otherwise a Backspace/Delete adjacent to the placeholder
                # of a component that owns fields selects the component first
                if self._selected_component is not null:
                    self._remove_component(self._selected_component)
                    return
                component = self._adjacent_component(key == Qt.Key.Key_Backspace)
                if component is not null and component.autoFocusWidget() is not null:
                    self.select_component(component)
                    return
            elif self._selected_component is not null:
                self.clear_selection()

            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._completions_enabled:
                # Popup hidden (e.g. dismissed by Escape): still confirm an exactly typed keyword
                entry = self._lookup_entry(self._current_word())
                if entry is not null:
                    # noinspection bad-argument-type
                    self._confirm_completion(entry)
                    return

        super().keyPressEvent(event)
        self._update_completion()

    def focusOutEvent(self, event: QFocusEvent, /) -> void:
        self._hide_popup()
        self.clear_selection()
        super().focusOutEvent(event)

    def mousePressEvent(self, event: QMouseEvent, /) -> void:
        self._hide_popup()
        self.clear_selection()
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent, /) -> void:
        self._hide_popup()
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            # Keep the document layout width in sync with the new viewport width
            self.fitSize()
            # The applied width may have come from the canvas replaying the declared
            # geometry; the contents may need another fitting pass against the new cap
            self._update_auto_width()
            # The canvas size may still be stale while its resizeEvent relocates this
            # edit; defer the components refitting until the geometries have settled
            QTimer.singleShot(0, self._refit_after_resize)
