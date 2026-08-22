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

import copy
import re

from alias import *

from core.build import Compiler
from core.component import Component, ComponentDelegation, ComponentMetadata
from core.environment import Environment
from kits.fluent.fluent import UDF, fluent
from kits.fluent.localization import _

Indent: Final[string] = '    '

# Identifiers occupied by the counters of count loops currently in scope, carried
# in the compiler's products: an enclosing loop occupies its counter while its body
# renders, so nested loops pick distinct names and siblings reuse freed ones
OccupiedKey: Final[string] = '_ec_counters'

# Declarations lifted to block tops for ``auto`` variables (see ``analyze_scope``):
# maps the identity of a block-introducing edit archive to the declarations that
# must precede its contents; carried in the compiler's products
ScopeKey: Final[string] = '_ec_scope'

# Role-bearing contexts opened while rendering components that declare
# identifiers (the ``DEFINE_*`` macros, the traversal loops): a stack of
# role -> identifier maps ('cell', 'thread'...) the nested context-aware
# components resolve their arguments through; carried in the compiler's
# products. The innermost context providing a role wins
ContextKey: Final[string] = '_ec_context'

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
    Render a serialized component into UDF source.
    :param name: complete name of the component (in format 'kit.component')
    :param data: serialization produced by the component's ``__serialize__``
    :param builder: the compiler context (carries the target language)
    :return: the rendered source fragment
    :raise Compiler.BuildError: raise when no (or conflicting) delegation supports
        the target language

    Counterpart of ``Component.build`` for archives: nested components exist only as
    serializations, so native compilation (which needs the live component) is out of
    reach. A component natively supporting the language renders through its own
    archive-based ``render`` classmethod (mirroring ``render_unit``): the
    statement-level components the kits contribute for the language (e.g. the
    mesh traversal loops) nest inside visual code edits this way; the other
    components render through their delegations.
    """
    meta = Environment.instance().kit_manager.lookup(name)
    lang = builder.config.target_lang
    if lang in meta.languages:
        # Native at nest level: the component type renders its own archive
        render = getattr(meta.component_type, 'render', null)
        if render is null:
            raise Compiler.BuildError(Compiler.B1004, lang.name, meta.name)
        return render(data, builder)

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
    # The declared type of every hoisted name: the type field of the defining
    # assignment decides it (the first annotation wins), defaulting to ``real``
    declared_types: IDictionary[string, string] = {}

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
            declared_types.setdefault(target.strip(), _udf_type(data.get('type', '')))

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
        hoist.setdefault(block, []).append(f'{declared_types.get(name, "real")} {name};')


def _udf_type(type_key: Any) -> string:
    """
    :return: the C type the type key of an assignment stands for in UDF source:
        ``int`` and ``char`` pass through, everything else declares ``real``
        (the UDF alias of ``double``)
    """
    return type_key if type_key in ('int', 'char') else 'real'


def validate_unit(unit_data: IDictionary[string, Any], builder: Compiler) -> void:
    """
    Statically check the identifiers a translation-unit archive declares before
    rendering consumes it: every function name, macro parameter, loop counter
    and assignment target the components embed must be a valid C identifier
    (the checkers registered in the environment decide, so the C standard the
    project configures applies). Free C text stays unchecked here: it is
    incomplete fragments and the immediate checking of the edition covers it.
    :param unit_data: serialization of the translation-unit edit
    :param builder: the compiler context
    :raise Compiler.CompileError: raise B1006 listing every problem found
    """
    maybe_unused(builder)
    environment = Environment.instance()
    kit_manager = environment.kit_manager
    problems: IList[string] = []

    def identifier_problem(text: string) -> Nullable[string]:
        for checker_type in environment.checkers:
            diagnostic = checker_type(environment.project).check_identifier(text)
            if diagnostic is not null and diagnostic.severity == 'error':
                return diagnostic.message
        return null

    def check(display: string, value: Any, empty_message: Nullable[string] = null) -> void:
        if not isinstance(value, string):
            return
        text = value.strip()
        if not text:
            if empty_message is not null:
                problems.append(f'{display}: {empty_message}')
            return
        message = identifier_problem(text)
        if message is not null:
            problems.append(f'{display}: {message}')

    def on_component(name: string, data: Any, path: tuple[int, ...]) -> void:
        maybe_unused(path)
        if not isinstance(data, dict):
            return
        display = kit_manager.lookup(name).display_name
        if name == 'clk.assign':
            target = data.get('name', '')
            if isinstance(target, dict):
                # A target embedding components names no plain variable
                target = target.get('text', '') if not target.get('components') else ''
            check(display, target, _('validate_empty_name'))
        elif name == 'clk.for':
            # An absent or empty counter gets auto-named at render time
            check(display, data.get('counter', ''))
        elif name.startswith('fluent.'):
            # DEFINE_* macros declare a function name and parameter identifiers;
            # the traversal loops declare the identifiers their arguments name
            if 'name' in data:
                check(display, data['name'], _('validate_empty_name'))
            args = data.get('args')
            if isinstance(args, list):
                for arg in args:
                    check(display, arg, _('validate_empty_arg'))

    def on_text(text: string, path: tuple[int, ...]) -> void:
        maybe_unused(text, path)

    _walk_archive(unit_data, (), on_text, on_component)
    if problems:
        raise Compiler.CompileError(Compiler.B1006, '\n'.join(problems))


# A minimal stand-in for Fluent's udf.h: ``check_product`` compiles the rendered
# translation unit against it, so the DEFINE_* macros, the traversal loops and
# the API macros the kits emit (or their snippets insert) resolve to plausible
# C constructs. The loop macros introduce their loop variables in ``for``
# initializers (C99), the field accessors expand to lvalues, and the stub itself
# stays silent in every standard the check runs (see ``check_product``); every
# diagnostic inside the stub's own lines is discarded
_UdfStub: Final[string] = """\
#include <stdio.h>
typedef double real;
typedef struct { real _ec_stub; } Thread, Domain, Node, Injection, Tracked_Part,
    Dynamic_Thread, Phase, Reaction, Source, Pollut_Cell, Pollut_Parameter,
    NOx_Model, SOx_Model;
