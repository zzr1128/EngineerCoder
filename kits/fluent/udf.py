# -*- coding: utf-8 -*-
"""
Delegating implementations of the Common Language Kit components for the Ansys
Fluent UDF language (a dialect of C).

CLK components are language-neutral: none of them primitively supports a concrete
language, so language support is supplied through delegations. This kit registers
one delegation per CLK component, teaching it to compile into UDF source.

Code generation reads the component's serialization archive (the same pure-data
contract persistence uses), so components embedded inside visual code edits are
compiled recursively without touching component internals. Rendered fragments of
top-level components are accumulated in ``builder.products[UDF.id]`` as a list of
source strings.
"""

from alias import *

from core.build import Compiler
from core.component import Component, ComponentDelegation, ComponentMetadata
from core.environment import Environment
from kits.fluent.fluent import UDF, fluent

Indent: Final[string] = '    '

# Identifiers occupied by the counters of count loops currently in scope, carried
# in the compiler's products: an enclosing loop occupies its counter while its body
# renders, so nested loops pick distinct names and siblings reuse freed ones
OccupiedKey: Final[string] = '_ec_counters'


def render_edit(data: IDictionary[string, Any], builder: Compiler) -> string:
    """
    Render the archive of a visual code edit into UDF source.
    :param data: serialization of the edit (text with ``\\uFFFC`` placeholders plus
        the serialized components in placeholder order)
    :param builder: the compiler context (carries the target language)
    :return: the rendered source fragment
    """
    require_member(data, 'text', 'components')
    segments = data['text'].split('\uFFFC')
    chunks: IList[string] = []
    for segment, serialized_component in zip(segments[:-1], data['components']):
        chunks.append(segment)
        require_member(serialized_component, 'name', 'data')
        chunks.append(render_component(serialized_component['name'], serialized_component['data'], builder))
    chunks.append(segments[-1])
    return ''.join(chunks)


def render_component(name: string, data: Any, builder: Compiler) -> string:
    """
    Render a serialized component into UDF source through its delegation.
    :param name: complete name of the component (in format 'kit.component')
    :param data: serialization produced by the component's ``__serialize__``
    :param builder: the compiler context (carries the target language)
    :return: the rendered source fragment
    :raise Compiler.BuildError: raise when no (or conflicting) delegation supports
        the target language

    Counterpart of ``Component.build`` for archives: nested components exist only as
    serializations, so native compilation (which needs the live component) is out of
    reach and only delegations can serve them.
    """
    meta = Environment.instance().kit_manager.lookup(name)
    lang = builder.config.target_lang
    if lang in meta.languages:
        raise Compiler.BuildError(Compiler.B1004, lang.name, meta.name)

    match meta.delegations.valid(lang):
        case ComponentMetadata.Delegation.VALID:
            return meta.delegations.delegated(lang).render(data, builder)
        case ComponentMetadata.Delegation.NOT_FOUND:
            raise Compiler.BuildError(Compiler.B1004, lang.name, meta.name)
        case ComponentMetadata.Delegation.CONFLICT:
            raise Compiler.BuildError(Compiler.B1005, lang.name, meta.name)

    unreachable()


def render_unit(data: IDictionary[string, Any], builder: Compiler) -> string:
    """
    Render the archive of a translation-unit-level edit into UDF source.

    Like ``render_edit``, but a component that primitively supports the target
    language renders through its own archive-based ``render`` classmethod
    (mirroring ``ComponentDelegation.render``): delegations only serve
    components the language is foreign to (see ``render_component``), while
    unit-level components such as the ``DEFINE_*`` macros support it natively.
    :param data: serialization of the edit (text with ``\\uFFFC`` placeholders
        plus the serialized components in placeholder order)
    :param builder: the compiler context (carries the target language)
    :return: the rendered source fragment
    """
    require_member(data, 'text', 'components')
    lang = builder.config.target_lang
    kit_manager = Environment.instance().kit_manager
    segments = data['text'].split('\uFFFC')
    chunks: IList[string] = []
    for segment, serialized_component in zip(segments[:-1], data['components']):
        chunks.append(segment)
        require_member(serialized_component, 'name', 'data')
        meta = kit_manager.lookup(serialized_component['name'])
        if lang in meta.languages:
            # Native at unit level: the component type renders its own archive
            render = getattr(meta.component_type, 'render', null)
            if render is null:
                raise Compiler.BuildError(Compiler.B1004, lang.name, meta.name)
            chunks.append(render(serialized_component['data'], builder))
        else:
            chunks.append(render_component(serialized_component['name'], serialized_component['data'], builder))
    chunks.append(segments[-1])
    return ''.join(chunks)


def _indent(source: string, level: int = 1) -> string:
    """
    Indent every non-blank line of a source fragment.
    """
    prefix = Indent * level
    return '\n'.join(prefix + line if line.strip() else line for line in source.splitlines())


