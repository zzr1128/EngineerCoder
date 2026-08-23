# -*- coding: utf-8 -*-
"""
The component palette of the left dock.

Lists the insertable components grouped by kit: one draggable entry per
component the code completion can insert (the built-in constructs plus the
keyword-registered components of the imported kits). A kit that organizes its
components into palette groups (see ``Kit.palette_groups``) shows one
collapsible section per group underneath its name; clicking a section header
collapses or expands the entries underneath it. Dragging an entry into a
visual code edit inserts the component at the drop position: the drag carries
the complete name of the component in ``VisualCodeEdit.ComponentMime`` and the
edit's drop handler performs the insertion (subject to its filter criteria).
"""

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from alias import *
from core.kit import KitManager
from interface.visual_code_edit import VisualCodeEdit


class _PaletteEntry(QLabel):
    """A draggable entry of the palette: the drag carries the complete name of
    the component the entry stands for (see ``VisualCodeEdit.ComponentMime``)."""

    def __init__(self, display_name: string, description: string,
                 component_name: string, keyword: string):
        super().__init__(display_name)
        self.component_name: Final[string] = component_name
        self.keyword: Final[string] = keyword
        self.setToolTip(f'{description}\n({keyword})' if description else keyword)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press_position: Nullable[QPoint] = null
        # Whether the entry matches the current filter text; the entry stays
        # visible only when it matches and its section is expanded
        self._match: bool = True

    def mousePressEvent(self, event: QMouseEvent, /) -> void:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent, /) -> void:
        if self._press_position is null \
                or not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._press_position).manhattanLength() \
                < QApplication.startDragDistance():
            return
        self._press_position = null
        mime = QMimeData()
        mime.setData(VisualCodeEdit.ComponentMime, self.component_name.encode('utf-8'))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())  # The entry itself is the drag feedback
        drag.setHotSpot(QPoint(self.width() // 2, self.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)


class _PaletteHeader(QLabel):
    """A collapsible section header: clicking it toggles the visibility of the
    entries of its section (the filter result still applies underneath)."""

    def __init__(self, title: string, object_name: string = 'paletteHeader'):
        super().__init__()
        self.title: Final[string] = title
        self.expanded: bool = True  # Every section starts expanded
        self.entries: IList[_PaletteEntry] = []
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_text()

    @final
    def _update_text(self) -> void:
        # The marker shows the current state: down arrow when expanded
        self.setText(('\u25be ' if self.expanded else '\u25b8 ') + self.title)

    @final
    def toggle(self) -> void:
        self.expanded = not self.expanded
        self._update_text()
        for entry in self.entries:
            entry.setVisible(entry._match and self.expanded)

    def mousePressEvent(self, event: QMouseEvent, /) -> void:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
        super().mousePressEvent(event)


class ComponentPalette(QWidget):
    """
    The grouped list of the insertable components: one section per imported kit
    (its display name heads the section), or one collapsible section per palette
    group when the kit organizes its components (see ``Kit.palette_groups``);
    one draggable entry per component the code completion can insert. The
    filter box of the dock narrows the listing (see ``apply_filter``).
    """

    def __init__(self, parent: Nullable[QWidget] = null):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self._layout: Final[QVBoxLayout] = layout
        # Collapsible section header -> the entries underneath it (the filter
        # hides both; collapsing the header hides the entries alone)
        self._sections: IList[tuple[_PaletteHeader, IList[_PaletteEntry]]] = []
        self._rebuild()

    @final
    def _rebuild(self) -> void:
        """Enumerate the insertable components of the imported kits: a component
        takes part when the code completion can insert it — the built-in
        constructs or a keyword the kit registered for it. Internal components
        (roots, helpers) carry no keyword and stay out of the palette."""
        keywords: IDictionary[string, string] = {}
        for entry in VisualCodeEdit.DefaultCompletions:
            if entry.component_name:
                keywords[entry.component_name] = entry.keyword
        manager = KitManager.instance()
        for keyword, component_name in manager.completions.items():
            keywords[component_name] = keyword
        # Context-gated components complete inside matching contexts only, but
        # the palette lists them as draggable entries nonetheless
        for component_name, keyword in manager.context_completions.items():
            keywords.setdefault(component_name, keyword)

        for kit in manager:
            grouped: IDictionary[string, IList[_PaletteEntry]] = {}
            for meta in sorted(kit, key=lambda member: member.display_name):
                name = KitManager.merge_names(kit.meta.name, meta.name)
                keyword = keywords.get(name, null)
                if keyword is null:
                    continue
                grouped.setdefault(meta.group, []).append(
                    _PaletteEntry(meta.display_name, meta.description, name, keyword))
            if not grouped:
                continue
            if not kit.palette_groups or list(grouped) == ['']:
                # Flat kit: the kit name heads a single collapsible section
                self._add_section(kit.meta.display_name, grouped[''])
                continue
            kit_header = QLabel(kit.meta.display_name)
            kit_header.setObjectName('paletteHeader')
            self._layout.addWidget(kit_header)
            # One collapsible section per palette group, in the kit's order
            for group in kit.palette_groups:
                entries = grouped.pop(group, [])
                if entries:
                    self._add_section(group, entries, 'paletteGroupHeader')
            for group, entries in grouped.items():  # Groups the kit did not announce
                self._add_section(group or kit.meta.display_name, entries, 'paletteGroupHeader')
        self._layout.addStretch(1)

    @final
    def _add_section(self, title: string, entries: IList[_PaletteEntry],
                     object_name: string = 'paletteHeader') -> void:
        header = _PaletteHeader(title, object_name)
        header.entries = entries
        self._layout.addWidget(header)
        for entry in entries:
            self._layout.addWidget(entry)
        self._sections.append((header, entries))

    def apply_filter(self, pattern: string) -> void:
        """
        Narrow the listing to the entries whose display name, keyword or
        complete name contains the pattern (case-insensitively); an empty
        pattern restores the complete listing. Sections without visible
        entries hide with them; collapsing a section still applies.
        :param pattern: the text of the dock's filter box
        """
        lowered = pattern.strip().lower()
        for header, entries in self._sections:
            visible = 0
            for entry in entries:
                entry._match = not lowered \
                    or lowered in entry.text().lower() \
                    or lowered in entry.keyword.lower() \
                    or lowered in entry.component_name.lower()
                visible += entry._match
                entry.setVisible(entry._match and header.expanded)
            header.setVisible(visible > 0)
