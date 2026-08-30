# -*- coding: utf-8 -*-

from PySide6.QtCore import *
from PySide6.QtWidgets import *

from alias import *
from core.kit import Kit, KitManager
from core.localization import _
from core.meta import SupportedLanguage


@final
class NewProjectDialog(QDialog):
    """Modal dialog for creating a new project: chooses the project name, the
    kits the project uses and the target language. Checking a kit also checks
    the kits it depends on, and a kit a checked one depends on refuses being
    unchecked (both behaviors publish a hint in the status line); the target
    language lists every language the checked kits support. ``project_name``,
    ``selected_kits`` and ``target_language`` publish the outcome once the
    dialog is accepted."""

    def __init__(self, kit_manager: KitManager, default_name: string,
                 parent: Nullable[QWidget] = null):
        super().__init__(parent)
        self._kit_manager = kit_manager
        # Programmatic check-state changes re-enter ``itemChanged``; the guard
        # keeps the dependency enforcement from chasing its own updates
        self._syncing = False
        self.setWindowTitle(_('ui.dialog.new_project_title'))
        self.setMinimumWidth(520)
        self._setup_ui(default_name)
        if self._kit_list.count() > 0:
            self._kit_list.setCurrentRow(0)
        self._refresh_languages()
        self._refresh_detail()
        self._refresh_ok()

    def _setup_ui(self, default_name: string) -> void:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._edit_name = QLineEdit(self)
        self._edit_name.setText(default_name)
        self._edit_name.textChanged.connect(self._refresh_ok)
        form.addRow(_('ui.newproj.name'), self._edit_name)

        self._combo_lang = QComboBox(self)
        form.addRow(_('ui.newproj.target_lang'), self._combo_lang)
        layout.addLayout(form)

        layout.addWidget(QLabel(_('ui.newproj.kits'), self))
        self._kit_list = QListWidget(self)
        self._kit_list.setMinimumHeight(160)
        for kit in self._kit_manager:
            item = QListWidgetItem(
                f'{kit.meta.display_name}  ({kit.meta.version.major}.{kit.meta.version.minor})',
                self._kit_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, kit)
            item.setCheckState(Qt.CheckState.Checked)  # Every imported kit starts selected
        self._kit_list.itemChanged.connect(self._on_kit_changed)
        self._kit_list.currentItemChanged.connect(lambda *_args: self._refresh_detail())
        layout.addWidget(self._kit_list)

        # Details of the highlighted kit: description, supported languages and
        # dependencies (the user reads them before deciding what to check)
        self._label_detail = QLabel(self)
        self._label_detail.setWordWrap(True)
        layout.addWidget(self._label_detail)

        # Dependency hints: automatic checking and refused unchecking
        self._label_status = QLabel(self)
        self._label_status.setWordWrap(True)
        layout.addWidget(self._label_status)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _item_of(self, name: string) -> Nullable[QListWidgetItem]:
        """The list item carrying the kit of the given name; null when absent."""
        for index in range(self._kit_list.count()):
            item = self._kit_list.item(index)
            kit = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(kit, Kit) and kit.meta.name == name:
                return item
        return null

    def _checked_kits(self) -> IList[Kit]:
        """The kits the user checked, in list order."""
        kits: IList[Kit] = []
        for index in range(self._kit_list.count()):
            item = self._kit_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                kit = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(kit, Kit):
                    kits.append(kit)
        return kits

    def _dependency_closure(self, name: string) -> IList[string]:
        """Every kit name the given kit transitively depends on (missing kits
        are skipped: only the imported ones can be checked in the list)."""
        closure: IList[string] = []
        stack: IList[string] = list(self._kit_manager[name].meta.dependencies) \
            if name in self._kit_manager else []
        while stack:
            dep = stack.pop()
            if dep in closure or dep not in self._kit_manager:
                continue
            closure.append(dep)
            stack.extend(self._kit_manager[dep].meta.dependencies)
        return closure

    def _on_kit_changed(self, item: QListWidgetItem) -> void:
        """Enforce the kit dependencies: checking a kit checks the kits it
        depends on too; unchecking a kit a checked one depends on is refused."""
        if self._syncing:
            return
        kit = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(kit, Kit):
            return
        self._syncing = True
        try:
            if item.checkState() == Qt.CheckState.Checked:
                # Pull the dependencies in with the kit (transitively)
                missing: IList[string] = []
                for name in self._dependency_closure(kit.meta.name):
                    dep_item = self._item_of(name)
                    if dep_item is not null and dep_item.checkState() != Qt.CheckState.Checked:
                        dep_item.setCheckState(Qt.CheckState.Checked)
                        missing.append(name)
                if missing:
                    self._label_status.setText(_('ui.newproj.dep_auto').format(
                        kit.meta.display_name,
                        ', '.join(self._kit_manager[name].meta.display_name for name in missing)))
                else:
                    self._label_status.setText('')
            else:
                # A checked dependant still needs the kit: refuse the unchecking
                dependants: IList[string] = []
                for other in self._checked_kits():
                    if other.meta.name != kit.meta.name \
                            and kit.meta.name in self._dependency_closure(other.meta.name):
                        dependants.append(other.meta.display_name)
                if dependants:
                    item.setCheckState(Qt.CheckState.Checked)
                    self._label_status.setText(_('ui.newproj.dep_required').format(
                        kit.meta.display_name, ', '.join(dependants)))
                else:
                    self._label_status.setText('')
        finally:
            self._syncing = False
        self._refresh_languages()
        self._refresh_ok()

    def _refresh_languages(self) -> void:
        """Refill the target language combo with the languages the checked kits
        support, keeping the previous selection when it survives."""
        current = self._combo_lang.currentData()
        current_id = current.id if isinstance(current, SupportedLanguage) else null
        self._combo_lang.clear()
        seen: IDictionary[string, SupportedLanguage] = {}
        for kit in self._checked_kits():
            for lang in kit.meta.languages:
                if lang.id not in seen:
                    seen[lang.id] = lang
        for lang in seen.values():
            self._combo_lang.addItem(lang.name, lang)
        restore = -1
        for index in range(self._combo_lang.count()):
            lang = self._combo_lang.itemData(index)
            if isinstance(lang, SupportedLanguage) and lang.id == current_id:
                restore = index
                break
        if restore < 0 and self._combo_lang.count() > 0:
            restore = 0
        if restore >= 0:
            self._combo_lang.setCurrentIndex(restore)

    def _refresh_detail(self) -> void:
        """Describe the highlighted kit: description, supported languages and
        dependencies."""
        item = self._kit_list.currentItem()
        kit = item.data(Qt.ItemDataRole.UserRole) if item is not null else null
        if not isinstance(kit, Kit):
            self._label_detail.setText('')
            return
        meta = kit.meta
        langs = ', '.join(lang.name for lang in meta.languages) \
            or _('ui.newproj.detail.none')
        deps = ', '.join(
            self._kit_manager[dep].meta.display_name if dep in self._kit_manager else dep
            for dep in meta.dependencies) or _('ui.newproj.detail.none')
        self._label_detail.setText(
            f'{meta.description}\n'
            f'{_("ui.newproj.detail.languages")}{langs}\n'
            f'{_("ui.newproj.detail.dependencies")}{deps}')

    def _refresh_ok(self) -> void:
        """Accepting needs a non-empty name and a target language (the checked
        kits must support at least one)."""
        ok = bool(self._edit_name.text().strip()) and self._combo_lang.count() > 0
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def project_name(self) -> string:
        """The chosen project name (stripped)."""
        return self._edit_name.text().strip()

    def selected_kits(self) -> IList[Kit]:
        """The kits the user checked, in list order."""
        return self._checked_kits()

    def target_language(self) -> SupportedLanguage:
        """The chosen target language (the combo always holds one when the
        dialog is accepted)."""
        lang = self._combo_lang.currentData()
        assert isinstance(lang, SupportedLanguage), 'no target language selected'
        return lang
