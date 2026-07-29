# -*- coding: utf-8 -*-

from pathlib import Path

from alias import *
from component import Component


class Script:
    def __init__(self, tu: Component):
        if not tu.is_root():
            raise TypeError(f'Component {tu.meta.display_name} ({tu.meta.name}) does not act as a root')

        self.tu: Component = tu
        self.path: Nullable[Path] = null

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'path': str(self.path),
            'component': serialize(self.tu),
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Any]) -> Self:
        require_member(data, 'path', 'component')
        script = cls(deserialize(Component, data['component']))
        script.path = Path(data['path'])
        return script
