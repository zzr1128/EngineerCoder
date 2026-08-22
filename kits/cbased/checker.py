# -*- coding: utf-8 -*-
"""
C language checker of the C-based kit.

``CbasedChecker`` implements the ``Checker`` contract for the C family: it
validates identifiers against the rules of the C standard the project selects
(``Project.c_standard``: the lexical form, the keyword set the standard
reserves and the reserved underscore namespace), and it checks free C source
(hand-written code embedding no components) syntax-only.

The source check prefers the clang frontend: the bundled toolchain that ships
with the kit (``kits/cbased/clang``) first, a ``clang`` found on the PATH
afterwards; without one it falls back to the intrinsic structural check
(delimiter pairing, unterminated literals), so the checking degrades but
never disappears.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess

from alias import *
from core.checker import Checker, Diagnostic
from core.environment import Environment
from kits.cbased.localization import _

# C standards the checker supports (the project selects one, see ``Project.c_standard``)
C_STANDARDS: Final[tuple[string, ...]] = ('c89', 'c90', 'c99', 'c11', 'c17', 'c23')

# Keywords reserved by each standard: what one standard reserves stays reserved
# in its successors, and each newer standard adds its own
_KEYWORDS_C89: Final[frozenset[string]] = frozenset((
    'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if', 'int',
    'long', 'register', 'return', 'short', 'signed', 'sizeof', 'static',
    'struct', 'switch', 'typedef', 'union', 'unsigned', 'void', 'volatile',
    'while'))
_KEYWORDS_C99: Final[frozenset[string]] = _KEYWORDS_C89 | frozenset((
    'inline', 'restrict', '_Bool', '_Complex', '_Imaginary'))
_KEYWORDS_C11: Final[frozenset[string]] = _KEYWORDS_C99 | frozenset((
    '_Alignas', '_Alignof', '_Atomic', '_Generic', '_Noreturn',
    '_Static_assert', '_Thread_local'))
_KEYWORDS_C23: Final[frozenset[string]] = _KEYWORDS_C11 | frozenset((
    'alignas', 'alignof', 'bool', 'constexpr', 'false', 'nullptr',
    'static_assert', 'thread_local', 'true', 'typeof', 'typeof_unaligned'))
_KEYWORDS: Final[IDictionary[string, frozenset[string]]] = {
    'c89': _KEYWORDS_C89, 'c90': _KEYWORDS_C89, 'c99': _KEYWORDS_C99,
    'c11': _KEYWORDS_C11, 'c17': _KEYWORDS_C11, 'c23': _KEYWORDS_C23,
}

# The lexical form of a C identifier (every standard): a letter or underscore,
# then letters, digits or underscores
_IDENTIFIER: Final[re.Pattern] = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')

# Diagnostics clang emits on its standard error: ``file:line:col: severity: message``
_CLANG_DIAGNOSTIC: Final[re.Pattern] = re.compile(
    r'^.*?:(\d+):(\d+):\s*(fatal error|error|warning|note):\s*(.*)$')

# clang-tidy diagnostics carry the contributing check between brackets:
# ``file:line:col: severity: message [check-name]``
_TIDY_DIAGNOSTIC: Final[re.Pattern] = re.compile(
    r'^.*?:(\d+):(\d+):\s*(fatal error|error|warning|note):\s*(.*?)(?:\s*\[([\w.,\-]+)\])?$')

# The focused check set of the live lint: correctness-oriented and cheap, so
# the asynchronous run stays short enough to follow the typing. The
# clang-diagnostic pseudo checks surface the compiler's own warnings (e.g.
# using an assignment as a condition); bugprone-* and clang-analyzer-core.*
# catch the classic logic mistakes (a loop condition variable never updated,
# a division that reaches zero, an uninitialized read)
_TIDY_CHECKS: Final[string] = (
    '-*,clang-diagnostic-*,bugprone-infinite-loop,bugprone-suspicious-semicolon,'
    'bugprone-sizeof-expression,clang-analyzer-core.DivideZero,'
    'clang-analyzer-core.uninitialized.Assign,clang-analyzer-core.uninitialized.Branch,'
    'clang-analyzer-deadcode.DeadStores')

# Statement fragments (a macro body, a loop body...) are no translation unit;
# the lint wraps them into a minimal one declaring the conventional Fluent
# identifiers, so references like ``c``/``t`` are not reported undeclared
_TIDY_PREAMBLE: Final[string] = (
    'typedef int Thread, cell_t, face_t, Node, Domain;\n'
    'typedef double real;\n'
    'void ec_fragment(void)\n'
    '{\n'
    '    Thread *t = 0, *d = 0; cell_t c = 0; face_t f = 0;\n'
    '    Domain *domain = 0; int i = 0, n = 0; real x[3] = {0, 0, 0};\n')
_TIDY_PREAMBLE_LINES: Final[int] = _TIDY_PREAMBLE.count('\n')

# The identifiers the fragment wrapper declares itself: project variables of
# the same name never get declared a second time
_TIDY_PREDECLARED: Final[frozenset[string]] = frozenset(
    ('t', 'd', 'c', 'f', 'domain', 'i', 'n', 'x'))


def clang_tool() -> Nullable[Path]:
    """
    :return: the clang executable driving the source check: the one bundled
        with the kit when it is present, otherwise one found on the PATH;
        null when no clang is available (the intrinsic check steps in)
    """
    bundled = Path(__file__).resolve().parent / 'clang'
    for name in ('clang.exe', 'clang'):
        candidate = bundled / name
        if candidate.is_file():
            return candidate
    found = shutil.which('clang')
    return Path(found) if found is not null else null


def tidy_tool() -> Nullable[Path]:
    """
    :return: the clang-tidy executable driving the live lint: the one bundled
        with the kit when it is present, otherwise one found on the PATH;
        null when no clang-tidy is available (the lint simply does not run)
    """
    bundled = Path(__file__).resolve().parent / 'clang'
    for name in ('clang-tidy.exe', 'clang-tidy'):
        candidate = bundled / name
        if candidate.is_file():
            return candidate
    found = shutil.which('clang-tidy')
    return Path(found) if found is not null else null


class CbasedChecker(Checker):
    """
    The C language checker: identifier rules and syntax-only source checking
    against the C standard the loaded project selects (default ``c99``), plus
    an asynchronous clang-tidy lint of the free source texts while they are
    being written.
    """

    @property
    def standard(self) -> string:
        """The C standard the check applies: the loaded project selects it."""
        project = self.project
        if project is not null:
            selected = getattr(project, 'c_standard', '').strip().lower()
            if selected in C_STANDARDS:
                return selected
        return 'c99'

    def check_identifier(self, name: string) -> Nullable[Diagnostic]:
        """
        Validate an identifier against the selected standard: its lexical
        form, the keywords the standard reserves, and the reserved underscore
        namespace (identifiers starting with two underscores, or an underscore
        and an uppercase letter, are reserved by the C standard).
        """
        name = name.strip()
        if not name:
            return Diagnostic('error', _('identifier_empty'))
        if not name.isascii() or _IDENTIFIER.fullmatch(name) is null:
            return Diagnostic('error', _('identifier_invalid').format(name))
        if name in _KEYWORDS[self.standard]:
            return Diagnostic('error', _('identifier_keyword').format(name, self.standard))
        if name.startswith('__') or (len(name) > 1 and name[0] == '_' and name[1].isupper()):
            return Diagnostic('warning', _('identifier_reserved').format(name))
        return null

    def check_source(self, text: string) -> IList[Diagnostic]:
        """
        Check a free C source text syntax-only: through clang when one is
        available (the exact diagnostics of the selected standard), otherwise
        through the intrinsic structural check.
        """
        if not text.strip():
            return []
        tool = clang_tool()
        if tool is not null:
            diagnostics = self._clang_check(tool, text)
            if diagnostics is not null:
                return diagnostics
        return self._intrinsic_check(text)

    def lint_source(self, text: string, report: Callable[[IList[Diagnostic]], void],
                    fragment: bool = False) -> Nullable[Any]:
        """
        Lint a free C source text asynchronously through clang-tidy (the focused
        correctness checks of ``_TIDY_CHECKS``). Statement fragments are first
        wrapped into a minimal translation unit (``_TIDY_PREAMBLE`` plus the
        variables the project introduces, so references to them stay silent);
        the reported lines are relative to the text the user wrote.
        :return: the running process (the cancellation handle), or null when
            no clang-tidy is available
        """
        if not text.strip():
            return null
        tool = tidy_tool()
        if tool is null:
            return null
        preamble = _TIDY_PREAMBLE
        if fragment:
            # Expression and statement fields omit their terminating semicolon:
            # add it, so a value like ``s+1`` is judged by its contents alone
            stripped = text.rstrip()
            if stripped and not stripped.endswith((';', '{', '}')):
                stripped += ';'
            text = stripped
            # The variables the project introduces are visible in the fragment;
            # declaring them keeps the lint silent about legitimate references
            declarations = self._project_declarations()
            if declarations:
                preamble = _TIDY_PREAMBLE + declarations + '\n'
        source = f'{preamble}{text}\n}}\n' if fragment else text
        # Lines the wrapper prepends before the user's text (rebased away from
        # the reported diagnostics)
        preamble_lines = preamble.count('\n') if fragment else 0
        try:
            descriptor, path = tempfile.mkstemp(suffix='.c', prefix='ec_lint_')
            with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
                f.write(source)
        except OSError:
            return null
        arguments: IList[string] = ['--quiet', f'--checks={_TIDY_CHECKS}', path, '--',
                                    f'-std={self.standard}', '-Wparentheses',
                                    # Unused values are noise while a text is still being
                                    # written; the correctness checks stay loud enough
                                    '-Wno-unused-variable', '-Wno-unused-value',
                                    '-Wno-unused-but-set-variable']
        if fragment:
            # UDF macros are functions the fragment never declares: silence the
            # implicit declarations instead of rejecting the fragment for them
            arguments += ['-Wno-implicit-function-declaration', '-Wno-implicit-int']
        process = QProcess()
        running = {'value': True}  # Survives the process object's deletion

        def finished(exit_code: int, exit_status: Any) -> void:
            maybe_unused(exit_code, exit_status)
            running['value'] = False
            output = bytes(process.readAllStandardOutput()).decode('utf-8', 'replace') \
                + bytes(process.readAllStandardError()).decode('utf-8', 'replace')
            report(self._tidy_diagnostics(output, path, fragment, preamble_lines))
            try:
                os.remove(path)
            except OSError:  # A leftover temporary file never breaks the edition
                pass
            process.deleteLater()

        # The handle outlives the process object (the next lint must be able to
        # ask whether its predecessor still runs without touching the deleted
        # C++ object); ``kill`` only reaches a process that is still alive
        class _Handle:
            @staticmethod
            def state() -> int:
                return 1 if running['value'] else 0

            @staticmethod
            def kill() -> void:
                if running['value']:
                    process.kill()

        # noinspection bad-argument-type
        process.finished.connect(finished)
        process.start(str(tool), arguments)
        return _Handle()

    @final
    def _project_declarations(self) -> string:
        """
        :return: the declarations of the variables the loaded project
            introduces (one line per name, file scope), so linted fragments
            referencing them do not report them undeclared; empty without a
            loaded project or without completers deriving variables
        """
        environment = Environment.instance()
        project = environment.project
        if project is null:
            return ''
        declarations: IList[string] = []
        seen: HashSet[string] = set(_TIDY_PREDECLARED)
        for completer_type in environment.completers:
            # noinspection broad-exception
            try:
                completer = completer_type(project)
                completions = completer.complete()
            except Exception:  # A completer must never break the lint
                continue
            for completion in completions:
                name = completion.keyword.strip()
                # Only analyzer-derived variables declare names; the wrapper's
                # own identifiers and C keywords never get re-declared
                if getattr(completion.kind, 'value', '') != 'variable' \
                        or not name or name in seen \
                        or _IDENTIFIER.fullmatch(name) is null \
                        or name in _KEYWORDS[self.standard]:
                    continue
                seen.add(name)
                # noinspection broad-exception
                try:
                    declared = completer.lookup_type(name).strip()
                except Exception:
                    declared = ''
                # Constants are declared in place: re-declaring them here would
                # make every assignment to them a read-only error
                if not declared or 'const' in declared:
                    declared = 'real'
                declarations.append(f'{declared} {name};')
        return '\n'.join(declarations)

    @staticmethod
    def _tidy_diagnostics(output: string, path: string, fragment: bool,
                          preamble_lines: int = _TIDY_PREAMBLE_LINES) -> IList[Diagnostic]:
        """Translate clang-tidy's output into diagnostics of the linted text."""
        forward = path.replace(os.sep, '/')
        diagnostics: IList[Diagnostic] = []
        for raw in output.splitlines():
            line = raw.strip()
            # Only the linted translation unit matters: includes and notes
            # annotate other files and stay out of the concise feedback
            if not (line.startswith(path) or line.startswith(forward)):
                continue
            match = _TIDY_DIAGNOSTIC.match(line)
            if match is null or match.group(3) == 'note':
                continue
            located = int(match.group(1)) - (preamble_lines if fragment else 0)
            if located < 1:
                continue  # Inside the wrapper's preamble, not the user's text
            message = match.group(4)
            check_name = match.group(5)
            if check_name:
                message = f'{message} [{check_name}]'
            diagnostics.append(Diagnostic(
                'error' if match.group(3) in ('error', 'fatal error') else 'warning',
                message, located, int(match.group(2))))
        return diagnostics

    @final
    def _clang_check(self, tool: Path, text: string) -> Nullable[IList[Diagnostic]]:
        """
        Run the clang frontend syntax-only over the text and translate its
        diagnostics; null when the tool cannot run (the intrinsic check then
        steps in).
        """
        try:
            result = subprocess.run(
                [str(tool), '-fsyntax-only', '-x', 'c', f'-std={self.standard}', '-'],
                input=text, capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=10)
        except (OSError, subprocess.SubprocessError):
            return null
        diagnostics: IList[Diagnostic] = []
        for line in result.stderr.splitlines():
            match = _CLANG_DIAGNOSTIC.match(line.strip())
            if match is null:
                continue
            severity = match.group(3)
            if severity == 'note':
                continue  # Notes annotate preceding diagnostics; the message list stays concise
            diagnostics.append(Diagnostic(
                'error' if severity in ('error', 'fatal error') else 'warning',
                match.group(4), int(match.group(1)), int(match.group(2))))
        return diagnostics

    @staticmethod
    def _intrinsic_check(text: string) -> IList[Diagnostic]:
        """
        The structural fallback without clang: delimiter pairing and
        unterminated strings, character constants and comments. Deliberately
        conservative, it reports only what is certainly wrong.
        """
        diagnostics: IList[Diagnostic] = []
        pairs = {')': '(', ']': '[', '}': '{'}
        stack: IList[tuple[string, int]] = []
        line = 1
        index = 0
        length = len(text)
        while index < length:
            ch = text[index]
            if ch == '\n':
                line += 1
            elif ch in ('"', "'"):
                # A string or character constant must terminate on its own line
                quote, start_line = ch, line
                index += 1
                terminated = False
                while index < length:
                    symbol = text[index]
                    if symbol == '\\':
                        index += 2
                        continue
                    if symbol == quote:
                        terminated = True
                        break
                    if symbol == '\n':
                        break
                    index += 1
                if not terminated:
                    diagnostics.append(Diagnostic('error', _('source_unterminated').format(quote), start_line))
            elif ch == '/' and index + 1 < length:
                if text[index + 1] == '/':
                    index = text.find('\n', index)
                    if index < 0:
                        break
                    continue
                if text[index + 1] == '*':
                    start_line = line
                    end = text.find('*/', index + 2)
                    if end < 0:
                        diagnostics.append(Diagnostic('error', _('source_unterminated_comment'), start_line))
                        break
                    line += text.count('\n', index, end)
                    index = end + 1
            elif ch in '([{':
                stack.append((ch, line))
            elif ch in ')]}':
                if not stack or stack[-1][0] != pairs[ch]:
                    diagnostics.append(Diagnostic('error', _('source_unbalanced').format(ch), line))
                else:
                    stack.pop()
            index += 1
        for opening, opened_at in reversed(stack):
            diagnostics.append(Diagnostic('error', _('source_unclosed').format(opening), opened_at))
        return diagnostics


# Contribute the checker to the environment so the editors and the compilation
# consult it (instantiated against the loaded project on demand)
Environment.instance().register_checker(CbasedChecker)
