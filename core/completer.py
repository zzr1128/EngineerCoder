# -*- coding: utf-8 -*-
"""
Completion abstraction: the shared suggestion type and the completer contract.

A ``Completer`` analyzes a project and contributes ``Completion`` suggestions to
the code completion of the editors (see ``VisualCodeEdit``). Static components
are offered through the kit manager's completion registry; completers derive
additional suggestions (e.g. variables discovered from assignments) that have
no component of their own.

The ``Completer`` contract is the customization point of the code completion:
a kit subclasses it, implements the derivations it offers (the suggestions
themselves, the declared type of the variables it introduces and the type
options of assignments) and registers the subclass in the environment; the
editors then consult every registered completer through this interface only.
"""

from dataclasses import dataclass

from alias import *
from core.component import ComponentMetadata
from core.project import Project


@dataclass
class Completion:
    """
    A single code-completion suggestion.

    :param keyword: the keyword/identifier that triggers the suggestion
    :param component_name: complete name of the component to insert (e.g.
        ``clk.br``); empty for derived suggestions that carry no component
        (confirming them completes the keyword as plain text instead)
    :param description: description shown in the popup detail pane
    :param kind: symbol kind selecting the glyph shown in front of the entry;
        ``null`` defers to the kind declared by the component metadata
    :param visibility: scope annotation of a derived variable: ``local`` keeps
        it inside the block that introduces it, ``auto`` lifts its declaration
        to the smallest namespace shared by all its references (see the kit
        compilation), ``scoped`` keeps it inside the subtree of the component
        introducing it (e.g. a function parameter); unused by suggestions that
        carry a component
    """
    keyword: string
    component_name: string = ''
    description: string = ''
    kind: Nullable[ComponentMetadata.Kind] = null
    visibility: string = 'local'


class Completer(abstract):
    """
    Base of completers: analyze a project and produce completion suggestions.

    Concrete completers (e.g. ``kits.fluent.analyzer``) inspect the component
    trees of the project's scripts and return the suggestions they derive.
    Completers are registered in the environment (``Environment.register_completer``)
    and consulted by the editors while completing.
    """

    def __init__(self, project: Project):
        self.project = project

    @pure_virtual
    def complete(self, at: Any = null) -> IList[Completion]:
        """
        Analyze the project and derive the completion suggestions it yields.
        :param at: the edit requesting the completion; scope-aware completers
            restrict their suggestions to the names visible at that edit, while
            ``null`` asks for the whole-project view
        :return: the suggestions derived from the project
        """
        raise NotImplementedError

    def lookup_type(self, name: string) -> string:
        """
        Resolve the declared type of a variable the project defines (e.g. from
        a declaration in the sources or from another definition of the name).
        Kits override this to feed e.g. the type annotation of assignments;
        the default knows no types.
        :param name: name of the variable
        :return: the declared type, normalized (empty when unknown)
        """
        maybe_unused(name)
        return ''

    def type_options(self) -> IList[tuple[string, string]]:
        """
        The options the kit offers for the type field of assignments:
        (display text, type key) pairs in display order; the assignment always
        prepends the empty option and stores the chosen key in its archive.
        Kits override this to customize the selection; the default offers
        nothing, leaving the assignment its built-in C scalar types.
        :return: the offered options (empty defers to the assignment's default)
        """
        return []
