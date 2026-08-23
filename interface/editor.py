# -*- coding: utf-8 -*-

import json
from pathlib import Path

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *

from alias import *
from alias import Nullable
from core.build import Builder
from core.localization import _
from core.script import Script
from core.environment import Environment
from core.meta import SupportedLanguage
from core.project import Project
from core.resource import Resource
from kits.fluent.fluent import UDF
from interface.ui_style_editor import Ui_EditorWindow
from interface.edition_canvas import EditionCanvas
from interface.component_palette import ComponentPalette
from interface.project_properties_dialog import ProjectPropertiesDialog


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
        # Identity counter of allocated handlers; equality and hashing derive
        # from the allocated value, so every handler must carry a unique one
        _next_value: int = 1
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
            handler = EditorWindow.TabHandler(cls._next_value, title)
            cls._next_value += 1
            return handler

        @property
        def valid(self) -> bool:
            return (self in EditorWindow._instance.tabs) if EditorWindow._instance is not null else False

    def __init__(self, parent: Nullable[QWidget] = null):
        super(EditorWindow, self).__init__(parent)
        self.setupUi(self)
        self.tabs: IDictionary[EditorWindow.TabHandler, EditionCanvas] = {}
        self._script_handlers: IDictionary[EditorWindow.TabHandler, Script] = {}
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
        self._init_blank_project()

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

            /* Dialogs */
            QDialog {{
                background-color: {self.env.theme.colors.background.name()};
                color: {self.env.theme.colors.foreground.name()};
            }}
            QDialog QLabel {{
                color: {self.env.theme.colors.foreground.name()};
            }}
            QDialog QLineEdit {{
                background-color: {self.env.theme.colors.secondary.name()};
                color: {self.env.theme.colors.foreground.name()};
                border: 1px solid {self.env.theme.colors.tertiary.name()};
                border-radius: 4px;
                padding: 4px;
            }}
            QDialog QPushButton {{
                background-color: {self.env.theme.colors.primary.name()};
                color: {self.env.theme.colors.foreground.name()};
                border: 1px solid {self.env.theme.colors.tertiary.name()};
                border-radius: 4px;
                padding: 4px 16px;
                min-width: 80px;
            }}
            QDialog QPushButton:hover {{
                background-color: {self.env.theme.colors.secondary.name()};
            }}
            QDialog QPushButton:pressed {{
                background-color: {self.env.theme.colors.tertiary.name()};
            }}
        """)

    def setup_actions(self) -> void:
        # Theme-aware icons live in res/images/<theme name in lowercase>
        icon_dir = Resource.resource_path('images', self.env.theme.name.lower())

        self.action_compile = QAction(QIcon(str(icon_dir / 'compile.svg')), _('ui.action.compile'), self)
        self.action_compile.setShortcut(QKeySequence(Qt.Key.Key_F10))
        self.action_compile.triggered.connect(self.compile_project)

        self.menu_file = self.menubar.addMenu(_('ui.menu.file'))

        self.action_new_project = QAction(_('ui.action.new_project'), self)
        self.action_new_project.setShortcut(QKeySequence('Ctrl+Shift+N'))
        self.action_new_project.triggered.connect(self.new_project)

        self.action_open_project = QAction(_('ui.action.open_project'), self)
        self.action_open_project.setShortcut(QKeySequence('Ctrl+O'))
        self.action_open_project.triggered.connect(self.open_project)

        self.action_add_script = QAction(_('ui.action.add_script'), self)
        # triggered carries the checked flag; drop it so add_script gets no name
        # and asks for one in the dialog
        self.action_add_script.triggered.connect(lambda _checked: self.add_script())

        self.action_save = QAction(_('ui.action.save'), self)
        self.action_save.setShortcut(QKeySequence('Ctrl+S'))
        self.action_save.triggered.connect(self.save_project)

        self.action_save_as = QAction(_('ui.action.save_as'), self)
        self.action_save_as.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self.action_save_as.triggered.connect(self.save_project_as)

        self.menu_file.addAction(self.action_new_project)
        self.menu_file.addAction(self.action_open_project)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_save)
        self.menu_file.addAction(self.action_save_as)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_add_script)
        self.menu_file.addSeparator()

        self.action_properties = QAction(_('ui.action.properties'), self)
        self.action_properties.setShortcut(QKeySequence('Alt+Return'))
        self.action_properties.triggered.connect(self.show_project_properties)
        self.menu_file.addAction(self.action_properties)

        self.menu_edit = self.menubar.addMenu(_('ui.menu.edit'))
        self.menu_view = self.menubar.addMenu(_('ui.menu.view'))
        self.menu_code = self.menubar.addMenu(_('ui.menu.code'))
        self.menu_code.addAction(self.action_compile)
        self.toolBar.addAction(self.action_compile)

        self.tabWidget_editor.setTabsClosable(True)
        self.tabWidget_editor.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabWidget_editor.currentChanged.connect(self._on_tab_changed)

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

    def _init_blank_project(self) -> void:
        """Initialize a blank project with default kits and one empty script."""
        self.env.import_kit(r'kits/cbased')  # C checker; the fluent kit depends on it
        self.env.import_kit(r'kits/common')
        self.env.import_kit(r'kits/fluent')  # UDF delegations for the CLK components
        self._setup_component_palette()
        project = Project(_('ui.project.default_name'), UDF)
        self.env.project = project
        self._current_script = null
        self._script_handlers.clear()
        tab = self.create_canvas(_('ui.script.default_name'))
        canvas = self.canvas(tab)
        script = project.create_script(
            _('ui.script.default_name'), 'fluent.translation_unit',
            self.env.kit_manager, canvas)
        self._connect_canvas_dirty(canvas, script)
        canvas.add_interface(script.tu.interface)
        self._script_handlers[tab] = script
        self._current_script = script
        self._update_title()
        self._dirty_timer = QTimer(self)
        self._dirty_timer.timeout.connect(self._sync_dirty_title)
        self._dirty_timer.start(2000)

    def _setup_component_palette(self) -> void:
        """Create the component palette dock (left panel) with its filter binding."""
        self.component_palette = ComponentPalette(self.scrollAreaCompContents)
        self.compArea_layout.addWidget(self.component_palette)
        # noinspection bad-argument-type
        self.lineEdit_component.textChanged.connect(self.component_palette.apply_filter)

    def new_project(self) -> void:
        """Create a new blank project, prompting to save the current one if dirty."""
        if self.env.project is not null and self.env.project.is_dirty:
            reply = QMessageBox.question(
                self, _('ui.dialog.unsaved_title'),
                _('ui.dialog.unsaved_new'),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                self.save_project()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        for handler in list(self.tabs.keys()):
            self.tabWidget_editor.removeTab(0)
        self.tabs.clear()
        self._script_handlers.clear()
        project = Project(_('ui.project.default_name'), UDF)
        self.env.project = project
        self._current_script = null
        tab = self.create_canvas(_('ui.script.default_name'))
        canvas = self.canvas(tab)
        script = project.create_script(
            _('ui.script.default_name'), 'fluent.translation_unit',
            self.env.kit_manager, canvas)
        self._connect_canvas_dirty(canvas, script)
        canvas.add_interface(script.tu.interface)
        self._script_handlers[tab] = script
        self._current_script = script
        self._update_title()

    def open_project(self) -> void:
        """Open an existing .ecproj project file, replacing the current project."""
        if self.env.project is not null and self.env.project.is_dirty:
            reply = QMessageBox.question(
                self, _('ui.dialog.unsaved_title'),
                _('ui.dialog.unsaved_open'),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                self.save_project()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        path, _filter = QFileDialog.getOpenFileName(
            self, _('ui.dialog.open_project'), '',
            _('ui.dialog.ecproj_filter'))
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError('Invalid project file')
            project = Project(data['name'], deserialize(SupportedLanguage, data['target_lang']))
            project.path = path
            project.required_kits = data.get('required_kits', [])
            project.c_standard = data.get('c_standard', 'c99')
        except Exception as e:
            QMessageBox.critical(self, _('ui.dialog.open_failed'), str(e))
            return
        for handler in list(self.tabs.keys()):
            self.tabWidget_editor.removeTab(0)
        self.tabs.clear()
        self._script_handlers.clear()
        self.env.project = project
        self._current_script = null
        for script_data in data.get('scripts', []):
            tab = self.create_canvas(script_data.get('display_name', 'untitled'))
            canvas = self.canvas(tab)
            script = Script.restore(script_data, self.env.kit_manager, canvas)
            project.scripts.append(script)
            self._connect_canvas_dirty(canvas, script)
            canvas.add_interface(script.tu.interface)
            self._script_handlers[tab] = script
        if project.scripts:
            self._current_script = project.scripts[0]
        project.clear_dirty()
        self._update_title()

    def save_project(self) -> void:
        """Save the project: every unsaved tab asks whether it should be saved
        (saving a script without a path opens the file dialog first); the
        project archive is written afterwards. The archive itself goes through
        Save As while the project has no path yet."""
        if self.env.project is null:
            return
        if self.env.project.path is null:
            self.save_project_as()
            return
        if not self._name_untitled_scripts():
            return  # The user canceled the naming: the save aborts
        skipped = self._confirm_script_saves()
        if skipped is null:
            return  # The user canceled the whole save
        try:
            self.env.project.save(self.env.project.path)
        except Exception as e:
            QMessageBox.critical(self, _('ui.dialog.save_failed'), str(e))
            return
        # The archive persisted the skipped scripts too, but their changes were
        # deliberately not saved: keep them dirty so the state stays honest
        for script in skipped:
            script.mark_dirty()
        self._update_title()

    def save_project_as(self) -> void:
        """Save the project to a user-chosen .ecproj file path."""
        if self.env.project is null:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, _('ui.dialog.save_as'), '',
            _('ui.dialog.ecproj_filter'))
        if not path:
            return
        if not path.endswith(Project.Extension):
            path += Project.Extension
        self.env.project.path = path
        self.save_project()

    def add_script(self, name: Nullable[string] = null) -> void:
        """Add a new script to the project with a translation unit root component.
        Without an explicit name the script starts untitled ('Untitled-N'); saving
        such a script asks for a file, whose stem becomes the script's name."""
        if self.env.project is null:
            return
        untitled = False
        if not isinstance(name, str) or not name:
            name = self._next_untitled_name()
            untitled = True
        for existing in self.env.project.scripts:
            if existing.display_name == name:
                QMessageBox.warning(self, _('ui.dialog.add_script'), _('ui.dialog.script_exists'))
                return
        tab = self.create_canvas(name)
        canvas = self.canvas(tab)
        script = self.env.project.create_script(
            name, 'fluent.translation_unit', self.env.kit_manager, canvas)
        if untitled:
            # create_script assigned the placeholder through the display_name
            # setter, which settles the script; restore the untitled state
            script.untitled = True
        self._connect_canvas_dirty(canvas, script)
        canvas.add_interface(script.tu.interface)
        self._script_handlers[tab] = script
        self._current_script = script
        container: Nullable[QWidget] = canvas
        while container is not null and not isinstance(container, QScrollArea):
            container = container.parentWidget()
        self.tabWidget_editor.setCurrentWidget(container)

    def show_project_properties(self) -> void:
        """Open the project properties dialog and apply changes on accept."""
        if self.env.project is null:
            return
        dlg = ProjectPropertiesDialog(self.env.project, self.env.kit_manager, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            old_name = self.env.project.name
            dlg.apply_to(self.env.project)
            if self.env.project.name != old_name:
                self._update_title()

    def _next_untitled_name(self) -> string:
        """The first free 'Untitled-N' display name for a freshly added script."""
        taken = {script.display_name for script in self.env.project.scripts}
        number = 1
        name = f'{_("ui.script.untitled")}-{number}'
        while name in taken:
            number += 1
            name = f'{_("ui.script.untitled")}-{number}'
        return name

    def _name_untitled_scripts(self) -> bool:
        """Ask a real name for every untitled script before saving: confirming
        renames the script (and its tab, which settles the untitled state);
        canceling aborts and keeps the placeholders. Returns whether every
        untitled script ended up named."""
        project = self.env.project
        assert project is not null
        for script in project.scripts:
            if not script.untitled:
                continue
            dlg = QInputDialog(self)
            dlg.setInputMode(QInputDialog.InputMode.TextInput)
            dlg.setWindowTitle(_('ui.dialog.name_script'))
            dlg.setLabelText(_('ui.dialog.name_script_prompt').format(script.display_name))
            ok = dlg.exec() == QDialog.DialogCode.Accepted
            name = dlg.textValue() if ok else ''
            if not ok or not name:
                return False
            script.display_name = name
            self._set_tab_title(script, name)
        return True

    def _confirm_script_saves(self) -> Nullable[IList[Script]]:
        """Publish one save/discard/cancel dialog per unsaved tab and persist
        the scripts the user chose to save. Returns the scripts the user chose
        NOT to save (they stay dirty), or ``null`` when the user canceled the
        whole save."""
        project = self.env.project
        assert project is not null
        skipped: IList[Script] = []
        for script in project.scripts:
            if not script.is_dirty:
                continue
            reply = QMessageBox.question(
                self, _('ui.dialog.unsaved_title'),
                _('ui.dialog.unsaved_save_script').format(script.display_name),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                return null
            if reply == QMessageBox.StandardButton.Discard:
                skipped.append(script)
                continue
            if not self._save_script_file(script):
                return null  # No path chosen (or write failed): abort the save
        return skipped

    def _save_script_file(self, script: Script) -> bool:
        """Persist one script to its file: a script without a path opens the
        save-file dialog first. Returns whether the script ended up saved."""
        if script.path is null:
            suggested = f'{script.display_name}{Script.Extension}'
            path, _filter = QFileDialog.getSaveFileName(
                self, _('ui.dialog.save_script'), suggested,
                _('ui.dialog.ecscript_filter'))
            if not path:
                return False
            if not path.endswith(Script.Extension):
                path += Script.Extension
            script.path = Path(path)
        try:
            script.save(script.path)
        except Exception as e:
            QMessageBox.critical(self, _('ui.dialog.save_failed'), str(e))
            return False
        if script.untitled:
            # The file name becomes the script's name: it stops being untitled
            script.display_name = script.path.stem
            self._set_tab_title(script, script.display_name)
        return True

    def _set_tab_title(self, script: Script, title: string) -> void:
        """Rename the tab hosting the script, keeping it in sync with the
        script's display name."""
        for handler, candidate in self._script_handlers.items():
            if candidate is not script:
                continue
            canvas = self.tabs.get(handler, null)
            if canvas is null:
                return
            for index in range(self.tabWidget_editor.count()):
                container = self.tabWidget_editor.widget(index)
                if container is not null and container.findChild(EditionCanvas) is canvas:
                    self.tabWidget_editor.setTabText(index, title)
                    return

    def _on_tab_changed(self, index: int) -> void:
        """Update the current script when the user switches tabs."""
        if index < 0:
            self._current_script = null
            return
        container = self.tabWidget_editor.widget(index)
        for handler, canvas in self.tabs.items():
            if canvas is not null:
                scroll: Nullable[QWidget] = canvas
                while scroll is not null and not isinstance(scroll, QScrollArea):
                    scroll = scroll.parentWidget()
                if scroll == container:
                    self._current_script = self._script_handlers.get(handler, null)
                    return
        self._current_script = null

    def _sync_dirty_title(self) -> void:
        """Periodic sync: refresh the title bar when the project dirty state changes."""
        self._update_title()

    def _connect_canvas_dirty(self, canvas: EditionCanvas, script: Script) -> void:
        """Wire canvas edits to the script's dirty flag: the canvas hosts exactly
        one script, and its dirtiness surfaces on the project too (see
        ``Project.is_dirty``). The canvas binds the callback when it creates the
        script's edit controls, so this must run before the interface is added."""
        canvas.set_dirty_callback(lambda *_args: script.mark_dirty())

    def _update_title(self) -> void:
        name = self.env.project.name if self.env.project is not null else _('ui.project.default_name')
        dirty = self.env.project is not null and self.env.project.is_dirty
        suffix = ' *' if dirty else ''
        self.setWindowTitle(f'{name}{suffix} - {_("ui.title_short")}')

    def _on_tab_close_requested(self, index: int) -> void:
        container = self.tabWidget_editor.widget(index)
        canvas = container.findChild(EditionCanvas) if container is not null else null
        if canvas is not null:
            handler = null
            for h, c in self.tabs.items():
                if c == canvas:
                    handler = h
                    break
            script = self._script_handlers.get(handler, null) if handler is not null else null
            if script is not null and script.is_dirty:
                reply = QMessageBox.question(
                    self, _('ui.dialog.unsaved_title'),
                    _('ui.dialog.unsaved_close'),
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Save:
                    self.save_project()
                elif reply == QMessageBox.StandardButton.Cancel:
                    return
            if handler is not null and handler in self._script_handlers:
                del self._script_handlers[handler]
            self.remove_canvas(canvas)
        self.tabWidget_editor.removeTab(index)

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
        key = null
        for k, v in self.tabs.items():
            if v == canvas:
                key = k
                break
        if key is null:
            raise KeyError('No such canvas to unregister')
        self.tabs.pop(key)

    @property
    def script(self) -> Nullable[Script]:
        """The currently active script (backward-compatible access for probes)."""
        return self._current_script
