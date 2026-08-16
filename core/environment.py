# -*- coding:utf-8 -*-

import enum
from pathlib import Path

from alias import *
from core.build import BuildConfig
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
        # Do NOT call KitManager() here: when the singleton already exists (e.g.
        # created while a kit module was imported), __init__ would run again and
        # wipe the registered kits and completions (same convention as instance)
        self.kit_manager = KitManager.instance()
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
        kit = self.kit_manager.import_package_kit(path)
        # The languages a kit declares become available in this environment
        for lang in kit.meta.languages:
            if lang not in self.languages:
                self.languages.append(lang)
        return kit

    def build(self, config: Nullable[BuildConfig] = null) -> IList[Path]:
        """
        Build the loaded project: compile its scripts and write the products to files.
        :param config: building configuration; defaults to the project's target language
        :return: paths of the generated artifacts
        :raise ValueError: raise when no project is loaded
        """
        if self.project is null:
            raise ValueError('Cannot build: no project is loaded in the environment')
        project = self.project
        if config is null:
            config = BuildConfig(project.target_lang)
        return project.build_project(config)

    def __repr__(self) -> string:
        return f'Environment<project {"loaded" if self.project is not null else "unloaded"} @ {self.version.major}.{self.version.minor}>'
