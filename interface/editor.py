# -*- coding: utf-8 -*-

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from alias import *
from alias import Nullable
from core.build import Builder
from core.localization import _
from core.script import Script
from core.environment import Environment
from core.project import Project
from core.resource import Resource
from kits.fluent.fluent import UDF
from interface.ui_style_editor import Ui_EditorWindow
from interface.edition_canvas import EditionCanvas
from interface.component_palette import ComponentPalette


@final
class EditorWindow(QMainWindow, Ui_EditorWindow):
    _instance: Nullable['EditorWindow'] = null

    @staticmethod
    def build_error_rows(error: BaseException) -> IList[tuple[string, string, string]]:
        """
        Decompose a building exception into rows (level, code, message) of the
        build message table: one row per problem the error carries (the B1006
        static checking lists every problem), or a single row describing it.
        """
        if isinstance(error, Builder.BuildError) and len(error.texts) == 1 \
                and isinstance(error.texts[0], string):
            return [('error', error.code, line) for line in string(error.texts[0]).splitlines()]
        return [('error', getattr(error, 'code', ''), str(error))]

    @staticmethod
    def fill_build_table(table: QTableWidget, rows: IEnumerable[tuple[string, string, string]]) -> void:
        """Fill the build message table with (level, code, message) rows."""
        table.setRowCount(0)
        for level, code, message in rows:
            row = table.rowCount()
            table.insertRow(row)
            if level == 'error':
                label = _('ui.build.level.error')
            elif level == 'warning':
                label = _('ui.build.level.warning')
            else:
                label = _('ui.build.level.info')
            for column, text in enumerate((label, code, message)):
                item = QTableWidgetItem(text)
                if column < 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    if level == 'error':
                        item.setForeground(QColor('#D9534F'))  # Error rows announce their level
                    elif level == 'warning':
                        item.setForeground(QColor('#E0A800'))  # Warnings stay gentler than errors
                table.setItem(row, column, item)

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

        # Build message panel (bottom dock): a table listing the compile
        # messages like an IDE's error list, so every problem the build
        # reports stays visible with its level and code
        self.dock_build = QDockWidget(_('ui.build.title'), self)
        self.dock_build.setObjectName('dockWidget_build')
        self.table_build_messages = QTableWidget(0, 3, self.dock_build)
        self.table_build_messages.setObjectName('tableBuildMessages')
        self.table_build_messages.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_build_messages.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_build_messages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_build_messages.verticalHeader().setVisible(False)
        self.table_build_messages.setShowGrid(False)
        self.table_build_messages.horizontalHeader().setStretchLastSection(True)
        self.table_build_messages.setHorizontalHeaderLabels(
            [_('ui.build.column.level'), _('ui.build.column.code'), _('ui.build.column.message')])
        self.dock_build.setWidget(self.table_build_messages)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_build)
        self.dock_build.hide()

        self.setup()
        self.setup_actions()

        # Test code
        self.env.import_kit(r'kits/cbased')  # C checker; the fluent kit depends on it
        self.env.import_kit(r'kits/common')
        self.env.import_kit(r'kits/fluent')  # UDF delegations for the CLK components
        # Component palette (left dock): one draggable entry per component the
        # code completion can insert; the filter box above narrows the listing
        self.component_palette = ComponentPalette(self.scrollAreaCompContents)
        self.compArea_layout.addWidget(self.component_palette)
        # noinspection bad-argument-type
        self.lineEdit_component.textChanged.connect(self.component_palette.apply_filter)
        tab = self.create_canvas('TestTab')
        canvas = self.canvas(tab)
        # The tab widget is the scroll area wrapping the canvas (through its viewport)
        container: Nullable[QWidget] = canvas
        while container is not null and not isinstance(container, QScrollArea):
            container = container.parentWidget()
        self.tabWidget_editor.setCurrentWidget(container)
        # canvas.create_lineedit(QRectF(0, 0, 100, 20))
        # The script root is a translation unit: a whole-page visual code edit
        # filling the canvas' client rectangle (leaving only its margin). Type e.g.
        # "adjust" and press Enter to insert a DEFINE_ADJUST component inline.
        comp_meta = self.env.kit_manager.lookup('fluent.translation_unit')
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
            QDockWidget {{
                color: {self.env.theme.colors.foreground.name()};
            }}
            QDockWidget::title {{
                background-color: {self.env.theme.colors.tertiary.name()};
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            QScrollArea, QWidget#{self.scrollAreaCompContents.objectName()} {{
                background-color: {self.env.theme.colors.secondary.name()};
                border-radius: 6px;
            }}
            
            /* Component palette (left dock): draggable entries of the components
               the code completion can insert */
            QLabel#paletteHeader {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
                font-weight: bold;
                padding: 6px 2px 2px 2px;
            }}
            QLabel#paletteGroupHeader {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
                padding: 4px 2px 1px 12px;
            }}
            _PaletteEntry {{
                background-color: {self.env.theme.colors.tertiary.name()};
                border-radius: 6px;
                padding: 4px 8px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            _PaletteEntry:hover {{
                background-color: {tp.name()};
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
            QMainWindow QPlainTextEdit {{
                background-color: {self.env.theme.colors.tertiary.name()};
                border-radius: 6px;
                color: {self.env.theme.colors.foreground.name()};
            }}
            /* Combo boxes (e.g. the type option of a set): the box and its
               dropdown list both follow the theme colors */
            QMainWindow QComboBox {{
                background-color: {self.env.theme.colors.tertiary.name()};
                color: {self.env.theme.colors.foreground.name()};
                border: none;
                border-radius: 6px;
                padding: 2px 8px;
            }}
            QMainWindow QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {self.env.theme.colors.secondary.name()};
                color: {self.env.theme.colors.foreground.name()};
                selection-background-color: {self.env.theme.colors.selected.name()};
                selection-color: {self.env.theme.colors.foreground.name()};
                border-radius: 6px;
                outline: none;
            }}
            /* Status bar */
            QStatusBar {{
                background-color: {self.env.theme.colors.secondary.name()};
                color: {self.env.theme.colors.foreground.name()};
            }}
            QStatusBar QLabel {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
            }}
            /* Build message table (the bottom error-list dock) */
            QMainWindow QTableWidget {{
                background-color: {self.env.theme.colors.tertiary.name()};
                color: {self.env.theme.colors.foreground.name()};
                border-radius: 6px;
            }}
            QTableWidget::item:selected {{
                background-color: {self.env.theme.colors.selected.name()};
                color: {self.env.theme.colors.foreground.name()};
            }}
            QHeaderView::section {{
                background-color: {self.env.theme.colors.secondary.name()};
                color: {self.env.theme.colors.foreground.name()};
                border: none;
                padding: 4px 8px;
            }}
            /* Advisory lint marking: deliberately gentler than the invalid
               marking below, so the deep check never shouts while typing */
            QLineEdit[ecTidyWarning="true"], HyperTextEdit[ecTidyWarning="true"], VisualCodeEdit[ecTidyWarning="true"] {{
                border: 1px solid #E0A800;
                border-radius: 6px;
                background-color: rgba(224, 168, 0, 12%);
            }}
            /* Immediate static checking: fields the registered checkers reject
               carry the ecInvalid property and are drawn red */
            QLineEdit[ecInvalid="true"], HyperTextEdit[ecInvalid="true"], VisualCodeEdit[ecInvalid="true"] {{
                border: 1px solid #D9534F;
                border-radius: 6px;
                background-color: rgba(217, 83, 79, 14%);
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
            
            /* Toolbar */
            QToolBar {{
                background-color: {self.env.theme.colors.background.name()};
                color: {self.env.theme.colors.foreground.name()};
                border: none;
                spacing: 2px;
                padding: 2px;
            }}
            QToolBar QToolButton {{
                background: transparent;
                color: {self.env.theme.colors.foreground.name()};
                padding: 5px;
                border: none;
                border-radius: 6px;
            }}
            QToolBar QToolButton:hover {{
                background-color: {self.env.theme.colors.tertiary.name()};
            }}
            QToolBar QToolButton:pressed {{
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
        """Build the loaded project and report the outcome: the status bar
        summarizes it, the bottom build panel lists the compile messages
        (or the generated artifacts on success)."""
        if self.env.project is null:
            self.statusbar.showMessage(_('ui.build.no_project'), 5000)
            return
        try:
            artifacts, warnings = self.env.build()
        except Exception as e:  # Building must never crash the UI
            self.fill_build_table(self.table_build_messages, self.build_error_rows(e))
            self.dock_build.show()
            self.statusbar.showMessage(_('ui.build.fail').format(str(e)), 8000)
            return
        # Warnings precede the artifact list: one row per problem line (the
        # B1007 product check joins them into its message)
        rows: IList[tuple[string, string, string]] = [
            ('warning', warning.code, line)
            for warning in warnings for line in warning.message.splitlines()]
        rows.extend(('info', '', str(artifact)) for artifact in artifacts)
        self.fill_build_table(self.table_build_messages, rows)
        self.dock_build.show()
        self.statusbar.showMessage(
            _('ui.build.success').format('; '.join(str(artifact) for artifact in artifacts)), 8000)

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
