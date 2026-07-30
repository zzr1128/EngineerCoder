# -*- coding: utf-8 -*-

from PySide6.QtCore import QRect, QSize, Signal
from PySide6.QtGui import (QPyTextObject, QTextFormat, QTextDocument, QPainter,
                           QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import QWidget, QTextEdit

from alias import *
from graphics import TextMeasure
from treap import NonRotationalTreap


class HyperTextEdit(QTextEdit):
    inlineObjectRestored: ClassVar[Signal] = Signal(QWidget)

    class _InlineObject:
        """
        A structure to maintain inline widget, contained object and position in document.
        """

        # noinspection GrazieInspection
        @overload
        def __init__(self, obj: null, widget: null, posInDocument: Literal['maximum', 'minimum']):
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
            self.object: 'HyperTextObject' = obj
            self.widget: QWidget = widget
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

        def __eq__(self, other: Self | int) -> bool:
            if isinstance(other, HyperTextEdit._InlineObject):
                other = other.position
            return self.position == other

        def __gt__(self, other: Self | int) -> bool:
            if isinstance(other, HyperTextEdit._InlineObject):
                other = other.position
            return self.position > other

        def __add__(self, other: int) -> 'HyperTextEdit._InlineObject':
            return HyperTextEdit._InlineObject(self.object, self.widget, self.position + other)

        def __sub__(self, other: int) -> 'HyperTextEdit._InlineObject':
            return HyperTextEdit._InlineObject(self.object, self.widget, self.position - other)

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

        self.mdf_stack: list[int | tuple[QWidget, ...]] = []  # Stack of modifications
        self.objects: IDictionary[string, HyperTextEdit._InlineObject] = {}
        self.displaying_objects: NonRotationalTreap[HyperTextEdit._InlineObject, int] \
            = NonRotationalTreap.create_integral(HyperTextEdit._InlineObject)  # type: ignore

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
        obj = HyperTextEdit._InlineObject(interface, widget, pos)
        self.objects[widget.objectName()] = obj
        self.displaying_objects.insert(obj)
        cursor.insertText('\uFFFC', fmt)
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

    def _on_content_change(self, pos: int, removed_count: int, added_count: int) -> void:
        if removed_count > 0:  # Remove text
            to_remove = self.displaying_objects.query_by_value(pos, pos + removed_count - 1)
            cnt = 0
            for obj in to_remove:
                self.removeObject(obj.widget)
                cnt += 1

        if added_count != removed_count:
            self.displaying_objects.add_suffix_by_value(pos + added_count - removed_count, added_count - removed_count)


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

    def intrinsicSize(self, doc: QTextDocument, posInDocument: int, fmt: QTextFormat, /) -> QSize:
        return self.widget.sizeHint()

    def drawObject(self, painter: QPainter, rect: QRect, doc: QTextDocument,
                   posInDocument: int, fmt: QTextFormat, /) -> void:
        cursor = QTextCursor(doc)
        cursor.setPosition(posInDocument)
        fmt = cursor.charFormat()
        font = fmt.font()
        metrics = TextMeasure(font, '')
        x: int = rect.x() - self.editor.horizontalScrollBar().value()
        y: int = rect.y() - self.editor.verticalScrollBar().value() + (self.widget.height() - metrics.ascent) // 2
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
