# -*- coding: utf-8 -*-
"""
Static checking abstraction: the shared diagnostic type and the checker contract.

A ``Checker`` validates what the edition and the building pipeline produce:
the identifiers the user writes into name fields (``check_identifier``) and
the free source text that embeds no components (``check_source``). Checkers
are contributed by kits (e.g. the C-based kit checking against the C standard
the project selects) and registered in the environment; the editors consult
them for the immediate static checking (marking invalid contents right while
they are written) and the compilation consults them before emitting source,
so invalid components never pass the build.
"""

from dataclasses import dataclass

from alias import *
from core.project import Project


@dataclass
class Diagnostic:
    """
    A single message a checker reports.

    :param severity: ``error`` (contents cannot compile) or ``warning``
    :param message: human-readable description of the problem
    :param line: line of the checked text the problem is located in (0 = unknown)
    :param column: column of the checked text the problem is located in (0 = unknown)
    """
    severity: string
    message: string
    line: int = 0
    column: int = 0

    def __str__(self):
        location = f'{self.line}:{self.column}: ' if self.line else ''
        return f'{location}{self.severity}: {self.message}'


class Checker(abstract):
    """
    Base of checkers: validate identifiers and free source text of a project.

    Concrete checkers (e.g. ``kits.cbased.checker``) implement the language
    rules they stand for. Checkers are registered in the environment
    (``Environment.register_checker``) and instantiated per project, so they
    may consult the project's settings (e.g. the C standard it selects).
    """

    def __init__(self, project: Nullable[Project]):
        self.project = project

    def check_identifier(self, name: string) -> Nullable[Diagnostic]:
        """
        Validate an identifier the user writes into a name field (the target
        of an assignment, a loop counter, a macro parameter...).
        :param name: the identifier text (already stripped)
        :return: the first problem found, or null when the identifier is valid
        """
        maybe_unused(name)
        return null

    def check_source(self, text: string) -> IList[Diagnostic]:
        """
        Check a free source text (hand-written code embedding no components).
        :param text: the source text to check
        :return: the problems found (empty when the text is valid)
        """
        maybe_unused(text)
        return []

    def lint_source(self, text: string, report: Callable[[IList[Diagnostic]], void],
                    fragment: bool = False) -> Nullable[Any]:
        """
        Lint a free source text asynchronously (a deep analysis the synchronous
        ``check_source`` is too fast for, e.g. a clang-tidy run). The checker
        starts the analysis and calls ``report`` with the diagnostics once it
        finishes; the caller discards reports whose text is outdated.
        :param text: the source text to lint
        :param report: callback receiving the diagnostics when the lint finishes
        :param fragment: whether the text is a statement fragment (the checker
            then wraps it into a minimal translation unit before linting)
        :return: a cancellation handle (exposing ``kill()``), or null when this
            checker provides no asynchronous lint
        """
        maybe_unused(text, report, fragment)
        return null
