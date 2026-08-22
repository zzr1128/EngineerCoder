# -*- coding: utf-8 -*-

from math import ceil

from PySide6.QtCore import QEvent, QRect, QRectF, QSizeF, Signal
from PySide6.QtGui import (QPyTextObject, QTextFormat, QTextDocument, QPainter,
                           QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import QWidget, QTextEdit

from alias import *
from graphics import TextMeasure
from treap import NonRotationalTreap


class HyperTextEdit(QTextEdit):
    inlineObjectRestored: ClassVar[Signal] = Signal(QWidget)

    # Signal emitted when space the edit occupies in layout changes.
    # When emitted, the size of the widget is already changed. Use size(), width() or height() to acquire the new size.
    layoutSpaceChanged: Signal = Signal()

    class _InlineObject:
        """
        A structure to maintain inline widget, contained object and position in document.
        """

        # noinspection GrazieInspection
        @overload
        def __init__(self, obj: Nullable['HyperTextObject'], widget: Nullable[QWidget],
                     posInDocument: Literal['maximum', 'minimum']):
            """
            Create an inline-object that contains an infinite value as a placeholder for non-existing elements.
            :param obj: null
            :param widget: null
            :param posInDocument: literal 'maximum' or 'minimum'
            """
            ...

        @overload
        def __init__(self, obj: 'HyperTextObject', widget: QWidget, posInDocument: int):
            """
            Create an inline-object that records object, widget and the position in the document.
            :param obj: hyper-text inline object
            :param widget: widget to show
            :param posInDocument: position in the document
            """
            ...

        def __init__(self, obj: Nullable['HyperTextObject'], widget: Nullable[QWidget],
                     posInDocument: int | Literal['maximum', 'minimum']):
            self.object: Nullable['HyperTextObject'] = obj
            self.widget: Nullable[QWidget] = widget
            if posInDocument == 'maximum':
                self.position = float('inf')
            elif posInDocument == 'minimum':
                self.position = -float('inf')
            else:
                self.position = posInDocument

        @property
        def name(self):
            """
            :return: the object name of the displaying widget
            """
            return self.widget.objectName()

        # noinspection method-overriding
        def __eq__(self, other: Self | int) -> bool:
            if isinstance(other, HyperTextEdit._InlineObject):
                other = other.position
            return self.position == other

        def __gt__(self, other: Self | int) -> bool:
            if isinstance(other, HyperTextEdit._InlineObject):
                other = other.position
            return self.position > other

        def __add__(self, other: int) -> 'HyperTextEdit._InlineObject':
            return HyperTextEdit._InlineObject(self.object, self.widget, self.position + other)  # type: ignore

        def __sub__(self, other: int) -> 'HyperTextEdit._InlineObject':
            return HyperTextEdit._InlineObject(self.object, self.widget, self.position - other)  # type: ignore

        def __iadd__(self, other: int) -> Self:
            self.position += other
            return self

        def __isub__(self, other: int) -> Self:
            self.position -= other
            return self

        def __value__(self) -> float | int:
            """
            Return the position as the value in treap.
            :return: position in the document
            """
            return self.position

        @classmethod
        def __minimum__(cls) -> 'HyperTextEdit._InlineObject':
            return HyperTextEdit._InlineObject(null, null, 'minimum')

        @classmethod
        def __maximum__(cls) -> 'HyperTextEdit._InlineObject':
            return HyperTextEdit._InlineObject(null, null, 'maximum')

        def __has_value__(self) -> bool:
            return isinstance(self.position, int)

    def __init__(self, parent: Nullable[QWidget]):
        super().__init__(parent)
        self.document().contentsChange.connect(self._on_content_change)
        self.inlineObjectRestored.connect(self._restoreObject)
        self.document().setDefaultFont(self.font())
        self.basic_height = self._heightToFit()

        self.mdf_stack: list[int | tuple[QWidget, ...]] = []  # Stack of modifications
        self.objects: IDictionary[string, HyperTextEdit._InlineObject] = {}
        self.displaying_objects: NonRotationalTreap[HyperTextEdit._InlineObject, int] \
            = NonRotationalTreap.create_integral(HyperTextEdit._InlineObject)  # type: ignore
        self.max_height = self.maximumHeight()
        self._basic_frame_width = self.frameWidth()  # Frame the basic height was measured with

    def insertObject(self, widget: QWidget) -> void:
        """
        Generate an inline text object for the specified widget and insert it
        into the hypertext document.
        :param widget: the widget to insert
        """
        widget.setParent(self.viewport())

        interface = HyperTextObject(self, widget)
        doc_layout = self.document().documentLayout()
        doc_layout.registerHandler(interface.format_id, interface)

        fmt = QTextCharFormat()
        fmt.setObjectType(interface.format_id)
        fmt.setProperty(interface.property_id, widget)

        cursor = self.textCursor()
        pos = cursor.position()
        # Insert the placeholder first: the emitted contentsChange shifts the recorded
        # positions of the objects at or after the insertion point; the new object is
        # recorded afterwards so that it is not shifted itself
        cursor.insertText('\uFFFC', fmt)
        obj = HyperTextEdit._InlineObject(interface, widget, pos)
        self.objects[widget.objectName()] = obj
        self.displaying_objects.insert(obj)
        self.setTextCursor(cursor)
        self.viewport().update()

    def removeObject(self, widget: QWidget) -> void:
        """
        Remove the specified inline widget from the hypertext document.
        :param widget: the widget to remove

        This method only removes the widget from the editor, does not delete the widget.

        **Attention**: This method only detaches the inline rendering of the widget
        and does not delete the document placeholder.
        """
        name: string = widget.objectName()
        if name not in self.objects:
            raise KeyError(f'Widget not found: {name}')
        obj: HyperTextEdit._InlineObject = self.objects[name]
        self.displaying_objects.remove(obj)
        widget.hide()
        self.viewport().update()

    def _restoreObject(self, widget: QWidget) -> void:
        """
        Restore the specified inline widget in the hypertext document, especially when redo
        :param widget: the widget to recover

        This method requires the widget was inserted in the edit and has its inline object in widget treap cache.
        """
        name: string = widget.objectName()
        if name not in self.objects:
            raise KeyError(f'Widget not found: {name}')
        obj: HyperTextEdit._InlineObject = self.objects[name]
        self.displaying_objects.insert(obj)
        widget.show()
        self.viewport().update()

    def _heightToFit(self) -> int:
        """
        Calculate the minimum height of this editor that can display all
        the content without vertical scrolling.
        :return: the minimum height in pixels
        """
        doc = self.document()
        if self.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth:
            doc.setTextWidth(self.viewport().width())
        else:
            doc.setTextWidth(-1)

        content_height = ceil(doc.documentLayout().documentSize().height())
        vm = self.viewportMargins()
        # The frame (e.g. the 1px border a validation marking styles in) surrounds
        # the viewport; counting it keeps the contents visible when the border
        # appears or disappears
        return content_height + vm.top() + vm.bottom() + 2 * self.frameWidth()

    def _on_content_change(self, pos: int, removed_count: int, added_count: int) -> void:
        if removed_count > 0:  # Remove text
            to_remove = self.displaying_objects.query_by_value(pos, pos + removed_count - 1)
            cnt = 0
            for obj in to_remove:
                NotNull(obj.widget)
                self.removeObject(obj.widget)
                cnt += 1

        if added_count != removed_count:
            self._shift_suffix(pos + removed_count, added_count - removed_count)

        self.fitSize()

    @final
    def _shift_suffix(self, threshold: int, delta: int) -> void:
        """
        Shift the recorded positions of all inline objects located at or after the
        threshold by the specified delta, keeping them synchronized with the document
        after an insertion (positive delta) or removal (negative delta).
        :param threshold: smallest position affected by the shift (document coordinates
            before the change takes effect on the recorded positions)
        :param delta: the shift amount

        ``add_suffix`` compares plain values, so the split key needs not exist in
        the treap: a detached pivot marks the boundary without being inserted.
        (Inserting it could collide with a real object at the same position, and
        removing it would then non-deterministically evict the wrong twin, leaking
        the pivot into queries.)
        """
        pivot = HyperTextEdit._InlineObject(null, null, threshold - 1)
        self.displaying_objects.add_suffix(pivot, delta)

    def setMaximumHeight(self, maxh: int, /) -> void:
        super().setMaximumHeight(maxh)
        self.max_height = self.maximumHeight()

    def setBasicHeight(self, height: int) -> void:
        """
        Set the basic height: the floor ``fitSize`` never shrinks below,
        regardless of the contents.
        :param height: the new basic height in pixels

        Editors that must fill a given area (e.g. the client rectangle of the
        canvas) keep the area height as their basic height, so empty contents
        still fill it while growing contents still extend it.
        """
        if height == self.basic_height:
            return
        self.basic_height = height
        self._basic_frame_width = self.frameWidth()
        self.fitSize()

    def changeEvent(self, event: QEvent, /) -> void:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.document().setDefaultFont(self.font())
            self.basic_height = self._heightToFit()
            self._basic_frame_width = self.frameWidth()
            self.fitSize()
        elif event.type() == QEvent.Type.StyleChange:
            # A stylesheet state change (e.g. a validation marking styling a
            # border in or out) changes the frame around the viewport: shift
            # the basic floor by the frame delta and refit, so the contents
            # stay visible without drifting
            frame_width = self.frameWidth()
            if frame_width != self._basic_frame_width:
                self.basic_height += 2 * (frame_width - self._basic_frame_width)
                self._basic_frame_width = frame_width
            self.fitSize()

    def fitSize(self) -> void:
        if self.viewport().width() <= 0:
            # Degenerate geometry (e.g. the window is minimized): the document
            # layout cannot be measured, and locking the size now would freeze
            # the edit at a wrong height the restore cannot undo
            return
        h = max(self.basic_height, min(self.max_height, self._heightToFit()))
        if self.height() != h:
            self.setFixedHeight(h)
            self.layoutSpaceChanged.emit()


class HyperTextObject(QPyTextObject):
    _ObjectId: ClassVar[int] = 1
    _ObjectIdFreeList: ClassVar[IList[int]] = []
    property_id = QTextFormat.Property.UserProperty + 1

    def __init__(self, editor: HyperTextEdit, widget: QWidget):
        super().__init__(editor.viewport())
        self.editor: HyperTextEdit = editor
        self.widget: QWidget = widget
        self.id = HyperTextObject.acquireObjectId()
        self.format_id = QTextFormat.ObjectTypes.UserObject + self.id

    def intrinsicSize(self, doc: QTextDocument, posInDocument: int, fmt: QTextFormat, /) -> QSizeF:
        return QSizeF(self.widget.sizeHint())

    def drawObject(self, painter: QPainter, rect: QRect | QRectF, doc: QTextDocument,
                   posInDocument: int, fmt: QTextFormat, /) -> void:
        cursor = QTextCursor(doc)
        cursor.setPosition(posInDocument)
        fmt = cursor.charFormat()
        font = fmt.font()
        metrics = TextMeasure(font, '')
        x = int(rect.x() - self.editor.horizontalScrollBar().value())
        y = int(rect.y() - self.editor.verticalScrollBar().value() + (self.widget.height() - metrics.ascent) // 2)
        self.widget.move(x, y)

        if self.widget.isHidden():  # When widget is restored via undo/redo, the widget is updated
            self.widget.show()
            self.editor.inlineObjectRestored.emit(self.widget)  # Notify the editor to update the treap cache

    @classmethod
    def acquireObjectId(cls) -> int:
        """
        Acquire and occupy an available object id to register as character format handler.
        :return: an object id
        """
        if cls._ObjectIdFreeList:
            return cls._ObjectIdFreeList.pop()
        r = cls._ObjectId
        cls._ObjectId += 1
        return r

    @classmethod
    def releaseObjectId(cls, id_: int) -> void:
        """
        Give back an object id for reusing.
        :param id_: an object id
        """
        cls._ObjectIdFreeList.append(id_)
