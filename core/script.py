# -*- coding: utf-8 -*-

import json
from pathlib import Path

from alias import *
from core.build import Compiler
from core.component import Component
from core.graphics import IComponentGraphics
from core.kit import KitManager


class Script:
    # Canonical extension of standalone script files written by ``save``
    Extension: Final[string] = '.ecscript'

    def __init__(self, tu: Component):
        if not tu.is_root():
            raise TypeError(f'Component {tu.meta.display_name} ({tu.meta.name}) does not act as a root')

        self.tu: Component = tu
        self.path: Nullable[Path] = null
        # Explicit name shown on tabs and palettes; ``null`` falls back to the
        # file stem (or 'untitled' while unsaved), see ``display_name``
        self._display_name: Nullable[string] = null
        # Scripts added without a user-given name stay untitled until someone
        # names them (the UI prompts for a name before saving); never persisted,
        # because saving forces a name first
        self.untitled: bool = False
        self._dirty: bool = False

    @property
    def name(self) -> string:
        """Basename of the script's build artifact: derived from the file path,
        falling back to ``main`` while the script is unsaved."""
        return self.path.stem if self.path is not null else 'main'

    @property
    def display_name(self) -> string:
        """Name shown by the UI (tabs, palette): the explicit display name first,
        then the file stem, falling back to 'untitled' while the script is unsaved."""
        if self._display_name is not null and self._display_name.strip():
            return self._display_name
        return self.path.stem if self.path is not null else 'untitled'

    @display_name.setter
    def display_name(self, value: Nullable[string]) -> void:
        self._display_name = value
        if value is not null and value.strip():
            # Giving a real name settles the script: it stops being untitled
            self.untitled = False

    @property
    def is_dirty(self) -> bool:
        """Whether the script changed since it was last saved."""
        return self._dirty

    def mark_dirty(self) -> void:
        """Record that the script content changed (called by the editing UI)."""
        self._dirty = True

    def clear_dirty(self) -> void:
        """Reset the dirty state after the script was persisted."""
        self._dirty = False

    def build(self, compiler: Compiler) -> void:
        """Compile the component tree of the script into the compiler's products."""
        self.tu.build(compiler)

    def save(self, path: string | Path) -> void:
        """
        Write the script to a standalone ``.ecscript`` file on disk.
        Bridges ``__serialize__`` to the file system; the persisted script
        remembers the path it was written to and starts clean.
        :param path: target file path of the script file
        :except OSError: raise when the file cannot be written
        """
        path = Path(path)
        with path.open('w', encoding='utf-8') as file:
            json.dump(serialize(self), file, ensure_ascii=False, indent=4)
        self.path = path
        self.clear_dirty()

    def __serialize__(self) -> IDictionary[string, Any]:
        # noinspection bad-argument-type
        return {
            'path': str(self.path) if self.path is not null else null,
            # Optional: absent in archives made before display names existed
            'display_name': self._display_name,
            # The component archive carries its complete name, because restoring
            # it requires resolving the component type through the kit manager
            'component': {
                'name': KitManager.instance().full_name(self.tu),
                'data': serialize(self.tu),
            },
        }

    @classmethod
    def restore(cls, data: IDictionary[string, Any], kit_manager: KitManager,
                graphics: IComponentGraphics) -> Self:
        """
        Restore a script from its serialization.
        Counterpart of ``__serialize__``; the component tree is reconstructed through
        ``Component.restore`` with the UI context (graphics) it requires.
        :param data: serialization produced by ``__serialize__``
        :param kit_manager: kit manager used to resolve the component type
        :param graphics: graphics interface of the canvas the script is restored on
        :return: the restored script
        """
        require_member(data, 'path', 'component')
        component = data['component']
        require_member(component, 'name', 'data')
        meta = kit_manager.lookup(component['name'])
        script = cls(meta.component_type.restore(component['data'], null, graphics))
        script.path = Path(data['path']) if data['path'] is not null else null
        # 'display_name' is absent in archives made before display names existed
        display_name = data.get('display_name')
        if display_name is not null:
            require_type(display_name, string)
        script._display_name = display_name
        return script
