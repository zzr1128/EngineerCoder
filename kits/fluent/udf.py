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

Variables annotated ``auto`` (see ``kits.common.assign``) are declared once, at
the top of the smallest block shared by every definition and reference of the
name: ``analyze_scope`` pre-scans the translation-unit archive for such names
and records the declarations per block (``ScopeKey``), and the renderers of the
block-introducing edits emit them ahead of the block contents.
"""

import re

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

# Declarations lifted to block tops for ``auto`` variables (see ``analyze_scope``):
# maps the identity of a block-introducing edit archive to the declarations that
# must precede its contents; carried in the compiler's products
ScopeKey: Final[string] = '_ec_scope'

# Archive keys that open a fresh block scope; the other keys of a component
# archive (conditions, counts, values) stay in the enclosing scope
_BlockKeys: Final[frozenset[string]] = frozenset(('then', 'else', 'body'))

# Heuristic scalar declarations in free C text (``int counter = 0;``,
# ``real area;``...): qualifier tokens, a scalar type and a simple declarator,
# capturing the declared type (1) and name (2); detects externally defined variables
_Declaration: Final[re.Pattern] = re.compile(
    r'\b((?:(?:const|static|extern|unsigned|signed|volatile|struct)\s+)*'
    r'(?:int|real|float|double|char|bool|long|short|size_t)\s*\**)\s*'
    r'([A-Za-z_]\w*)\s*(?:=[^=]|\[|;|,)')


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
    # Declarations lifted to the unit root precede everything else
    return _hoist_prefix(builder, data) + ''.join(chunks)


def analyze_scope(unit_data: IDictionary[string, Any], builder: Compiler) -> void:
    """
    Pre-analyze a translation-unit archive for ``auto`` variables and record the
    declarations their renderers must lift (see ``ScopeKey``).

    An assignment annotated ``auto`` introduces a variable whose single ``real``
    declaration belongs at the top of the smallest block enclosing every
    definition and every reference of the name, so all uses compile against a
    declared identifier. The analysis identifies blocks by the identity of the
    edit archive that opens them, therefore it must run on the very archive the
    renderers consume (``render_unit``), and once per translation unit.

    Identifiers declared at the unit root (external C declarations in the free
    text) occupy the counter names of count loops as well, so auto-named loops
    never shadow them (see ``OccupiedKey``).
    :param unit_data: serialization of the translation-unit edit
    :param builder: the compiler context receiving the hoisted declarations
    """
    hoist: IDictionary[int, IList[string]] = {}
    builder.products[ScopeKey] = hoist
    occupied: HashSet[string] = builder.products.setdefault(OccupiedKey, HashSet[string]())

    definitions: IDictionary[string, IList[tuple[int, ...]]] = {}

    def collect_definition(name: string, data: Any, path: tuple[int, ...]) -> void:
        maybe_unused(path)
        if name != 'clk.assign' or not isinstance(data, dict) or data.get('constant'):
            return
        # The annotation evolved from a legacy ``visibility`` (``auto`` lifted the
        # declaration) to the ``local_only`` flag (its inversion lifts it)
        if 'local_only' in data:
            if data['local_only']:
                return
        elif data.get('visibility', 'local') != 'auto':
            return
        target = data.get('name', '')
        if isinstance(target, dict):
            # A target embedding components names no plain variable
            target = target.get('text', '') if not target.get('components') else ''
        if isinstance(target, string) and target.strip():
            definitions.setdefault(target.strip(), []).append(path)

    def seed_occupation(text: string, path: tuple[int, ...]) -> void:
        if path:
            return  # Declarations inside functions stay local to them
        for match in _Declaration.finditer(text):
            occupied.add(match.group(2))

    _walk_archive(unit_data, (), seed_occupation, collect_definition)
    if not definitions:
        return

    patterns = {name: re.compile(rf'\b{re.escape(name)}\b') for name in definitions}
    references: IDictionary[string, IList[tuple[int, ...]]] = {}

    def collect_reference(text: string, path: tuple[int, ...]) -> void:
        for name, pattern in patterns.items():
            if pattern.search(text):
                references.setdefault(name, []).append(path)

    def collect_component_reference(name: string, data: Any, path: tuple[int, ...]) -> void:
        # Native code and member accesses mention names as plain text too
        if name == 'clk.native' and isinstance(data, dict):
            code = data.get('code', '')
            if isinstance(code, string):
                collect_reference(code, path)
        elif name == 'clk.field' and isinstance(data, dict):
            for key in ('owner', 'member'):
                text = data.get(key, '')
                if isinstance(text, string):
                    collect_reference(text, path)

    _walk_archive(unit_data, (), collect_reference, collect_component_reference)

    for name, sites in definitions.items():
        paths = sites + references.get(name, [])
        common = _common_prefix(paths)
        # The innermost common block; the unit root when nothing deeper is shared
        block = common[-1] if common else id(unit_data)
        hoist.setdefault(block, []).append(f'real {name};')


def _hoist_prefix(builder: Compiler, edit_data: IDictionary[string, Any]) -> string:
    """
    :return: the declarations ``analyze_scope`` lifted to the top of the block
        a block-introducing edit archive opens (empty when none, or when no
        scope analysis ran on the enclosing translation unit)
    """
    hoist = builder.products.get(ScopeKey, {})
    declarations: IList[string] = hoist.get(id(edit_data), [])
    return ''.join(declaration + '\n' for declaration in declarations)


def _walk_archive(archive: IDictionary[string, Any], path: tuple[int, ...],
                  on_text: Callable[[string, tuple[int, ...]], Any],
                  on_component: Callable[[string, Any, tuple[int, ...]], Any]) -> void:
    """
    Traverse an edit archive depth-first, visiting every free-text segment and
    every serialized component.
    :param archive: serialization of an edit (text plus components)
    :param path: identities of the block-introducing archives enclosing this one
    :param on_text: called with each placeholder-free text segment and its path
    :param on_component: called with each component's name, data and path
    """
    require_member(archive, 'text', 'components')
    for segment in archive['text'].split('\uFFFC'):
        if segment:
            on_text(segment, path)
    for serialized_component in archive['components']:
        require_member(serialized_component, 'name', 'data')
        name, data = serialized_component['name'], serialized_component['data']
        on_component(name, data, path)
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and 'text' in value and 'components' in value:
                    sub = path + (id(value),) if key in _BlockKeys else path
                    _walk_archive(value, sub, on_text, on_component)


def _common_prefix(paths: IList[tuple[int, ...]]) -> tuple[int, ...]:
    """
    :return: the longest block chain shared by every path (the innermost common
        block scope); empty when the paths diverge right from the unit root
    """
    prefix: IList[int] = []
    for levels in zip(*paths):
        if any(level != levels[0] for level in levels[1:]):
            break
        prefix.append(levels[0])
    return tuple(prefix)


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
        then = _hoist_prefix(builder, data['then']) + render_edit(data['then'], builder)
        otherwise = _hoist_prefix(builder, data['else']) + render_edit(data['else'], builder)
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
        body = _hoist_prefix(builder, data['body']) + render_edit(data['body'], builder)
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
            body = _hoist_prefix(builder, data['body']) + render_edit(data['body'], builder)
        finally:
            if fresh:
                occupied.discard(counter)
        return f'for (int {counter} = 0; {counter} < ({count}); ++{counter}) {_block(body)}'


@fluent.register
class UdfAssign(UdfDelegation):
    """Assignment compiles into ``name = value;``; checking ``constant`` declares
    the value as a ``const real`` instead (UDF uses ``real`` for floating point).
    The target may embed a member access (``cell.volume``...) since it archives
    as a visual code edit."""

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.assign')

    @classmethod
    def render(cls, data: IDictionary[string, Any], builder: Compiler) -> string:
        require_member(data, 'name', 'value', 'constant')
        require_type(data['constant'], bool, 'constant')
        name = data['name']
        if isinstance(name, dict):
            name = render_edit(name, builder)
        else:
            # Archives made before the target could embed components kept a plain name
            require_type(name, string, 'name')
        name = name.strip()
        value = render_edit(data['value'], builder).strip()
        if data['constant']:
            return f'const real {name} = {value};'
        return f'{name} = {value};'


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