def _block(body: string) -> string:
    """
    Wrap statements in a C block; an empty body yields an empty block.
    """
    if not body.strip():
        return '{\n}'
    return '{\n' + _indent(body) + '\n}'


class UdfDelegation(ComponentDelegation[Component]):
    """
    Base of the UDF delegations.

    ``render`` turns the delegated component's serialization archive into UDF
    source; it is archive-based so that components nested inside visual code edits
    can be compiled recursively. ``compile`` adapts the delegation protocol to it
    and accumulates the rendered source in ``builder.products``.
    """

    @classmethod
    @pure_virtual
    def render(cls, data: Any, builder: Compiler) -> string:
        raise NotImplementedError

    @classmethod
    def compile(cls, component: Component, builder: Compiler) -> void:
        # noinspection bad-argument-type
        source = cls.render(serialize(component), builder)
        fragments: IList[string] = builder.products.setdefault(UDF.id, [])
        fragments.append(source)


@fluent.register
class UdfNative(UdfDelegation):
    """Native code is emitted verbatim: UDF accepts raw C."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.native')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        maybe_unused(builder)
        require_member(data, 'code')
        require_type(data['code'], string, 'code')
        return data['code']


@fluent.register
class UdfBranch(UdfDelegation):
    """Branch compiles into ``if (...) { ... } else { ... }``; the ``else`` part
    is omitted when it is empty."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.br')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        require_member(data, 'cond', 'then', 'else')
        cond = render_edit(data['cond'], builder).strip()
        then = render_edit(data['then'], builder)
        otherwise = render_edit(data['else'], builder)
        source = f'if ({cond}) {_block(then)}'
        if otherwise.strip():
            source += f' else {_block(otherwise)}'
        return source


@fluent.register
class UdfLoop(UdfDelegation):
    """Count-free loop compiles into ``while (...) { ... }``."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.loop')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        require_member(data, 'cond', 'body')
        cond = render_edit(data['cond'], builder).strip()
        body = render_edit(data['body'], builder)
        return f'while ({cond}) {_block(body)}'


@fluent.register
class UdfFor(UdfDelegation):
    """Count loop compiles into a ``for`` over a counter: an explicit counter name
    from the archive is used as is; otherwise the first available identifier is
    occupied (see ``counter_name``)."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.for')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        # Deferred import: loading kits.common.loop at module level would import the
        # whole common kit ahead of this one, breaking the kit importation order
        from kits.common.loop import counter_name
        require_member(data, 'count', 'body')
        count = render_edit(data['count'], builder).strip()
        occupied: HashSet[string] = builder.products.setdefault(OccupiedKey, HashSet[string]())
        # 'counter' is absent in archives made before the counter field existed
        named: string = data.get('counter', '')
        require_type(named, string, 'counter')
        counter = named.strip()
        if not counter:
            counter = counter_name(occupied)
        # Occupy the counter while the body renders; release it afterwards unless an
        # enclosing scope had occupied the same name already (explicit duplicates)
        fresh = counter not in occupied
        occupied.add(counter)
        try:
            body = render_edit(data['body'], builder)
        finally:
            if fresh:
                occupied.discard(counter)
        return f'for (int {counter} = 0; {counter} < ({count}); ++{counter}) {_block(body)}'


@fluent.register
class UdfAssign(UdfDelegation):
    """Assignment compiles into ``name = value;``; checking ``constant`` declares
    the value as a ``const real`` instead (UDF uses ``real`` for floating point)."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.assign')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        require_member(data, 'name', 'value', 'constant')
        require_type(data['name'], string, 'name')
        require_type(data['constant'], bool, 'constant')
        value = render_edit(data['value'], builder).strip()
        if data['constant']:
            return f'const real {data["name"]} = {value};'
        return f'{data["name"]} = {value};'


class UdfOperator(UdfDelegation):
    """An arithmetic operator renders as its C symbol; it carries no fields."""

    symbol: ClassVar[string] = ''

    @classmethod
    def render(cls, data: Any, builder: Compiler) -> string:
        maybe_unused(data, builder)
        return cls.symbol


@fluent.register
class UdfPlus(UdfOperator):
    symbol = '+'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.plus')


@fluent.register
class UdfMinus(UdfOperator):
    symbol = '-'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.minus')


@fluent.register
class UdfMultiply(UdfOperator):
    symbol = '*'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.multiply')


@fluent.register
class UdfDivide(UdfOperator):
    symbol = '/'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.divide')


@fluent.register
class UdfModulus(UdfOperator):
    symbol = '%'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.modulus')


@fluent.register
class UdfField(UdfDelegation):
    """Member access compiles into ``owner.member``."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.field')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        maybe_unused(builder)
        require_member(data, 'owner', 'member')
        require_type(data['owner'], string, 'owner')
        require_type(data['member'], string, 'member')
        return f'{data["owner"].strip()}.{data["member"].strip()}'
