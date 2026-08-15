# -*- coding:utf-8 -*-

import enum
from pathlib import Path

from alias import *
from core.kit import Kit, KitManager
from core.localization import language
from core.meta import Version, SupportedLanguage
from core.project import Project
from core.theme import Theme


@final
class Environment:
    """
    The environment of the runtime and edition.
    """
    VERSION = Version(0, 1, 0x0_000_0001)
    # noinspection bad-assignment
    _instance: 'Environment' = null

    def __new__(cls) -> 'Environment':
        if cls._instance is null:
            cls._instance = super(Environment, cls).__new__(cls)
        return cls._instance

    @classmethod
    def instance(cls) -> 'Environment':
        # Do NOT call cls() when the instance already exists: __init__ would run
        # again and wipe the runtime state (kit manager, theme cache, rt store).
        if cls._instance is null:
            return cls()
        return cls._instance

    class SatisfactionError(enum.IntEnum):
        SATISFIED = 0
        KIT_VERSION_UNSATISFIED = 1
        LANGUAGE_UNSUPPORTED = 2

    def __init__(self):
        self.version = Environment.VERSION
        self.languages: IList[SupportedLanguage] = []
        self.project: Nullable['Project'] = null
        self.kit_manager = KitManager()
        self.local_language = language
        self.theme = Theme.from_resource('light.json')
        self.rt: IDictionary[string, Any] = {}

    def satisfy_kit_version(self, kit: Kit) -> bool:
        return kit.meta.satisfy_version(self.version)

    def satisfy(self, project: 'Project') -> SatisfactionError:
        """
        Check if the environment satisfies requirements of a project.
        """
        if project.required_kits and any(not self.satisfy_kit_version(kit) for kit in project.required_kits):
            return Environment.SatisfactionError.KIT_VERSION_UNSATISFIED
        if project.target_lang not in self.languages:
            return Environment.SatisfactionError.LANGUAGE_UNSUPPORTED
        return Environment.SatisfactionError.SATISFIED

    def import_kit(self, path: Path | string) -> Kit:
        """
        Import a kit from the specified path.
        :param path: path of the kit
        :return: the imported kit
        :raise KitManager.KitImportError: raise when exception occurred during importation
        """
        if isinstance(path, Path):
            path = str(path)
        return self.kit_manager.import_package_kit(path)

    def __repr__(self) -> string:
        return f'Environment<project {"loaded" if self.project is not null else "unloaded"} @ {self.version.major}.{self.version.minor}>'
