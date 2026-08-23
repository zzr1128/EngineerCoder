# -*- coding: utf-8 -*-

from pathlib import Path

from PySide6.QtCore import *
from PySide6.QtGui import QColor
from PySide6.QtWidgets import *

from alias import *
from core.localization import _
from core.preferences import Preferences
from core.theme import Theme


@final
class PreferencesDialog(QDialog):
    """JetBrains-style preferences dialog with theme color editing."""

    _LANGUAGES: tuple[tuple[string, string], ...] = (
        ('zh_CN', '简体中文'),
        ('en_US', 'English'),
    )

    _DEFAULT_FONT_SIZE: int = 10
    _DEFAULT_COMPLETION_LIST_WIDTH: int = 280
    _DEFAULT_COMPLETION_DETAIL_WIDTH: int = 260
    _DEFAULT_COMPLETION_MAX_HEIGHT: int = 240

    _COLOR_KEYS: tuple[tuple[string, string], ...] = (
        ('background', 'ui.prefs.color.background'),
        ('primary', 'ui.prefs.color.primary'),
        ('secondary', 'ui.prefs.color.secondary'),
        ('tertiary', 'ui.prefs.color.tertiary'),
        ('side', 'ui.prefs.color.side'),
        ('foreground', 'ui.prefs.color.foreground'),
        ('selected', 'ui.prefs.color.selected'),
    )

    settings_changed = Signal(dict)

    def __init__(self, current_theme_name: string, current_language: string,
                 font_size: int = _DEFAULT_FONT_SIZE,
                 completion_list_width: int = _DEFAULT_COMPLETION_LIST_WIDTH,
                 completion_detail_width: int = _DEFAULT_COMPLETION_DETAIL_WIDTH,
                 completion_max_height: int = _DEFAULT_COMPLETION_MAX_HEIGHT,
                 current_colors: Nullable[IDictionary[string, string]] = null,
                 current_palette: Nullable[IList[IList[string]]] = null,
                 parent: Nullable[QWidget] = null):
        super().__init__(parent)
        self._current_theme_name = current_theme_name
        self._current_language = current_language
        self._font_size = font_size
        self._completion_list_width = completion_list_width
        self._completion_detail_width = completion_detail_width
        self._completion_max_height = completion_max_height
        self._current_colors: IDictionary[string, string] = dict(current_colors) if current_colors else {}
        self._current_palette: IList[IList[string]] = [list(row) for row in current_palette] if current_palette else []
        self._color_buttons: IDictionary[string, QPushButton] = {}
        self._color_label_ids: IDictionary[string, string] = {}
        self._palette_buttons: IList[IList[QPushButton]] = []
        self._btn_delete_theme: Nullable[QPushButton] = null
        self._combo_theme: Nullable[QComboBox] = null
        self.setWindowTitle(_('ui.prefs.title'))
        self.setMinimumSize(620, 520)
        self._setup_ui()
        self._load_current_values()

    # ── UI construction ──────────────────────────────────────────────

    def _setup_ui(self) -> void:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._category_list = QListWidget(self)
        self._category_list.setFixedWidth(160)
        self._category_list.setObjectName('prefsCategoryList')
        self._category_list.currentRowChanged.connect(self._on_category_changed)
        root.addWidget(self._category_list)

        right = QVBoxLayout()
        right.setContentsMargins(12, 12, 12, 12)

        self._stack = QStackedWidget(self)
        right.addWidget(self._stack, 1)

        self._stack.addWidget(self._create_appearance_page())
        self._stack.addWidget(self._create_editor_page())

        self._category_list.addItem(_('ui.prefs.cat.appearance'))
        self._category_list.addItem(_('ui.prefs.cat.editor'))
        self._category_list.setCurrentRow(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply,
            self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn:
            apply_btn.clicked.connect(self._on_apply)
        right.addWidget(buttons)

        root.addLayout(right, 1)

    def _make_separator(self, parent: QWidget) -> QFrame:
        line = QFrame(parent)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(2)
        return line

    def _create_appearance_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # ── Theme selection row ──
        self._combo_theme = QComboBox(page)
        self._available_themes = self._discover_themes()
        for theme_name, display_name in self._available_themes:
            self._combo_theme.addItem(display_name, theme_name)
        self._combo_theme.currentIndexChanged.connect(self._on_theme_changed)

        theme_row = QHBoxLayout()
        theme_row.addWidget(self._combo_theme, 1)

        btn_new = QPushButton(_('ui.prefs.theme.new'), page)
        btn_new.clicked.connect(self._on_new_theme)
        theme_row.addWidget(btn_new)

        btn_save_as = QPushButton(_('ui.prefs.theme.save_as'), page)
        btn_save_as.clicked.connect(self._on_save_as_theme)
        theme_row.addWidget(btn_save_as)

        self._btn_delete_theme = QPushButton(_('ui.prefs.theme.delete'), page)
        self._btn_delete_theme.clicked.connect(self._on_delete_theme)
        theme_row.addWidget(self._btn_delete_theme)

        form.addRow(_('ui.prefs.theme'), theme_row)

        # ── Language ──
        self._combo_lang = QComboBox(page)
        for lang_code, lang_label in self._LANGUAGES:
            self._combo_lang.addItem(lang_label, lang_code)
        form.addRow(_('ui.prefs.language'), self._combo_lang)

        # ── Color editing section ──
        form.addRow(self._make_separator(page))
        color_label = QLabel(_('ui.prefs.colors.section'), page)
        color_label.setStyleSheet('font-weight: bold;')
        form.addRow(color_label)

        for key, label_id in self._COLOR_KEYS:
            btn = QPushButton(page)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_color_clicked(k))
            self._color_buttons[key] = btn
            self._color_label_ids[key] = label_id
            form.addRow(_(label_id), btn)

        # ── Components palette section ──
        form.addRow(self._make_separator(page))
        palette_label = QLabel(_('ui.prefs.palette.section'), page)
        palette_label.setStyleSheet('font-weight: bold;')
        form.addRow(palette_label)

        palette_container = QWidget(page)
        palette_grid = QGridLayout(palette_container)
        palette_grid.setContentsMargins(0, 0, 0, 0)
        palette_grid.setSpacing(3)
        self._populate_palette_grid(palette_grid)
        form.addRow(palette_container)

        return page

    def _populate_palette_grid(self, grid: QGridLayout) -> void:
        self._palette_buttons = []
        for i, row_colors in enumerate(self._current_palette):
            row_buttons: IList[QPushButton] = []
            for j, color_hex in enumerate(row_colors):
                btn = QPushButton(grid.parentWidget())
                btn.setFixedSize(28, 22)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f'background-color: {color_hex}; border: 1px solid #999; border-radius: 3px;')
                btn.setToolTip(color_hex)
                btn.clicked.connect(lambda checked, r=i, c=j: self._on_palette_clicked(r, c))
                grid.addWidget(btn, i, j)
                row_buttons.append(btn)
            self._palette_buttons.append(row_buttons)

    def _create_editor_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._spin_font = QSpinBox(page)
        self._spin_font.setRange(6, 48)
        self._spin_font.setSuffix(' pt')
        form.addRow(_('ui.prefs.font_size'), self._spin_font)

        self._spin_comp_list = QSpinBox(page)
        self._spin_comp_list.setRange(120, 600)
        self._spin_comp_list.setSuffix(' px')
        form.addRow(_('ui.prefs.comp_list_width'), self._spin_comp_list)

        self._spin_comp_detail = QSpinBox(page)
        self._spin_comp_detail.setRange(120, 600)
        self._spin_comp_detail.setSuffix(' px')
        form.addRow(_('ui.prefs.comp_detail_width'), self._spin_comp_detail)

        self._spin_comp_height = QSpinBox(page)
        self._spin_comp_height.setRange(80, 600)
        self._spin_comp_height.setSuffix(' px')
        form.addRow(_('ui.prefs.comp_max_height'), self._spin_comp_height)

        return page

    # ── Theme discovery ──────────────────────────────────────────────

    def _discover_themes(self) -> list[tuple[string, string]]:
        """Use the backend API to enumerate bundled + user themes."""
        self._theme_built_in = {}
        result: list[tuple[string, string]] = []
        lang = self._current_language
        for entry in Preferences().available_themes():
            name = entry['name']
            display_names = entry.get('display_name', {})
            display = display_names.get(lang) or display_names.get('en_US') or Path(name).stem
            self._theme_built_in[name] = entry.get('built_in', False)
            result.append((name, display))
        return result

    # ── Load / update ────────────────────────────────────────────────

    def _load_current_values(self) -> void:
        idx = self._combo_theme.findData(self._current_theme_name)
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)
        idx = self._combo_lang.findData(self._current_language)
        if idx >= 0:
            self._combo_lang.setCurrentIndex(idx)
        self._spin_font.setValue(self._font_size)
        self._spin_comp_list.setValue(self._completion_list_width)
        self._spin_comp_detail.setValue(self._completion_detail_width)
        self._spin_comp_height.setValue(self._completion_max_height)
        self._update_color_buttons()
        self._update_delete_state()

    def _update_color_buttons(self) -> void:
        for key, btn in self._color_buttons.items():
            hex_ = self._current_colors.get(key, '#000000')
            btn.setStyleSheet(
                f'background-color: {hex_}; border: 1px solid #999; border-radius: 4px;')
            btn.setText(hex_)
        for i, row in enumerate(self._palette_buttons):
            for j, btn in enumerate(row):
                if i < len(self._current_palette) and j < len(self._current_palette[i]):
                    hex_ = self._current_palette[i][j]
                    btn.setStyleSheet(
                        f'background-color: {hex_}; border: 1px solid #999; border-radius: 3px;')
                    btn.setToolTip(hex_)

    def _update_delete_state(self) -> void:
        if self._btn_delete_theme:
            self._btn_delete_theme.setEnabled(not self._is_builtin_theme())

    def _is_builtin_theme(self) -> bool:
        return self._theme_built_in.get(self._current_theme_name, False)

    def _refresh_theme_dropdown(self) -> void:
        old_name = self._current_theme_name
        self._available_themes = self._discover_themes()
        self._combo_theme.blockSignals(True)
        self._combo_theme.clear()
        for theme_name, display_name in self._available_themes:
            self._combo_theme.addItem(display_name, theme_name)
        idx = self._combo_theme.findData(old_name)
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)
        self._combo_theme.blockSignals(False)
        self._update_delete_state()

    # ── Theme selection changed ──────────────────────────────────────

    def _on_theme_changed(self, index: int) -> void:
        if index < 0:
            return
        theme_name = self._combo_theme.itemData(index)
        if not theme_name:
            return
        try:
            theme = Theme.from_resource(theme_name)
            colors = serialize(theme.colors)
            self._current_colors = {k: v for k, v in colors.items() if not isinstance(v, list)}
            self._current_palette = [list(row) for row in colors.get('components', [])]
            self._current_theme_name = theme_name
            self._update_color_buttons()
            self._update_delete_state()
            self._emit_preview()
        except Exception:
            pass

    # ── Theme operations ─────────────────────────────────────────────

    def _on_new_theme(self) -> void:
        name, ok = QInputDialog.getText(
            self, _('ui.prefs.theme.new'), _('ui.prefs.theme.name_prompt'))
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            filename = Theme._normalize_theme_name(name)
        except ValueError:
            QMessageBox.warning(self, _('ui.prefs.theme.new'), name)
            return
        if filename in self._theme_built_in:
            QMessageBox.warning(self, _('ui.prefs.theme.new'),
                                _('ui.prefs.theme.exists'))
            return
        try:
            theme = Theme.create_new(name, {'en_US': name, 'zh_CN': name})
            theme.save_to_user()
        except Exception as e:
            QMessageBox.warning(self, _('ui.prefs.theme.new'), str(e))
            return
        filename = f'{theme.name}.json'
        self._current_theme_name = filename
        colors = serialize(theme.colors)
        self._current_colors = {k: v for k, v in colors.items() if not isinstance(v, list)}
        self._current_palette = [list(row) for row in colors.get('components', [])]
        self._refresh_theme_dropdown()
        idx = self._combo_theme.findData(filename)
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)
        self._update_color_buttons()
        self._emit_preview()

    def _on_save_as_theme(self) -> void:
        name, ok = QInputDialog.getText(
            self, _('ui.prefs.theme.save_as'), _('ui.prefs.theme.name_prompt'))
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            filename = Theme._normalize_theme_name(name)
        except ValueError:
            QMessageBox.warning(self, _('ui.prefs.theme.save_as'), name)
            return
        if filename in self._theme_built_in:
            QMessageBox.warning(self, _('ui.prefs.theme.save_as'),
                                _('ui.prefs.theme.exists'))
            return
        try:
            source = Theme.from_resource(self._current_theme_name)
            theme = Theme.duplicate(source, name, {'en_US': name, 'zh_CN': name})
            for attr in ('background', 'primary', 'secondary', 'tertiary',
                         'side', 'foreground', 'selected'):
                if attr in self._current_colors:
                    setattr(theme.colors, attr, QColor(self._current_colors[attr]))
            if self._current_palette:
                theme.colors.components = [[QColor(c) for c in row] for row in self._current_palette]
            theme.save_to_user()
        except Exception as e:
            QMessageBox.warning(self, _('ui.prefs.theme.save_as'), str(e))
            return
        filename = f'{theme.name}.json'
        self._current_theme_name = filename
        self._refresh_theme_dropdown()
        idx = self._combo_theme.findData(filename)
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)
        QMessageBox.information(self, _('ui.prefs.theme.save_as'),
                                _('ui.prefs.theme.saved'))

    def _on_delete_theme(self) -> void:
        if self._is_builtin_theme():
            QMessageBox.warning(self, _('ui.prefs.theme.delete'),
                                _('ui.prefs.theme.builtin_nodelete'))
            return
        reply = QMessageBox.question(
            self, _('ui.prefs.theme.delete'),
            _('ui.prefs.theme.confirm_delete').format(self._current_theme_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            Theme.delete_user(self._current_theme_name)
        except Exception as e:
            QMessageBox.critical(self, _('ui.prefs.theme.delete'), str(e))
            return
        self._current_theme_name = str(Preferences.Defaults['theme'])
        try:
            theme = Theme.from_resource(self._current_theme_name)
            colors = serialize(theme.colors)
            self._current_colors = {k: v for k, v in colors.items() if not isinstance(v, list)}
            self._current_palette = [list(row) for row in colors.get('components', [])]
        except Exception:
            pass
        self._refresh_theme_dropdown()
        idx = self._combo_theme.findData(self._current_theme_name)
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)
        self._update_color_buttons()
        self._emit_preview()

    # ── Color editing ────────────────────────────────────────────────

    def _on_color_clicked(self, key: string) -> void:
        hex_ = self._current_colors.get(key, '#808080')
        initial = QColor(hex_)
        label_id = self._color_label_ids.get(key, '')
        title = _(label_id) if label_id else ''
        color = QColorDialog.getColor(initial, self, title)
        if color.isValid():
            self._current_colors[key] = color.name()
            self._update_color_buttons()
            self._emit_preview()

    def _on_palette_clicked(self, row: int, col: int) -> void:
        if row >= len(self._current_palette) or col >= len(self._current_palette[row]):
            return
        hex_ = self._current_palette[row][col]
        initial = QColor(hex_)
        color = QColorDialog.getColor(initial, self, _('ui.prefs.palette.edit'))
        if color.isValid():
            self._current_palette[row][col] = color.name()
            self._update_color_buttons()
            self._emit_preview()

    def _emit_preview(self) -> void:
        self.settings_changed.emit({
            'theme': self._current_theme_name,
            'theme_colors': dict(self._current_colors),
            'theme_palette': [list(row) for row in self._current_palette],
        })

    # ── Accept / Apply ───────────────────────────────────────────────

    def _on_category_changed(self, row: int) -> void:
        if 0 <= row < self._stack.count():
            self._stack.setCurrentIndex(row)

    def _collect_changes(self) -> IDictionary[string, Any]:
        return {
            'theme': self._current_theme_name,
            'language': self._combo_lang.currentData(),
            'font_size': self._spin_font.value(),
            'completion_list_width': self._spin_comp_list.value(),
            'completion_detail_width': self._spin_comp_detail.value(),
            'completion_max_height': self._spin_comp_height.value(),
            'theme_colors': dict(self._current_colors),
            'theme_palette': [list(row) for row in self._current_palette],
        }

    def _on_accept(self) -> void:
        changes = self._collect_changes()
        self.settings_changed.emit(changes)
        self.accept()

    def _on_apply(self) -> void:
        changes = self._collect_changes()
        self.settings_changed.emit(changes)
