# -*- coding:utf-8 -*-

import enum
from pathlib import Path

from alias import *
from core.build import BuildConfig, Builder
from core.checker import Checker
from core.completer import Completer, Completion
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
    # Completer classes contributed by kits (see ``core.completer``); the editors
    # instantiate them against the loaded project to derive completion suggestions.
    # Class-level on purpose: kits register their completers at import time, which
    # may precede the application's Environment() (a bare call re-runs __init__),
    # and the re-initialization must not wipe the registrations
    _completers: ClassVar[IList[typeof[Completer]]] = []
    # Checker classes contributed by kits (see ``core.checker``); the editors consult
    # them for the immediate static checking and the compilation before emitting source.
    # Class-level for the same reason as ``_completers``
    _checkers: ClassVar[IList[typeof[Checker]]] = []
    # Static text snippets contributed by kits (keyword -> suggestion); the visual
    # code edits absorb them into their completion, confirming one inserts its text.
    # Class-level for the same reason as ``_completers``
    _snippets: ClassVar[IDictionary[string, Completion]] = {}

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
        # Shared registry (see ``_completers``): re-initialization rebinds it, never clears it
        self.completers = Environment._completers
        self.checkers = Environment._checkers
        self.snippets = Environment._snippets

    def register_completer(self, completer: typeof[Completer]) -> void:
        """
        Register a completer class so the editors consult it while completing.
        :param completer: completer class to register (instantiated per project)
        """
        if completer not in self.completers:
            self.completers.append(completer)

    def register_checker(self, checker: typeof[Checker]) -> void:
        """
        Register a checker class so the editors and the compilation consult it
        while validating identifiers and free source text.
        :param checker: checker class to register (instantiated per project)
        """
        if checker not in self.checkers:
            self.checkers.append(checker)

    def register_snippet(self, snippet: Completion) -> void:
        """
        Register a static text snippet the kits contribute to the completion
        (e.g. a function-like macro call); the visual code edits absorb the
        registry automatically, so the registration may happen at any time
        relative to the edit construction. Re-registering a keyword replaces
        the snippet it maps to.
        :param snippet: the suggestion carrying the keyword and its text
        """
        self.snippets[snippet.keyword] = snippet

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

    def build(self, config: Nullable[BuildConfig] = null) -> tuple[IList[Path], IList[Builder.BuildWarning]]:
        """
        Build the loaded project: compile its scripts and write the products to files.
        :param config: building configuration; defaults to the project's target language
        :return: paths of the generated artifacts and the warnings the compilers
            raised along the way
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
