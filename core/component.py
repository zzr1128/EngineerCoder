# -*- coding: utf-8 -*-

from dataclasses import dataclass

from PySide6.QtCore import QPointF

from alias import *
from alias import IList
from core.build import Compiler
from core.graphics import IComponentGraphics
from core.meta import SupportedLanguage


class IComponentInterface(abstract):
    """
    Interface that all components should implement for UI.
    """

    def __init__(self, graphics: IComponentGraphics):
        maybe_unused(graphics)
        # UI origin of the interface, in absolute coordinates of the graphics canvas.
        # Implementations should push it as anchor at the beginning of ``paint``
        # and pop it before returning, so that figures are located correctly.
        self.origin: QPointF = QPointF()

    @pure_virtual
    def paint(self, graphics: IComponentGraphics, painting: bool = True) -> void:  # To be overridden
        raise NotImplementedError


@final
@dataclass
class ComponentMetadata:
    """
    Metadata of a component.
    """
    class Delegation:
        """
        Delegation of a component.

        ``Delegation`` is a class that stores all delegating implementations for a component. **Delegating implementation**
        is 'like a component', shares the same interface with the delegated component, but supports languages the
        original one does not.
        When accessing implementation for a specified language, if the component primitively supports, use it; otherwise
        search for delegating implementations. If there is one, use it; otherwise raise an error.
        """
        DelegationValidation = NewType('DelegationValidation', int)

        VALID = DelegationValidation(0)
        NOT_FOUND = DelegationValidation(1)
        CONFLICT = DelegationValidation(2)

        def __init__(self):
            self.data: IDictionary[SupportedLanguage, IList[typeof['ComponentDelegation']]] = {}

        def append(self, lang: SupportedLanguage, delegation: typeof['ComponentDelegation'], /) -> void:
            if lang not in self.data:
                self.data[lang] = []
            else:
                self.data[lang].append(delegation)

        def valid(self, lang: SupportedLanguage, /) -> 'DelegationValidation':
            """
            Check if the delegation is valid for the specified language
            """
            if lang not in self.data:
                return self.NOT_FOUND
            for delegation in self.data[lang]:
                if delegation.delegated().languages == lang:
                    return self.VALID
            return self.CONFLICT

        def delegated(self, lang: SupportedLanguage, /) -> typeof['ComponentDelegation']:
            """
            :param lang: a language
            :return: the component delegation that supports the specified language
            """
            # pyrefly: ignore [bad-assignment]
            ds = self.data.get(lang, null)
            assert ds is not null, f'Delegation not found for {lang.name}'
            ds: IList[typeof[ComponentDelegation]]
            assert len(ds) == 1, f'{len(ds)} delegations conflict for {lang.name}'
            return ds[0]

        def __contains__(self, item) -> bool:
            return item in self.data

    name: string
    display_name: string
    description: string
    component_type: typeof['Component']
    languages: IList[SupportedLanguage]
    delegations: Delegation

    @staticmethod
    def create(name: string, display_name: string, description: string, languages: IList[SupportedLanguage]) -> Callable[[T], T]:
        def decorator(cls: T) -> T:
            if hasattr(cls, 'meta') and not getattr(cls.meta, '__isabstractmethod__', False):
                raise TypeError(f'Component "{cls}" already has metadata')
            meta = ComponentMetadata(name=name, display_name=display_name, description=description,
                                     component_type=cls,
                                     languages=languages, delegations=ComponentMetadata.Delegation())
            setattr(cls, '_meta', meta)
            return Component.use__meta(cls)
        return decorator

    def support_language(self, lang: SupportedLanguage) -> bool:
        return lang in self.languages or lang in self.delegations


ComponentTy = TypeVar('ComponentTy', bound='Component')


class Component:
    """
    The abstract super class of all components.
    All non-abstract implementation component should derive from the class.
    """

    def __new__(cls, *args, **kwargs):
        if cls.meta() is null:
            raise TypeError("Component cannot be instantiated missing metadata")
        return super(Component, cls).__new__(cls)

    def __init__(self, parent: Nullable['Component'], graphics: 'IComponentGraphics'):
        self.parent = parent

    def is_root(self) -> bool:
        return self.parent is null

    @property
    @pure_virtual
    def interface(self) -> IComponentInterface:
        raise NotImplementedError

    @classmethod
    @pure_virtual
    def meta(cls) -> ComponentMetadata:
        raise NotImplementedError

    @staticmethod
    def use__interface(cls: T) -> T:
        """
        A decorator that uses ``_interface`` feature to implement ``interface`` property.
        """
        if 'interface' not in cls.__dict__:  # No override for 'interface' in the wrapped class
            setattr(cls, 'interface', property(lambda self: self._interface))
        return cls

    @classmethod
    def impl_use__meta(cls):
        return cls._meta  # type: ignore

    @staticmethod
    def use__meta(cls: T) -> T:
        """
        A decorator that uses ``_meta`` feature to implement ``meta`` class method.
        """
        if 'meta' not in cls.__dict__:  # No override for 'meta' in the wrapped class
            setattr(cls, 'meta', cls.impl_use__meta)
        return cls

    @pure_virtual
    def __serialize__(self) -> Any:
        raise NotImplementedError

    @classmethod
    @pure_virtual
    def __deserialize__(cls, data: Any) -> Self:
        raise NotImplementedError

    @pure_virtual
    def compile(self, builder: Compiler) -> void:
        raise NotImplementedError

    def build(self, builder: Compiler) -> void:
        """
        Build a component in the specified language
        :param builder: the compiler object

        If the component has support to the target language, it will be applied;
        otherwise, search for other components for delegations.
        """
        if (lang := builder.config.target_lang) in (meta := self.meta()).languages:
            self.compile(builder)
            return

        match meta.delegations.valid(lang):
            case ComponentMetadata.Delegation.VALID:
                meta.delegations.delegated(lang).compile(builder)
                return
            case ComponentMetadata.Delegation.NOT_FOUND:
                raise Compiler.BuildError(
                    Compiler.B1004,
                    lang.name, meta.name,
                )
            case ComponentMetadata.Delegation.CONFLICT:
                raise Compiler.BuildError(
                    Compiler.B1005,
                    lang.name, meta.name,
                )

        unreachable()


class ComponentDelegation(Generic[T]):
    """
    A delegation of a component to another component.
    """

    @dataclass
    class DelegationTarget:
        languages: tuple[SupportedLanguage]
        component_name: string

        def __iter__(self) -> IEnumerator[tuple[SupportedLanguage] | string]:
            yield self.languages
            yield self.component_name

    @classmethod
    def delegated(cls) -> DelegationTarget:
        """
        :return: the languages and the name of delegated component
        """
        raise NotImplementedError

    def __init__(self, km, parent: Nullable[Component]):
        languages, name = self.delegated()  # type: tuple[SupportedLanguage], string
        self._meta: ComponentMetadata = km.lookup(name)
        self.component: Component = self._meta.component_type(parent)

    def interface(self) -> IComponentInterface:
        return self.component.interface()

    def is_root(self) -> bool:
        return self.component.is_root()

    @classmethod
    def compile(cls, builder: Compiler) -> void:
        """
        Compile the component.
        :param builder: the compiler context
        :raise Compiler.CompilationError: raise when errors occur during compilation
        :raise Compiler.CompilationWarning: raise when warnings are made during compilation
        """
        raise NotImplementedError
