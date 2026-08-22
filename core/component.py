# -*- coding: utf-8 -*-

import enum
from dataclasses import dataclass

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

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
            self.data[lang].append(delegation)

        def valid(self, lang: SupportedLanguage, /) -> 'DelegationValidation':
            """
            Check if the delegation is valid for the specified language
            """
            if lang not in self.data:
                return self.NOT_FOUND
            matches = [delegation for delegation in self.data[lang]
                       if lang in delegation.delegated().languages]
            if len(matches) == 1:
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

    class Level(enum.IntEnum):
        """
        Predefined levels of a component.

        The level orders components by the contexts they may appear in: a context of
        a given level accepts the components whose level is less than or equal to it
        (see ``VisualCodeEdit.filter``). Custom levels are allowed as well: any ``int``
        between (or beyond) the predefined ones; the predefined values are spaced
        out so that there is always room in between.
        """
        Zero = 0
        Expression = 100
        Statement = 200
        Domain = 300

    class Kind(enum.Enum):
        """
        Symbol kind of a component, classifying how it is presented in the code
        completion (see ``VisualCodeEdit``): the kind selects the glyph shown in
        front of the completion entry.

        - ``Builtin``: language constructs (control flow, operators, ...); they
          show **no** glyph.
        - ``Macro``: ``DEFINE_*``-style macro components; they carry the
          ``cpl_macro`` icon.
        - ``Variable``: analyzer-derived variables; they carry the ``cpl_var``
          icon. Components are never of this kind themselves; it is used by
          completers (see ``core.completer``) for derived suggestions.
        - ``Function``: callable API entries (traversal loops, vector/reduction
          helpers, ``Lookup_Thread``...); they carry the ``cpl_func`` icon.
        - ``Type``: data access entries (field reads, geometry info,
          dimensionality parameters); they carry the ``cpl_type`` icon.
        - ``Parameter``: solver state parameters (``CURRENT_TIME``,
          ``THREAD_ID``...); they carry the ``cpl_param`` icon.
        """
        Builtin = 'builtin'
        Macro = 'macro'
        Variable = 'variable'
        Function = 'function'
        Type = 'type'
        Parameter = 'parameter'

    name: string
    display_name: string
    description: string
    component_type: typeof['Component']
    languages: IList[SupportedLanguage]
    delegations: Delegation
    # Level of the contexts the component may appear in (any int, see ``Level``);
    level: int
    # Symbol kind driving the completion glyph (see ``Kind``); defaults to builtin
    kind: Kind = Kind.Builtin

    @staticmethod
    def create(name: string, display_name: string, description: string, languages: IList[SupportedLanguage],
               level: int = Level.Zero, kind: 'ComponentMetadata.Kind' = Kind.Builtin) -> Callable[[T], T]:
        def decorator(cls: T) -> T:
            if hasattr(cls, 'meta') and not getattr(cls.meta, '__isabstractmethod__', False):
                raise TypeError(f'Component "{cls}" already has metadata')
            meta = ComponentMetadata(name=name, display_name=display_name, description=description,
                                     component_type=cls,
                                     languages=languages, delegations=ComponentMetadata.Delegation(),
                                     level=level, kind=kind)
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

    Serialization convention: ``__serialize__`` produces a pure-data archive (no UI
    context), while ``restore`` reconstructs a component from that archive together
    with the same UI context the constructor requires (parent and graphics).
    Components are therefore **not** restorable through the context-free, generic
    ``__deserialize__``/``deserialize`` protocol.
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

    def autoFocusWidget(self) -> Nullable[QWidget]:
        """
        :return: the widget that should receive the focus right after this component
            is inserted into an editor (usually its first required field); null keeps
            the text cursor right after the inserted component

        Components with input fields should override this method.
        """
        return null

    def editableWidgets(self) -> IList[QWidget]:
        """
        :return: the editable widgets of this component in navigation order, used by
            the editors for Left/Right arrow navigation: pressing Right at the end of
            one widget moves the focus to the next one (escaping behind the component
            when there is none), and pressing Left at the beginning moves it to the
            previous one (escaping before the component when there is none)

        Components with input fields should override this method.
        """
        return []

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
    def restore(cls: typeof[ComponentTy], data: Any, parent: Nullable['Component'],
                graphics: 'IComponentGraphics') -> ComponentTy:
        """
        Restore a component from its serialization.
        :param data: archive produced by ``__serialize__``
        :param parent: logical parent of the restored component (null for a root)
        :param graphics: graphics interface of the canvas the component is restored on

        The context parameters mirror the constructor: constructing a component
        requires a UI context that a pure-data archive cannot contain.
        """
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
                meta.delegations.delegated(lang).compile(self, builder)
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

    def __init__(self, km, parent: Nullable[Component], graphics: IComponentGraphics):
        languages, name = self.delegated()  # type: tuple[SupportedLanguage], string
        self._meta: ComponentMetadata = km.lookup(name)
        self.component: Component = self._meta.component_type(parent, graphics)

    def interface(self) -> IComponentInterface:
        return self.component.interface

    def is_root(self) -> bool:
        return self.component.is_root()

    @classmethod
    def compile(cls, component: Component, builder: Compiler) -> void:
        """
        Compile the delegated component in the languages this delegation supports.
        :param component: instance of the delegated component being built
        :param builder: the compiler context
        :raise Compiler.CompilationError: raise when errors occur during compilation
        :raise Compiler.CompilationWarning: raise when warnings are made during compilation
        """
        raise NotImplementedError
