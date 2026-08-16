# -*- coding: utf-8 -*-

from pathlib import Path

from alias import *
from core.build import Compiler
from core.component import Component
from core.graphics import IComponentGraphics
from core.kit import KitManager


class Script:
    def __init__(self, tu: Component):
        if not tu.is_root():
            raise TypeError(f'Component {tu.meta.display_name} ({tu.meta.name}) does not act as a root')

        self.tu: Component = tu
        self.path: Nullable[Path] = null

    @property
    def name(self) -> string:
        """Basename of the script's build artifact: derived from the file path,
        falling back to ``main`` while the script is unsaved."""
        return self.path.stem if self.path is not null else 'main'

    def build(self, compiler: Compiler) -> void:
        """Compile the component tree of the script into the compiler's products."""
        self.tu.build(compiler)

    def __serialize__(self) -> IDictionary[string, Any]:
        # noinspection bad-argument-type
        return {
            'path': str(self.path) if self.path is not null else null,
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
        return script
