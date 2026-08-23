# -*- coding: utf-8 -*-

from pathlib import Path

from PySide6.QtCore import *
from PySide6.QtWidgets import *

from alias import *
from core.build import BuildConfig
from core.kit import KitManager
from core.localization import _
from core.project import Project


@final
class ProjectPropertiesDialog(QDialog):
    """Modal dialog for editing project properties: general info, imported kits,
    and build configuration. Changes are held in temporary fields until the user
    accepts; ``apply_to`` writes them back to the project."""

    # Optimization level entries: (BuildConfig constant, i18n key)
    _OPT_LEVELS: tuple[tuple[int, string], ...] = (
        (BuildConfig.OptimizationLevel.O0, 'ui.props.opt.none'),
        (BuildConfig.OptimizationLevel.O1, 'ui.props.opt.basic'),
        (BuildConfig.OptimizationLevel.O2, 'ui.props.opt.standard'),
        (BuildConfig.OptimizationLevel.O3, 'ui.props.opt.aggressive'),
    )

    def __init__(self, project: Project, kit_manager: KitManager,
                 parent: Nullable[QWidget] = null):
        super().__init__(parent)
        self._project = project
        self._kit_manager = kit_manager
        self.setWindowTitle(_('ui.dialog.properties_title'))
        self.setMinimumWidth(420)
        self._setup_ui()
        self._load_from_project()

    def _setup_ui(self) -> void:
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._create_general_tab(), _('ui.props.tab.general'))
        self._tabs.addTab(self._create_kits_tab(), _('ui.props.tab.kits'))
        self._tabs.addTab(self._create_build_tab(), _('ui.props.tab.build'))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_general_tab(self) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._edit_name = QLineEdit(tab)
        form.addRow(_('ui.props.name'), self._edit_name)

        self._label_lang = QLabel(tab)
        form.addRow(_('ui.props.target_lang'), self._label_lang)

        self._combo_c_standard = QComboBox(tab)
        for std in Project.available_c_standards():
            self._combo_c_standard.addItem(std.upper(), std)
        form.addRow(_('ui.props.c_standard'), self._combo_c_standard)

        return tab

    def _create_kits_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        self._kit_list = QListWidget(tab)
        self._kit_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self._kit_list)

        return tab

    def _create_build_tab(self) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        dir_row = QHBoxLayout()
        self._edit_output = QLineEdit(tab)
        dir_row.addWidget(self._edit_output)
        self._btn_browse = QPushButton(_('ui.props.browse'), tab)
        self._btn_browse.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(self._btn_browse)
        form.addRow(_('ui.props.output_dir'), dir_row)

        self._combo_opt = QComboBox(tab)
        for level, key in self._OPT_LEVELS:
            self._combo_opt.addItem(_(key), level)
        form.addRow(_('ui.props.opt_level'), self._combo_opt)

        return tab

    def _browse_output_dir(self) -> void:
        start = self._edit_output.text()
        path = QFileDialog.getExistingDirectory(self, _('ui.props.output_dir'), start)
        if path:
            self._edit_output.setText(path)

    def _load_from_project(self) -> void:
        """Fill controls from the current project state."""
        self._edit_name.setText(self._project.name)
        self._label_lang.setText(self._project.target_lang.name)

        idx = self._combo_c_standard.findData(self._project.c_standard)
        if idx >= 0:
            self._combo_c_standard.setCurrentIndex(idx)

        output = self._project.build_config.output
        self._edit_output.setText(str(output) if output is not null else '')
        opt_idx = self._combo_opt.findData(self._project.build_config.opt_level)
        if opt_idx >= 0:
            self._combo_opt.setCurrentIndex(opt_idx)

        self._kit_list.clear()
        if self._project.required_kits:
            for kit in self._project.required_kits:
                if isinstance(kit, str):
                    name = kit
                    desc = ''
                else:
                    name = kit.meta.display_name
                    desc = kit.meta.description
                label = f'{name}  —  {desc}' if desc else name
                self._kit_list.addItem(label)
        else:
            for kit in self._kit_manager:
                if kit.meta.description:
                    label = f'{kit.meta.display_name}  —  {kit.meta.description}'
                else:
                    label = kit.meta.display_name
                self._kit_list.addItem(label)
        if self._kit_list.count() == 0:
            self._kit_list.addItem(_('ui.props.kits.none'))

    def apply_to(self, project: Project) -> void:
        """Write the dialog values back to the project and mark it dirty."""
        new_name = self._edit_name.text().strip()
        if new_name:
            project.name = new_name
        c_std = self._combo_c_standard.currentData()
        if isinstance(c_std, str) and c_std:
            project.c_standard = c_std
        output_text = self._edit_output.text().strip()
        project.build_config.output = Path(output_text) if output_text else null
        opt_level = self._combo_opt.currentData()
        if isinstance(opt_level, int):
            project.build_config.opt_level = opt_level
        project.mark_dirty()
