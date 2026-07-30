# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import IntEnum
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from alias import *
from core.component import Component, ComponentMetadata, ComponentDelegation, ComponentTy
from core.meta import Version, SupportedLanguage, AuthorInfo


@final
@dataclass
class KitMetadata:
    """
    Metadata of a kit.
    """
    name: string
    display_name: string
    description: string
    version: Version
    languages: IList[SupportedLanguage]
    require_lowest: Nullable[Version]
    require_highest: Nullable[Version]
    dependencies: IList[string]  # Names of dependent kits
    authors: IList[AuthorInfo]
    external_supports: IList[SupportedLanguage]  # Languages that are supported by other kits

    def satisfy_version(self, env_version: Version) -> bool:
        return Version.satisfy(env_version, self.require_lowest, self.require_highest)

    def __repr__(self) -> string:
        return f'KitMetadata<{self.display_name} ({self.name}) @ {self.version.major}.{self.version.minor}>'


@final
class Kit:
    """
    A kit of components.
    """

    class ComponentNotFoundError(LookupError):
        def __init__(self, kit_name: string, component_name: string):
            self.kit_name = kit_name
            self.component_name = component_name

        def __str__(self) -> string:
            return f'No such component in kit {self.kit_name}: {self.component_name}'

    class ComponentExistsError(Exception):
        def __init__(self, kit_name: string, component_name: string):
            self.kit_name = kit_name
            self.component_name = component_name

        def __str__(self) -> string:
            return f'Component already registered: {self.kit_name}.{self.component_name}'

    def __init__(self, module_key: string, meta: KitMetadata, components: IEnumerable[ComponentMetadata]):
        self.module_key = module_key
        self.meta = meta
        self.components: IDictionary[string, ComponentMetadata] = {}
        self.delegation_buffer: IList[typeof[ComponentDelegation]] = []

        for comp in components:
            self.components[comp.name] = comp

    def __getitem__(self, item: string) -> ComponentMetadata:
        if not KitManager.is_valid_segment_name(item):
            raise KitManager.InvalidComponentNameError(f'Invalid component name: "{item}"')

        if item in self.components:
            return self.components[item]
        else:
            raise Kit.ComponentNotFoundError(self.meta.name, item)

    def __contains__(self, item: string) -> bool:
        return item in self.components

    def __iter__(self) -> IEnumerator[ComponentMetadata]:
        return iter(self.components.values())

    def __len__(self) -> int:
        return len(self.components)

    @overload
    def register(self, component: ComponentMetadata, /) -> void:
        """
        Register a component to a kit.
        :param component: component to register
        :except Kit.ComponentExistsError: raise when the component is already registered
        """
        ...

    @overload
    def register(self, component: typeof[Component], /) -> typeof[Component]:
        """
        Register a component to a kit.
        :param component: component type to register
        :return: the component type itself
        :except Kit.ComponentExistsError: raise when the component is already registered
        """
        ...

    @overload
    def register(self, delegation: typeof[ComponentDelegation[ComponentTy]], /) -> void:
        """
        Register a component delegation to a kit, store it in the buffer and waiting for flushing.
        :param delegation: delegation to store
        """
        ...

    def register(self, component: ComponentMetadata | typeof[Component] | typeof[ComponentDelegation[ComponentTy]], /) -> void | typeof[Component]:
        if isinstance(component, ComponentMetadata):
            if component.name in self.components:
                raise Kit.ComponentExistsError(self.meta.name, component.name)
            self.components[component.name] = component
            return None
        else:  # type: typeof[ComponentDelegation[ComponentTy]]
            # noinspection bad-argument-type
            if issubclass(component, ComponentDelegation):
                self.delegation_buffer.append(component)
                return None
            elif issubclass(component, Component):
                self.register(component.meta())
                return component
            else:
                raise TypeError(f'{component.__name__} is not a component')

    # noinspection variance
    def __call__(self, component_type: T) -> T:
        """
        Register a component to a kit by its class.
        :param component_type: class of the component to register
        :return: the class itself

        This enables the kit to be used as a decorator.
        """
        if not isinstance(component_type, type):
            raise TypeError(f'{component_type} is not a type')
        if not issubclass(component_type, Component):
            raise TypeError(f'{component_type.__name__} is not a component')
        # pyrefly: ignore [missing-attribute]
        meta: ComponentMetadata = component_type.meta()
        if not isinstance(meta, ComponentMetadata):
            raise TypeError(f'{component_type.__name__} does not have meta-data')
        if meta.component_type is null:
            # pyrefly: ignore [bad-assignment]
            meta.component_type = component_type
        self.register(meta)
        return component_type

    def unregister(self, name: string) -> void:
        if name not in self.components:
            raise Kit.ComponentNotFoundError(self.meta.name, name)
        del self.components[name]

    @staticmethod
    def create_empty(meta: KitMetadata) -> 'Kit':
        """
        Create a kit that has no components using specified metadata.
        :param meta: metadata of the kit
        :return: a kit object that ``module_key`` field is null
        """
        return Kit(null, meta, [])  # type: ignore

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'name': self.meta.name,
            'display_name': self.meta.display_name,
            'description': self.meta.description,
            'version': serialize(self.meta.version),
            'require_lowest': serialize(self.meta.require_lowest) if self.meta.require_lowest is not None else null,
            'require_highest': serialize(self.meta.require_highest) if self.meta.require_highest is not None else null,
            'dependencies': self.meta.dependencies,
            'authors': [serialize(author) for author in self.meta.authors],
            'external_supports': [serialize(lang) for lang in self.meta.external_supports],
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Any]) -> IDictionary[string, Any]:
        require_member(data, 'name', 'display_name', 'description', 'version', 'require_lowest', 'require_highest',
                       'dependencies', 'authors', 'external_supports')
        name = data['name']
        require_type(name, string)
        display_name = data['display_name']
        require_type(display_name, string)
        description = data['description']
        require_type(description, string)
        version = deserialize(Version, data['version'])
        require_lowest = deserialize(Version, data['require_lowest'])
        require_highest = deserialize(Version, data['require_highest'])
        deps_ = data['dependencies']
        require_type(deps_, list)
        dependencies: IList[string] = []
        for n in deps_:
            require_type(n, string)
            dependencies.append(n)
        auth_ = data['authors']
        require_type(auth_, list)
        authors: IList[AuthorInfo] = []
        for author in auth_:
            authors.append(deserialize(AuthorInfo, author))
        ext_sup_ = data['external_supports']
        require_type(ext_sup_, list)
        external_supports: IList[SupportedLanguage] = []
        for lang in ext_sup_:
            external_supports.append(deserialize(SupportedLanguage, lang))

        return {
            'name': name,
            'display_name': display_name,
            'description': description,
            'version': version,
            'require_lowest': require_lowest,
            'require_highest': require_highest,
            'dependencies': dependencies,
            'authors': authors,
            'external_supports': external_supports,
        }

    def __repr__(self) -> string:
        return f'Kit<{self.meta.display_name} ({self.meta.name}) @ {self.meta.version.major}.{self.meta.version.minor}>'