typedef int cell_t, face_t;
#define DEFINE_ADJUST(name, d) void name(Domain *d)
#define DEFINE_INIT(name, d) void name(Domain *d)
#define DEFINE_EXECUTE_AT_END(name) void name(void)
#define DEFINE_ON_DEMAND(name) void name(void)
#define DEFINE_RW_FILE(name, fp) void name(FILE *fp)
#define DEFINE_DELTAT(name, d) real name(Domain *d)
#define DEFINE_EXECUTE_FROM_GUI(name, msg) void name(int msg)
#define DEFINE_PROFILE(name, t, i) void name(Thread *t, int i)
#define DEFINE_SOURCE(name, c, t, dS, eqn) real name(cell_t c, Thread *t, real dS[], int eqn)
#define DEFINE_PROPERTY(name, c, t) real name(cell_t c, Thread *t)
#define DEFINE_DIFFUSIVITY(name, c, t, i) real name(cell_t c, Thread *t, int i)
#define DEFINE_TURBULENT_VISCOSITY(name, c, t) real name(cell_t c, Thread *t)
#define DEFINE_PRANDTL(name, c, t) real name(cell_t c, Thread *t)
#define DEFINE_TURB_SCHMIDT(name, c, t, i) real name(cell_t c, Thread *t, int i)
#define DEFINE_SPECIFIC_HEAT(name, T, Tref, h, yi) real name(real T, real Tref, real *h, real yi[])
#define DEFINE_HEAT_FLUX(name, f, t, c0, t0, cid, cir) void name(face_t f, Thread *t, cell_t c0, Thread *t0, real cid[], real cir[])
#define DEFINE_VR_RATE(name, c, t, r, mw, yi, rr, rr_t) void name(cell_t c, Thread *t, Reaction *r, real *mw, real *yi, real *rr, real *rr_t)
#define DEFINE_SR_RATE(name, f, t, r, mw, yi, rr) void name(face_t f, Thread *t, Reaction *r, real *mw, real *yi, real *rr)
#define DEFINE_CAVITATION_RATE(name, c, t, p, rhoV, rhoL, mafV, p_v, cigma, f_gas, m_dot) void name(cell_t c, Thread *t, real p, real rhoV, real rhoL, real mafV, real p_v, real cigma, real f_gas, real *m_dot)
#define DEFINE_NOX_RATE(name, c, t, Pollut, Pollut_Par, NOx) void name(cell_t c, Thread *t, Pollut_Cell *Pollut, Pollut_Parameter *Pollut_Par, NOx_Model *NOx)
#define DEFINE_SOX_RATE(name, c, t, Pollut, Pollut_Par, SOx) void name(cell_t c, Thread *t, Pollut_Cell *Pollut, Pollut_Parameter *Pollut_Par, SOx_Model *SOx)
#define DEFINE_CPHI(name, c, t) real name(cell_t c, Thread *t)
#define DEFINE_DOM_SOURCE(name, c, t, s, xi, emission, in_scattering, abs_coeff, scat_coeff) void name(cell_t c, Thread *t, int s, real xi, real *emission, real *in_scattering, real *abs_coeff, real *scat_coeff)
#define DEFINE_EMISSIVITY_WEIGHTING_FACTOR(name, c, t, s, xi, weight) void name(cell_t c, Thread *t, int s, real xi, real *weight)
#define DEFINE_DPM_INJECTION_INIT(name, I) void name(Injection *I)
#define DEFINE_DPM_LAW(name, p, ci) void name(Tracked_Part *p, int ci)
#define DEFINE_DPM_DRAG(name, p, Re) real name(Tracked_Part *p, real Re)
#define DEFINE_DPM_BODY_FORCE(name, p, mass, F, Fd) real name(Tracked_Part *p, real mass, real F[], real Fd)
#define DEFINE_DPM_SOURCE(name, cell, thread, S, strength, p) void name(cell_t cell, Thread *thread, Source *S, real strength, Tracked_Part *p)
#define DEFINE_DPM_BC(name, p, t, f, f_normal, dim) void name(Tracked_Part *p, Thread *t, face_t f, real f_normal[], int dim)
#define DEFINE_GRID_MOTION(name, d, dt, time, dtime) void name(Domain *d, Dynamic_Thread *dt, real time, real dtime)
#define DEFINE_CG_MOTION(name, dt, cg_velocity, cg_omega, time, dtime) void name(Dynamic_Thread *dt, real cg_velocity[], real cg_omega[], real time, real dtime)
#define DEFINE_MASS_TRANSFER(name, from, from_t, to, to_t) real name(Phase *from, Thread *from_t, Phase *to, Thread *to_t)
#define DEFINE_EXCHANGE_PROPERTY(name, from, from_t, to, to_t) real name(Phase *from, Thread *from_t, Phase *to, Thread *to_t)
#define DEFINE_VECTOR_EXCHANGE_PROPERTY(name, from, from_t, to, to_t) void name(Phase *from, Thread *from_t, Phase *to, Thread *to_t)
#define thread_loop_c(t, d) for (Thread *t = (Thread *)0; t; )
#define thread_loop_f(t, d) for (Thread *t = (Thread *)0; t; )
#define begin_c_loop(c, t) for (cell_t c = 0; c; )
#define end_c_loop(c, t)
#define begin_f_loop(f, t) for (face_t f = 0; f; )
#define end_f_loop(f, t)
#define c_face_loop(c, t, n) for (int n = 0; n; )
#define c_node_loop(c, t, n) for (int n = 0; n; )
#define C_T(...) (*(volatile real *)0)
#define C_P(...) (*(volatile real *)0)
#define C_U(...) (*(volatile real *)0)
#define C_V(...) (*(volatile real *)0)
#define C_W(...) (*(volatile real *)0)
#define C_R(...) (*(volatile real *)0)
#define C_MU_L(...) (*(volatile real *)0)
#define C_MU_T(...) (*(volatile real *)0)
#define C_K_L(...) (*(volatile real *)0)
#define C_K(...) (*(volatile real *)0)
#define C_CP(...) (*(volatile real *)0)
#define C_EPS(...) (*(volatile real *)0)
#define C_OMEGA(...) (*(volatile real *)0)
#define C_T_G(...) (*(volatile real *)0)
#define C_P_G(...) (*(volatile real *)0)
#define C_CENTROID(...) (*(volatile real (*)[3])0)
#define C_VOLUME(...) (*(volatile real *)0)
#define C_UDMI(...) (*(volatile real *)0)
#define C_UDSI(...) (*(volatile real *)0)
#define C_UDSI_G(...) (*(volatile real *)0)
#define C_VOF(...) (*(volatile real *)0)
#define C_YI(...) (*(volatile real *)0)
#define F_T(...) (*(volatile real *)0)
#define F_P(...) (*(volatile real *)0)
#define F_U(...) (*(volatile real *)0)
#define F_V(...) (*(volatile real *)0)
#define F_W(...) (*(volatile real *)0)
#define F_CENTROID(...) (*(volatile real (*)[3])0)
#define F_PROFILE(...) (*(volatile real *)0)
#define C_PROFILE(...) (*(volatile real *)0)
#define F_AREA(...) (*(volatile real (*)[3])0)
#define F_FLUX(...) (*(volatile real *)0)
#define F_FLUX_I(...) (*(volatile real *)0)
#define F_VOF(...) (*(volatile real *)0)
#define F_YI(...) (*(volatile real *)0)
#define F_RHO(...) (*(volatile real *)0)
#define F_C0(...) ((cell_t)0)
#define F_C1(...) ((cell_t)0)
#define F_UDMI(...) (*(volatile real *)0)
#define C_FACE(...) ((face_t)0)
#define C_FACE_THREAD(...) ((Thread *)0)
#define C_NODE(...) ((Node *)0)
#define RP_2D ((int)0)
#define RP_3D ((int)1)
#define ND_ND 3
#define NV_V(...) ((void)0)
#define NV_VV(...) ((void)0)
#define NV_MAG(...) ((real)0)
#define NV_DOT(...) ((real)0)
#define PRF_GIHIGH1(...) ((int)0)
#define PRF_GRSUM1(...) ((real)0)
#define FL_MALLOC(...) ((void *)0)
#define FL_FREE(...) ((void)0)
#define CURRENT_TIMESTEP ((int)0)
#define CURRENT_TIME ((real)0)
#define PREVIOUS_TIME ((real)0)
#define Message(...) ((void)0)
#define Lookup_Thread(...) ((Thread *)0)
#define THREAD_ID(...) ((int)0)
#define THREAD_TYPE(...) ((int)0)
#define THREAD_SUB_THREAD(...) ((Thread *)0)
#define PHASE_INDEX(...) ((int)0)
"""
_UdfStubLines: Final[int] = _UdfStub.count('\n')


def check_product(body: string, builder: Compiler) -> void:
    """
    Check that the rendered translation-unit body can plausibly pass C
    compilation: compile it against the udf.h stand-in (``_UdfStub``) through
    the checkers registered in the environment and record every error of the
    body itself as a B1007 compile warning (the build itself stays green;
    the warning surfaces in the build message panel).
    :param body: the rendered source of the translation unit (without the
        leading ``#include "udf.h"``)
    :param builder: the compiler context receiving the warning
    """
    if not body.strip():
        return
    environment = Environment.instance()
    project = environment.project
    # The stub needs C99 loop initializers, and unresolved API names must stay
    # implicit calls (errors from C23 onwards): clamp the standard into the
    # range the stub itself compiles silently in
    if project is not null and project.c_standard not in ('c99', 'c11', 'c17'):
        project = copy.copy(project)
        project.c_standard = 'c99' if project.c_standard in ('c89', 'c90') else 'c17'
    problems: IList[string] = []
    for checker_type in environment.checkers:
        for diagnostic in checker_type(project).check_source(_UdfStub + body + '\n'):
            if diagnostic.severity != 'error' or diagnostic.line <= _UdfStubLines:
                continue  # Inside the stub's own lines, not the user's code
            problems.append(f'{diagnostic.line - _UdfStubLines}: {diagnostic.message}')
    if problems:
        builder.warnings.append(Compiler.CompileWarning(Compiler.B1007, '\n'.join(problems)))


def _hoist_prefix(builder: Compiler, edit_data: IDictionary[string, Any]) -> string:
    """
    :return: the declarations ``analyze_scope`` lifted to the top of the block
        a block-introducing edit archive opens (empty when none, or when no
        scope analysis ran on the enclosing translation unit)
    """
    hoist = builder.products.get(ScopeKey, {})
    declarations: IList[string] = hoist.get(id(edit_data), [])
    return ''.join(declaration + '\n' for declaration in declarations)


def enter_context(builder: Compiler, roles: IDictionary[string, string]) -> void:
    """
    Open a context mapping semantic roles to the identifiers in scope while
    the caller renders (see ``ContextKey``); pair with ``exit_context`` around
    the rendering of the body the identifiers belong to.
    :param builder: the compiler context
    :param roles: role -> identifier mappings the caller introduces
    """
    stack: IList[IDictionary[string, string]] = builder.products.setdefault(ContextKey, [])
    stack.append(dict(roles))


def exit_context(builder: Compiler) -> void:
    """
    Close the most recent context opened by ``enter_context``.
    :param builder: the compiler context
    """
    stack: IList[IDictionary[string, string]] = builder.products.get(ContextKey, [])
    if stack:
        stack.pop()


def context_role(builder: Compiler, role: string) -> string:
    """
    :param builder: the compiler context
    :param role: semantic role of the identifier ('cell', 'thread'...)
    :return: the identifier the innermost open context assigns to the role
        (empty when no context provides it)
    """
    stack: IList[IDictionary[string, string]] = builder.products.get(ContextKey, [])
    for frame in reversed(stack):
        identifier = frame.get(role, '')
        if identifier:
            return identifier
    return ''


def fresh_name(base: string, occupied: ICollection[string]) -> string:
    """
    Pick an identifier derived from ``base`` that is not occupied yet: ``base``
    itself when free, otherwise ``base`` suffixed with an up-counting index
    (``dS``, ``dS_1``, ``dS_2``...). The caller occupies the returned name.
    :param base: the identifier the name derives from
    :param occupied: identifiers that must not be reused
    :return: the first candidate that is not occupied yet
    """
    name = base
    index = 1
    while name in occupied:
        name = f'{base}_{index}'
        index += 1
    return name


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
    the value as a constant of the annotated type instead (``const real`` by
    default: UDF uses ``real`` for floating point, see ``_udf_type``).
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
            # 'type' is absent in archives made before the field existed
            return f'const {_udf_type(data.get("type", ""))} {name} = {value};'
        return f'{name} = {value};'


class UdfOperator(UdfDelegation):
    """A binary operator renders as ``(left symbol right)``: the parentheses
    keep the precedence intact when the expression nests. Archives made before
    the operands existed carry no keys and render as the bare symbol."""

    symbol: ClassVar[string] = ''

    @classmethod
    def render(cls, data: Any, builder: Compiler) -> string:
        if not isinstance(data, dict) or ('left' not in data and 'right' not in data):
            return cls.symbol  # Legacy archive: the bare symbol
        empty: IDictionary[string, Any] = {'text': '', 'components': []}
        left = data['left'] if 'left' in data else empty
        right = data['right'] if 'right' in data else empty
        return f'({render_edit(left, builder).strip()} {cls.symbol} {render_edit(right, builder).strip()})'


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
class UdfGreater(UdfOperator):
    symbol = '>'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.greater')


@fluent.register
class UdfLess(UdfOperator):
    symbol = '<'

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.less')


@fluent.register
class UdfGreaterEqual(UdfOperator):
    symbol = '>='

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.greater_equal')


@fluent.register
class UdfLessEqual(UdfOperator):
    symbol = '<='

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.less_equal')


@fluent.register
class UdfEqual(UdfOperator):
    symbol = '=='

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.equal')


@fluent.register
class UdfNotEqual(UdfOperator):
    symbol = '!='

    @classmethod
    def delegated(cls) -> ComponentDelegation.DelegationTarget:
        return ComponentDelegation.DelegationTarget((UDF,), 'clk.not_equal')


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
