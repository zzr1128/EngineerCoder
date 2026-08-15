# -*- coding: utf-8 -*-

from dataclasses import dataclass

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, QTimer, Signal
from PySide6.QtGui import (QFocusEvent, QKeyEvent, QMouseEvent, QPainter, QResizeEvent,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)
from PySide6.QtWidgets import QFrame, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from alias import *
from alias import Nullable
from core.component import Component
from core.environment import Environment
from core.graphics import IComponentGraphics
from core.hyper_text_edit import HyperTextEdit, HyperTextObject


class _CompletionPopup(QFrame):
    """
    Top-level list popup of code completions.

    The popup never takes the input focus (``WA_ShowWithoutActivating``),
    so the editor keeps receiving key events while the popup is visible.
    """
    PopupWidth: Final[int] = 280
    MaxHeight: Final[int] = 240

    def __init__(self):
        super().__init__(null, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.entries: IList['VisualCodeEdit.CompletionEntry'] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        self.list = QListWidget(self)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.list)

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
        self.setFixedSize(_CompletionPopup.PopupWidth, height)

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

    The editor itself has a translucent background (styled by the application's theme
    stylesheet) so that the figures painted on the canvas show through.
    """

    @dataclass
    class CompletionEntry:
        keyword: string           # Keyword typed by the user (e.g. 'if')
        component_name: string    # Complete name of the component (e.g. 'clk.br')

    DefaultCompletions: ClassVar[IList[CompletionEntry]] = [
        CompletionEntry('if', 'clk.br'),
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
        self.completions: IList[VisualCodeEdit.CompletionEntry] = list(VisualCodeEdit.DefaultCompletions)
        self.inserted_components: IList[Component] = []
        self._spacer_components: IDictionary[string, Component] = {}  # Placeholder name -> component
        self._component_spacers: IDictionary[Component, QWidget] = {}  # Component -> placeholder
        self._component_occupations: IDictionary[Component, float] = {}  # Component -> right occupation

        self._popup: Nullable[_CompletionPopup] = null

        # The edit grows to fit its contents without any height limit; the whole canvas
        # scrolls when the contents outgrow the visible area. Scrollbars stay off: text
        # wraps at the column width, keeping the inserted components aligned with it
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # No frame; the background comes from the application stylesheet (translucent,
        # so that components painted on the canvas underneath remain visible)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def add_completion(self, keyword: string, component_name: string) -> void:
        """
        Append a completion entry (keyword mapped to a component).
        :param keyword: keyword that triggers the completion
        :param component_name: complete name of the component to insert
        """
        self.completions.append(VisualCodeEdit.CompletionEntry(keyword, component_name))

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
        self._insert_inline_component(spacer, component, QSize(int(size.width()), int(size.height())))
        spacer.show()  # Avoid taking the undo/redo restore path on the first draw

        self.graphics.add_interface(component.interface, occupation)
        self.inserted_components.append(component)

        # Refit the placeholder whenever the component (or its descendants) changes size
        for widget in self._interface_widgets(component):
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
        obj = HyperTextEdit._InlineObject(interface, spacer, pos)
        self.objects[spacer.objectName()] = obj
        self.displaying_objects.insert(obj)
        cursor.insertText('\uFFFC', fmt)
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
        # The client area spans the text column width, whatever the placeholder x is
        origin = QPointF(self._content_left(), top_left.y())
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
        """
        component = self._spacer_components.get(object_name, null)
        if component is null:
            return
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
        self._detach_component(widget.objectName())
        super().removeObject(widget)

    def _restoreObject(self, widget: QWidget) -> void:
        super()._restoreObject(widget)
        self._attach_component(widget.objectName())

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

    # ---------------------------------------------------------- Completion

    @final
    def _current_word(self) -> string:
        """
        :return: the word (letters, digits and underscores) ending at the text cursor
        """
        cursor = self.textCursor()
        text = cursor.block().text()[:cursor.positionInBlock()]
        i = len(text)
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == '_'):
            i -= 1
        return text[i:]

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
        prefix = self._current_word()
        if not prefix:
            self._hide_popup()
            return

        lowered = prefix.lower()
        matches = [entry for entry in self.completions if entry.keyword.lower().startswith(lowered)]
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
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
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
        super().focusOutEvent(event)

    def mousePressEvent(self, event: QMouseEvent, /) -> void:
        self._hide_popup()
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent, /) -> void:
        self._hide_popup()
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            # Keep the document layout width in sync with the new viewport width
            self.fitSize()
            # The canvas size may still be stale while its resizeEvent relocates this
            # edit; defer the components refitting until the geometries have settled
            QTimer.singleShot(0, self._refit_after_resize)
