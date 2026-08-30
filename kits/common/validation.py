# -*- coding: utf-8 -*-
"""
Immediate static checking of the component fields.

The kits contributing checkers (see ``core.checker``) define the language
rules; this module applies them right while the user writes, so contents that
cannot compile are marked as soon as they appear: a widget whose contents a
checker rejects carries the ``ecInvalid`` property (the application stylesheet
draws it red) and the first diagnostic as its tooltip.

Name fields attach the identifier validation (``attach_identifier_check``);
edits hosting handwritten code attach the debounced source validation
(``attach_source_check``) and the debounced asynchronous lint
(``attach_source_lint``): the former answers fast and marks errors red, the
latter reports the deeper analysis gently (an amber outline and a tooltip),
and only once the text it checked is still the one being displayed, so the
reaction stays calm while the user is typing. The common kit stays
language-neutral: without a registered checker the attachments simply mark
nothing.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit, QWidget

from alias import *
from core.checker import Diagnostic
from core.environment import Environment

# The property the application stylesheet selects on to draw invalid fields red
InvalidProperty: Final[string] = 'ecInvalid'
# The property the application stylesheet selects on to outline fields whose
# asynchronous lint reported problems: deliberately gentler than ``ecInvalid``
LintProperty: Final[string] = 'ecTidyWarning'


def identifier_diagnostic(text: string) -> Nullable[Diagnostic]:
    """
    :return: the first diagnostic the registered checkers report for an
        identifier, or null when every checker accepts it (or none exists)
    """
    environment = Environment.instance()
    for checker_type in environment.checkers:
        diagnostic = checker_type(environment.project).check_identifier(text)
        if diagnostic is not null:
            return diagnostic
    return null


def source_diagnostics(text: string) -> IList[Diagnostic]:
    """
    :return: the diagnostics the registered checkers report for a free source
        text (empty when every checker accepts it, or none exists)
    """
    environment = Environment.instance()
    diagnostics: IList[Diagnostic] = []
    for checker_type in environment.checkers:
        # noinspection broad-exception
        try:
            diagnostics.extend(checker_type(environment.project).check_source(text))
        except Exception:  # A checker must never break the edition
            continue
    return diagnostics


def mark(widget: QWidget, diagnostic: Nullable[Diagnostic]) -> void:
    """
    Mark a widget invalid (red, carrying the diagnostic as its tooltip), or
    lift the marking. Errors mark the widget; warnings only explain themselves
    through the tooltip.
    """
    # noinspection unresolved-references
    invalid = diagnostic is not null and diagnostic.severity == 'error'
    if widget.property(InvalidProperty) != invalid:
        widget.setProperty(InvalidProperty, invalid)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    widget.setToolTip(str(diagnostic) if diagnostic is not null else '')


def mark_lint(widget: QWidget, diagnostics: IList[Diagnostic]) -> void:
    """
    Report the result of the asynchronous lint on a widget: gently. The lint
    is advisory next to the synchronous checking, so problems outline the
    widget amber (never red) and the tooltip lists what was found; a clean
    report lifts the outline. The caller already ensured the reported text is
    still the text the widget displays.
    """
    flagged = bool(diagnostics)
    if widget.property(LintProperty) != flagged:
        widget.setProperty(LintProperty, flagged)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    if flagged:
        widget.setToolTip('\n'.join(str(diagnostic) for diagnostic in diagnostics[:8]))
    elif widget.property(InvalidProperty) is not True:
        widget.setToolTip('')  # Keep the invalid marking's tooltip otherwise


def _widget_text(widget: QWidget) -> string:
    return widget.text() if isinstance(widget, QLineEdit) else widget.toPlainText()


def attach_identifier_check(widget: QWidget, allow_empty: bool = True) -> void:
    """
    Validate a name field (assignment target, loop counter, macro parameter...)
    live: the registered checkers decide whether the identifier being written
    is valid; invalid contents mark the field red. Empty contents stay
    unmarked while ``allow_empty`` holds (the field is still being filled).
    A visual code edit embedding components names no plain identifier and
    stays unmarked as well.
    :param widget: the single-line edit or visual code edit holding the name
    :param allow_empty: whether empty contents stay unmarked
    """
    def validate() -> void:
        if getattr(widget, 'inserted_components', null):
            mark(widget, null)  # A member access names no plain identifier
            return
        text = _widget_text(widget).strip()
        if not text and allow_empty:
            mark(widget, null)
            return
        mark(widget, identifier_diagnostic(text))

    # noinspection bad-argument-type
    widget.textChanged.connect(lambda *_: validate())


def attach_source_check(edit: QWidget, delay: int = 500) -> void:
    """
    Validate an edit hosting handwritten code live: the registered checkers
    run over the whole text, debounced so a fast typist triggers no check per
    keystroke. The first error marks the edit red; the tooltip lists the first
    diagnostics reported.
    :param edit: the code edit to watch
    :param delay: debounce interval in milliseconds
    """
    timer = QTimer(edit)
    timer.setSingleShot(True)
    timer.setInterval(delay)

    def recheck() -> void:
        diagnostics = source_diagnostics(_widget_text(edit))
        first_error = next((d for d in diagnostics if d.severity == 'error'), null)
        mark(edit, first_error)
        if diagnostics:
            edit.setToolTip('\n'.join(str(diagnostic) for diagnostic in diagnostics[:5]))

    # noinspection bad-argument-type
    timer.timeout.connect(recheck)
    # noinspection bad-argument-type
    edit.textChanged.connect(timer.start)


def attach_source_lint(edit: QWidget, delay: int = 500, fragment: bool = False) -> void:
    """
    Lint an edit hosting handwritten code live: the registered checkers run
    their asynchronous deep check (e.g. clang-tidy) over the whole text. The
    reaction stays calm: a generous debounce waits for a typing pause, a
    report arriving after the text changed again is discarded, a fresh run
    cancels the previous one, and the outline is advisory amber, never red.
    :param edit: the code edit to watch
    :param delay: debounce interval in milliseconds
    :param fragment: whether the text is a statement fragment (checkers then
        wrap it into a minimal translation unit before linting)
    """
    timer = QTimer(edit)
    timer.setSingleShot(True)
    timer.setInterval(delay)
    state: IDictionary[string, Any] = {'handle': null, 'text': ''}

    def relint() -> void:
        text = _widget_text(edit)
        previous = state['handle']
        if previous is not null and previous.state() != 0:  # NotRunning
            previous.kill()  # A fresh text supersedes the running analysis
        state['handle'] = null
        state['text'] = text
        if getattr(edit, 'inserted_components', null):
            mark_lint(edit, [])  # Embedded components render no plain source
            return
        if not text.strip():
            mark_lint(edit, [])
            return
        reported_at: IDictionary[string, Any] = {'text': text}

        def report(diagnostics: IList[Diagnostic]) -> void:
            # Discard outdated reports: the text changed while the lint ran
            if reported_at['text'] != _widget_text(edit):
                return
            mark_lint(edit, diagnostics)

        environment = Environment.instance()
        for checker_type in environment.checkers:
            # noinspection broad-exception
            try:
                handle = checker_type(environment.project).lint_source(text, report, fragment)
            except Exception:  # A checker must never break the edition
                continue
            if handle is not null:
                state['handle'] = handle
                return  # One running lint suffices; the first provider wins
        mark_lint(edit, [])  # No checker lints: lift any previous outline

    # noinspection bad-argument-type
    timer.timeout.connect(relint)
    # noinspection bad-argument-type
    edit.textChanged.connect(timer.start)
