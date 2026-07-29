# -*- coding: utf-8 -*-

from alias import *
from core.kit import Kit
from core.meta import SupportedLanguage
from core.script import Script


@final
class Project:
    def __init__(self, name: string, lang: SupportedLanguage):
        self.name = name
        self.path: Nullable[string] = null
        self.required_kits: IList[Kit] = []
        self.target_lang: SupportedLanguage = lang
        self.scripts: IList[Script] = []

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'name': self.name,
            'required_kits': [serialize(kit) for kit in self.required_kits],
            'target_lang': serialize(self.target_lang),
            'scripts': [serialize(script) for script in self.scripts]
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Any]) -> Self:
        """
        **Attention**: Deserialized ``required_kits`` field is of type IList[string],
        and requires further ``Kit`` resolution.
        """
        if not isinstance(data, dict):
            raise SerializationError(f'Cannot deserialize {data} to Project: invalid type')
        require_member(data, 'name', 'required_kits', 'target_lang', 'scripts')
        name = data['name']
        require_type(name, string)
        lang = deserialize(SupportedLanguage, data['target_lang'])
        require_type(data['required_kits'], list)
        require_type(data['scripts'], list)
        proj = Project(name, lang)
        proj.scripts = [deserialize(Script, script) for script in data['scripts']]
        proj.required_kits = [kit for kit in data['required_kits']]
        return proj