@final
class KitManager:
    KitModuleId: ClassVar[int] = 1
    KitEntryName: Final[string] = 'kit_entry'  # kit_entry() -> Kit
    _instance = null

    def __new__(cls) -> Self:
        if cls._instance is null:
            cls._instance = super().__new__(cls)
        return cls._instance

    class KitNotFoundError(LookupError):
        def __init__(self, kit_name: string):
            self.kit_name = kit_name

        def __str__(self) -> string:
            return f'No such kit: {self.kit_name}'

    class KitExistsError(Exception):
        def __init__(self, kit_name: string):
            self.kit_name = kit_name

        def __str__(self) -> string:
            return f'Kit already exists: {self.kit_name}'

    def __init__(self):
        self._kits: IDictionary[string, Kit] = {}
        self.modules: IDictionary[string, ModuleType] = {}

    def __iter__(self) -> IEnumerator[Kit]:
        return iter(self._kits.values())

    def __contains__(self, name: string) -> bool:
        return name in self._kits

    def __getitem__(self, item: string) -> Kit:
        """
        Get a kit by name.
        :param item: the kit name
        :return: the kit
        :except KitManager.KitNotFoundError: raise when the kit is not registered
        """
        if item in self._kits:
            return self._kits[item]
        else:
            raise KitManager.KitNotFoundError(item)

    def register(self, kit: Kit) -> void:
        """
        Register a kit in the manager.
        :param kit: kit to register
        :except KitManager.KitExistsError: raise when the kit is already registered
        """
        if kit.meta.name in self._kits:
            raise KitManager.KitExistsError(kit.meta.name)
        self._kits[kit.meta.name] = kit

    def unregister(self, name: string) -> void:
        """
        Unregister a kit in the manager.
        :param name: name of the kit to unregister
        :except KitManager.KitNotFoundError: raise when the kit is not registered
        """
        if name not in self._kits:
            raise KitManager.KitNotFoundError(name)
        del self._kits[name]

    def __len__(self) -> int:
        return len(self._kits)

    class InvalidComponentNameError(Exception):
        pass

    @staticmethod
    def is_valid_segment_name(name: string) -> bool:
        """
        Check whether a string is a valid segment name.
        :param name: string to check
        :return: True if the string is a valid segment name, False otherwise
        """
        return name.isidentifier() and not name.isdigit()

    @staticmethod
    def split_name(name: string) -> tuple[string, string]:
        """
        Split a complete component name into kit name and component name.
        :param name: complete component name
        :return: a tuple of kit name and component name
        :except KitManager.InvalidComponentNameError: raise when name given is invalid
        """
        names = name.strip().split('.')
        if len(names) != 2:
            raise KitManager.InvalidComponentNameError(f'Invalid component name: "{name}"')
        if not KitManager.is_valid_segment_name(names[0]):
            raise KitManager.InvalidComponentNameError(f'Invalid kit name: "{names[0]}"')
        if not KitManager.is_valid_segment_name(names[1]):
            raise KitManager.InvalidComponentNameError(f'Invalid component name: "{names[1]}"')
        return names[0], names[1]

    @staticmethod
    def merge_names(kit_name: string, component_name: string) -> string:
        """
        Merge kit name and component into complete component name.
        :param kit_name: kit name
        :param component_name: component name
        :return: complete name of component
        :except KitManager.InvalidComponentNameError: raise when names given are invalid
        """
        if not KitManager.is_valid_segment_name(kit_name):
            raise KitManager.InvalidComponentNameError(f'Invalid kit name: "{kit_name}"')
        if not KitManager.is_valid_segment_name(component_name):
            raise KitManager.InvalidComponentNameError(f'Invalid component name: "{component_name}"')
        return f'{kit_name}.{component_name}'

    def lookup(self, name: string) -> ComponentMetadata:
        """
        Lookup a component by specified name.
        :param name: complete name of the component (in format 'kit.component')
        :return: component metadata
        :except KitManager.InvalidComponentNameError: raise when the name given is invalid
        :except KitManager.KitNotFoundError: raise when the kit is not registered
        :except Kit.ComponentNotFoundError: raise when the component is not found in the kit
        """
        kit_name, component_name = KitManager.split_name(name)
        return self[kit_name][component_name]

    def _resolve_delegation(self, delegation: typeof[ComponentDelegation[ComponentTy]]) -> void:
        """
        Resolve a component delegation and register it to its target component.
        :param delegation: type of the delegation
        """
        languages, name = delegation.delegated()  # type: tuple[SupportedLanguage], string
        # pyrefly: ignore [bad-argument-type]
        comp: ComponentMetadata = self.lookup(name)
        for lang in languages:
            # pyrefly: ignore [bad-argument-type]
            comp.delegations.append(lang, delegation)

    def flush_delegations(self) -> void:
        """
        Flush all unresolved delegations and register them to their target components.

        Prior to flushing, delegations are invisible in building, etc.
        """
        for kit in self._kits.values():
            for delegation in kit.delegation_buffer:
                self._resolve_delegation(delegation)
            kit.delegation_buffer.clear()


    @overload
    def create_component(self, parent: Nullable[Component], name: string, /) -> Component:
        """
        Create a component by name.
        :param parent: the parent component
        :param name: complete name of the component
        :return: the component object
        """
        ...

    @overload
    def create_component(self, parent: Nullable[Component], meta: ComponentMetadata, /) -> Component:
        """
        Create a component by metadata.
        :param parent: the parent component
        :param meta: metadata of the component
        :return: the component object
        """
        ...

    def create_component(self, parent: Nullable[Component], name_or_meta: string | ComponentMetadata, /) -> Component:
        if isinstance(name_or_meta, string):
            meta = self.lookup(name_or_meta)
        else:
            meta = name_or_meta
        # noinspection unresolved-references
        component = meta.component_type(parent)
        return component

    class KitInternalError(Exception):
        pass

    class KitImportError(KitInternalError):
        EC_FileTypeError = 0x100    # Caused by incorrect path or file types
        EC_KitMetaError = 0x200     # Error during acquisition or verification of metadata
        EC_InternalError = 0x500    # Caused by kit internal code

        class ErrorCode(IntEnum):
            PathInvalid = 1                 # Specified path is invalid (according to the OS)
            PathIsNotFile = 2               # Specified path is not a file
            PathIsNotDirectory = 3          # Specified path is not a directory
            PathNotFound = 4                # Specified path does not exist
            PathCannotOpen = 5              # Cannot open the files
            KitImported = 6                 # Kit has been imported
            PathIsNotPackage = 0x101        # Specified path is not a Python package
            PathIsNotModule = 0x102         # Specified path is not a Python module
            PackageMissingInit = 0x103      # Python package is missing an __init__.py
            KitMissingEntryClass = 0x201    # Kit has no specified entry
            KitVersionTooHigh = 0x202       # Kit version is too high (need newer platform)
            KitVersionTooLow = 0x203        # Kit version is too low (need newer kit)
            KitMissingMetaField = 0x204     # Missing critical meta-data field
            KitMetaInvalid = 0x205          # Meta-data or entry is invalid
            KitRuntimeError = 0x501         # Runtime error is raised by kit internal code
            UnresolvedError = 0             # Other unresolved errors

        def __init__(self, code: ErrorCode, kit_name: Nullable[string], msg: string, exc: Nullable[Exception] = null):
            self.error_code: KitManager.KitImportError.ErrorCode = code
            self.kit_name: Nullable[string] = kit_name
            self.message: string = msg
            self.exception: Nullable[Exception] = exc

    def import_package_kit(self, package_path: string) -> Kit:
        """
        Import a kit from a Python package.
        :param package_path: path to the package directory
        :return: kit imported
        :raise KitManager.KitImportError: raise when exception occurred during importation
        """
        # Resolve path
        try:
            path = Path(package_path).resolve()
        except OSError:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.PathInvalid, null, f'Invalid path: "{package_path}"')
        if not path.exists():
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.PathNotFound, null, f'Path not found: {path}')
        if not path.is_dir():
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.PathIsNotDirectory, null, f'Path is not a directory: {path}')
        init_path = path / '__init__.py'
        if not init_path.exists() or not init_path.is_file():
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.PackageMissingInit, null, f'Package missing __init__.py: {path}')

        # Load the module spec
        spec = importlib.util.spec_from_file_location(module_name := f'kit_{KitManager.KitModuleId}', init_path)
        KitManager.KitModuleId += 1
        if spec is null or spec.loader is null:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.PathIsNotPackage, null, f'Path is not a package: {path}')
        module: ModuleType = importlib.util.module_from_spec(spec)

        # Execute and load the module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitRuntimeError, null, f'Kit runtime error: {e}', e)
        sys.modules[module_name] = module
        self.modules[module_name] = module

        # Extract kit entry and get entry instance
        kit_entry: Nullable[Callable[..., Kit]] = getattr(module, KitManager.KitEntryName, null)
        if kit_entry is null:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitMissingEntryClass, null, f'Kit missing entry class: {module_name}')
        if not callable(kit_entry):
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitMetaInvalid, null, f'Kit entry is not callable: {module_name}')
        try:
            kit = NotNull(kit_entry)()
        except Exception as e:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitRuntimeError, null, f'Kit runtime error: {e}', e)
        if not isinstance(kit, Kit):
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitMetaInvalid, null, f'Kit entry does not return a kit: {module_name}')

        try:
            meta = kit.meta
        except Exception as e:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitMetaInvalid, null, f'Kit meta-data is invalid: {module_name}', e)
        if not isinstance(meta, KitMetadata):
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitMetaInvalid, null, f'Kit meta-data is invalid: {module_name}')

        if (name := meta.name) in self:
            raise KitManager.KitImportError(KitManager.KitImportError.ErrorCode.KitImported, name, f'Kit has been imported: {name}')

        self.register(kit)
        kit.module_key = module_name
        return kit

    def __repr__(self) -> string:
        return f'KitManager<of {len(self)} kits>'
