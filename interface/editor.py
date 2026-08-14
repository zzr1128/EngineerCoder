# -*- coding: utf-8 -*-

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from alias import *
from alias import Nullable
from core.localization import _
from core.script import Script
from core.environment import Environment
from interface.ui_style_editor import Ui_EditorWindow
from interface.edition_canvas import EditionCanvas


@final
class EditorWindow(QMainWindow, Ui_EditorWindow):
    _instance: Nullable['EditorWindow'] = null

    def __new__(cls, parent: Nullable[QWidget] = null) -> Self:
        if cls._instance is null:
            cls._instance = super(EditorWindow, cls).__new__(cls)
            return cls._instance  # type: ignore
        raise TypeError('Singleton type EditorWindow is being instantiated the second time')

    @final
    class TabHandler:
        FreeHandler = 1
        __slots__ = ('value', 'title')

        def __init__(self, value: int, title: string):
            self.value = value
            self.title = title

        def __hash__(self) -> int:
            return hash(self.value)

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, EditorWindow.TabHandler):
                raise TypeError('Cannot compare EditorWindow.TabHandler with other types')
            return self.value == other.value

        @classmethod
        def allocate(cls, title: string) -> 'EditorWindow.TabHandler':
            return EditorWindow.TabHandler(cls.FreeHandler, title)

        @property
        def valid(self) -> bool:
            return (self in EditorWindow._instance.tabs) if EditorWindow._instance is not null else False

    def __init__(self, parent: Nullable[QWidget] = null):
        super(EditorWindow, self).__init__(parent)
        self.setupUi(self)
        self.tabs: IDictionary[EditorWindow.TabHandler, EditionCanvas] = {}
        self.tabWidget_editor.setEditor(self)
        self.env = Environment()

        self.compArea_layout = QVBoxLayout(self.scrollAreaCompContents)

        self.setup()

        # Test code
        self.env.import_kit(r'kits/common')
        tab = self.create_canvas('TestTab')
        self.tabWidget_editor.setCurrentWidget(canvas := self.canvas(tab))
        # canvas.create_lineedit(QRectF(0, 0, 100, 20))
        comp_meta = self.env.kit_manager.lookup('clk.br')
        comp = comp_meta.component_type(null, canvas)
        canvas.add_interface(comp.interface)
        self.script = Script(comp)
        # comp.interface.paint(canvas)

    def canvas(self, handler: 'EditorWindow.TabHandler') -> EditionCanvas:
        return self.tabs[handler]

    def register_canvas(self, handler: TabHandler, canvas: EditionCanvas) -> void:
        if handler in self.tabs:
            raise KeyError('Canvas already registered')
        self.tabs[handler] = canvas

    def unregister_canvas(self, canvas: EditionCanvas) -> void:
        # pyrefly: ignore [bad-assignment]
        key = null
        for k, v in self.tabs.items():
            if v == canvas:
                key = k
                break
        if key is null:
            raise KeyError('No such canvas to unregister')
        key: EditorWindow.TabHandler  # not null
        self.tabs.pop(key)

    def set_style(self):
        tp = QColor.fromRgb(self.env.theme.colors.tertiary.rgb() // 2 + self.env.theme.colors.primary.rgb() // 2)  # Mean of tertiary and primary
        self.dockWidgetContents_comp.setBackgroundColor(self.env.theme.colors.side)
        self.dockWidgetContents_details.setBackgroundColor(self.env.theme.colors.side)
        self.setStyleSheet(f"""
            /* Main Window */
            QMainWindow {{ 
                background-color: {self.env.theme.colors.background.name()}; 
                color: {self.env.theme.colors.foreground.name()};
            }}
            QWidget#{self.centralwidget.objectName()} {{ background: transparent; }}
            
            /* Tab widget */
            QTabBar::tab {{
                padding: 6px 14px;
                min-height: 10px;
                background: {self.env.theme.colors.secondary.name()};
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            QTabBar::tab:selected {{
                background-color: {self.env.theme.colors.tertiary.name()};
                border-radius: 6px;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {tp.name()};
                border-radius: 6px;
            }}
            QTabWidget::pane {{
                background-color: {self.env.theme.colors.secondary.name()};
                border-radius: 6px;
            }}
            QTabWidget, QTabBar {{
                background: transparent;
                spacing: 3px;
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            
            /* Side dock widget */
            QDockWidget::title {{
                background-color: {self.env.theme.colors.tertiary.name()};
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            QScrollArea, QWidget#{self.scrollAreaCompContents.objectName()} {{
                background-color: {self.env.theme.colors.secondary.name()};
                border-radius: 6px;
            }}
            
            /* Field controls */
            QMainWindow QLineEdit, QMainWindow QTextEdit, QMainWindow HyperTextEdit {{
                background-color: {self.env.theme.colors.tertiary.name()};
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            QMainWindow QLabel {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
            }}
        """)

    def setup(self) -> void:
        # Setup graphic properties
        self.set_style()
        self.compArea_layout.setObjectName(u"compArea_layout")
        self.compArea_layout.setSpacing(0)
        self.compArea_layout.setContentsMargins(0, 0, 0, 0)
        self.compArea_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scrollAreaCompContents.setLayout(self.compArea_layout)
        self.dockWidgetContents_comp.setPreferredWidth(300)
        self.dockWidgetContents_details.setPreferredWidth(300)

        # Setup texts
        self.lineEdit_component.setPlaceholderText(_("ui.component.filter"))
        self.setWindowTitle(_("ui.title_short"))
        self.dockWidget_components.setWindowTitle(_("ui.component.title"))
        self.dockWidget_details.setWindowTitle(_("ui.details.title"))

    def create_canvas(self, title: string) -> TabHandler:
        handler = EditorWindow.TabHandler.allocate(title)
        canvas = EditionCanvas(self.tabWidget_editor)
        self.tabWidget_editor.addTab(canvas, title)
        self.register_canvas(handler, canvas)
        return handler

    def remove_canvas(self, canvas: EditionCanvas) -> void:
        pass
