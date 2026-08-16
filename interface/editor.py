# -*- coding: utf-8 -*-

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from alias import *
from alias import Nullable
from core.localization import _
from core.script import Script
from core.environment import Environment
from core.project import Project
from core.resource import Resource
from kits.fluent.fluent import UDF
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
        self.setup_actions()

        # Test code
        self.env.import_kit(r'kits/common')
        self.env.import_kit(r'kits/fluent')  # UDF delegations for the CLK components
        tab = self.create_canvas('TestTab')
        canvas = self.canvas(tab)
        # The tab widget is the scroll area wrapping the canvas (through its viewport)
        container: Nullable[QWidget] = canvas
        while container is not null and not isinstance(container, QScrollArea):
            container = container.parentWidget()
        self.tabWidget_editor.setCurrentWidget(container)
        # canvas.create_lineedit(QRectF(0, 0, 100, 20))
        comp_meta = self.env.kit_manager.lookup('clk.br')
        comp = comp_meta.component_type(null, canvas)
        canvas.add_interface(comp.interface)
        self.script = Script(comp)
        # Test project so that the building pipeline has something to compile
        project = Project('Test', UDF)
        project.scripts.append(self.script)
        self.env.project = project
        # comp.interface.paint(canvas)
        # Visual code edit: type e.g. "if" and press Enter to insert a Branch component
        # inline into the text. Non-positive width extends the edit to the canvas right edge,
        # so inserted components align with the text column.
        # code_edit = canvas.create_visual_code_edit(QRectF(30, 280, 0, 30))
        # code_edit.setFocus()

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
        # Translucent background for visual code edits, so that components painted
        # on the canvas underneath remain visible through the edit
        vce_bg = QColor(self.env.theme.colors.tertiary)
        vce_bg.setAlpha(100)
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
            QMainWindow VisualCodeEdit {{
                background-color: {vce_bg.name(QColor.NameFormat.HexArgb)};
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            /* The canvas scroll area needs a solid background: 'transparent' is not
               composited on opaque native windows and shows up as black on Windows */
            QScrollArea#canvasScrollArea {{
                background-color: {self.env.theme.colors.secondary.name()};
                border: none;
                border-radius: 6px;
            }}
            /* The viewport is a separate widget layer; give it the same solid color */
            QScrollArea#canvasScrollArea > QWidget {{
                background-color: {self.env.theme.colors.secondary.name()};
                border-radius: 6px;
            }}
            QScrollArea#canvasScrollArea QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 2px;
            }}
            QScrollArea#canvasScrollArea QScrollBar::handle:vertical {{
                background: {self.env.theme.colors.tertiary.name()};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollArea#canvasScrollArea QScrollBar::add-line:vertical,
            QScrollArea#canvasScrollArea QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QMainWindow QLabel {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
            }}
            QMainWindow QCheckBox {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
            }}
            
            /* Menu bar */
            QMenuBar {{
                background-color: {self.env.theme.colors.background.name()};
                color: {self.env.theme.colors.foreground.name()};
            }}
            QMenuBar::item {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
                padding: 5px 10px;
                border-radius: 6px;
            }}
            QMenuBar::item:selected {{
                background-color: {self.env.theme.colors.tertiary.name()};
            }}
            QMenuBar::item:pressed {{
                background-color: {tp.name()};
            }}
            
            /* Dropdown menus */
            QMenu {{
                background-color: {self.env.theme.colors.secondary.name()};
                color: {self.env.theme.colors.foreground.name()};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
                padding: 6px 18px;
                border-radius: 6px;
            }}
            QMenu::item:selected {{
                background-color: {self.env.theme.colors.tertiary.name()};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {self.env.theme.colors.tertiary.name()};
                margin: 4px 8px;
            }}
        """)

    def setup_actions(self) -> void:
        # Theme-aware icons live in res/images/<theme name in lowercase>
        icon_dir = Resource.resource_path('images', self.env.theme.name.lower())

        self.action_compile = QAction(QIcon(str(icon_dir / 'compile.svg')), _('ui.action.compile'), self)
        self.action_compile.setShortcut(QKeySequence(Qt.Key.Key_F10))
        self.action_compile.triggered.connect(self.compile_project)

        self.menu_file = self.menubar.addMenu(_('ui.menu.file'))
        self.menu_edit = self.menubar.addMenu(_('ui.menu.edit'))
        self.menu_view = self.menubar.addMenu(_('ui.menu.view'))
        self.menu_code = self.menubar.addMenu(_('ui.menu.code'))
        self.menu_code.addAction(self.action_compile)
        self.toolBar.addAction(self.action_compile)

    def compile_project(self) -> void:
        """Build the loaded project and report the outcome in the status bar."""
        if self.env.project is null:
            self.statusbar.showMessage(_('ui.build.no_project'), 5000)
            return
        try:
            artifacts = self.env.build()
        except Exception as e:  # Building must never crash the UI
            self.statusbar.showMessage(_('ui.build.fail').format(null, str(e)), 8000)
            return
        self.statusbar.showMessage(
            _('ui.build.success').format(null, '; '.join(str(artifact) for artifact in artifacts)), 8000)

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
        # The canvas grows with its contents; the scroll area provides the page scrollbar
        # (a single scrollbar for the whole tab, never per-component scrollbars)
        scroll = QScrollArea(self.tabWidget_editor)
        scroll.setObjectName('canvasScrollArea')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # QScrollArea.setWidget turns autoFillBackground on for the scrolled widget,
        # which would fill the canvas with the palette's Window role (the dark system
        # color on dark-mode systems); the canvas must stay background-less so that the
        # styled viewport color underneath shows through
        canvas = EditionCanvas(scroll.viewport())
        scroll.setWidget(canvas)
        canvas.setAutoFillBackground(False)
        self.tabWidget_editor.addTab(scroll, title)
        self.register_canvas(handler, canvas)
        return handler

    def remove_canvas(self, canvas: EditionCanvas) -> void:
        pass
