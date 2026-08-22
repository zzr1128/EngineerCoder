# -*- coding: utf-8 -*-
"""
Completion analyzer of the Ansys Fluent kit.

The analyzer walks the component trees of the loaded project's scripts and
derives completion suggestions that no component of its own provides. It
offers the target name of every assignment (``set``) component and the
counter name of every count loop (``for``) component as a ``variable``
completion, prefixed with the variable glyph and described by its nature
(local variable, global variable or loop variable). On top of that, kit
modules contribute scope-bound suggestions through
``register_scope_contributor``: the macro components register the identifiers
their parameters declare this way (visible inside the macro only), and any
provider may attach suggestions to any scope up to the translation unit.

The analyzer is scope-aware: an assignment carries a visibility annotation
(``auto`` unless restricted to the local scope, see ``kits.common.assign``).
A variable restricted to its local scope is only suggested inside the block
that introduces it and at the siblings sharing that block, ``scoped`` names
(e.g. macro parameters) only inside the subtree of their introducer, while an
``auto`` variable is suggested everywhere of its script (its declaration is
lifted to the smallest namespace shared by all references,
see ``kits.fluent.udf``). Count-loop counters are inherently local. When the
requesting edit cannot be located in any script (detached edits), the
analyzer falls back to the whole-project view. An introducer's own name field
never suggests the name being written in it.

On top of scope-bound suggestions, kit modules contribute context-bound
components through ``register_context_completion``: suggestions that only
compile inside components providing certain semantic roles (the ``DEFINE_*``
macros and the traversal loops tag their declared identifiers with roles,
see ``ContextKey`` in ``kits.fluent.udf``). The analyzer offers a context
completion only when the components hosting the requesting edit provide every
role it requires, so e.g. a cell field access completes inside a source-term
macro or a cell loop, and never at a contextless position.

The analyzer also answers type lookups (``lookup_type``) for the assignment's
type field: a C declaration in the scripts' free text wins, then a constant
assignment of the same name, then the type annotation another assignment of
the name already carries. The options that field offers come from the
analyzer as well (``type_options``), so the kit customizes the selection.
"""

import re

from alias import *
from core.completer import Completer, Completion
from core.component import Component, ComponentMetadata
from core.environment import Environment
from core.kit import KitManager
from kits.fluent.localization import _
from kits.fluent.udf import _Declaration

# Descriptions of the introduced variables, shown in the popup detail pane
lt_local_var: Final[string] = _('desc_local_var')
lt_auto_var: Final[string] = _('desc_auto_var')
lt_counter_var: Final[string] = _('desc_counter_var')

# Type options of the assignment's type field: the C scalar type families UDF
# compiles to (the display texts localize, the keys enter the archives)
lt_type_real: Final[string] = _('type_real')
lt_type_int: Final[string] = _('type_int')
lt_type_char: Final[string] = _('type_char')

# Scope contributors the kit modules register (see ``register_scope_contributor``)
_scope_contributors: IList[Callable[[Component], IList[Completion]]] = []

# Context completions the kit modules register (see ``register_context_completion``):
# (suggestion, semantic roles the hosting components must provide) pairs
_context_completions: IList[tuple[Completion, tuple[string, ...]]] = []


def register_scope_contributor(contributor: Callable[[Component], IList[Completion]]) -> void:
    """
    Register a provider that contributes suggestions to the scopes the
    project's components open: the analysis presents it every component of
    every script, and the suggestions it returns count as introduced by that
    component (filtered by their ``visibility`` annotation like the built-in
    ones, deduplicated against the other introducers). Kit modules use this
    to add variables or other suggestions a component brings into its scope:
    macro parameters into the macro body, globals into a translation unit...
    :param contributor: called with each component; returns what it introduces
    """
    if contributor not in _scope_contributors:
        _scope_contributors.append(contributor)


def register_context_completion(completion: Completion, required_roles: IEnumerable[string]) -> void:
    """
    Register a suggestion the analyzer presents only inside components that
    provide every required semantic role: the components declaring identifiers
    (the ``DEFINE_*`` macros, the traversal loops) tag them with roles and the
    hosting chain of the requesting edit decides which suggestions take part
    (see ``ContextKey`` in ``kits.fluent.udf`` and ``complete``).
    :param completion: the suggestion (it carries the component to insert)
    :param required_roles: semantic roles the hosting components must provide
    """
    entry = (completion, tuple(required_roles))
    if entry not in _context_completions:
        _context_completions.append(entry)
    if completion.component_name:
        # The component palette lists the context-gated components as draggable
        # entries too: it reads the insertion keyword off the manager's registry
        KitManager.instance().add_context_completion(completion.keyword, completion.component_name)


class FluentAnalyzer(Completer):
    """
    Completer of the Ansys Fluent kit.

    It inspects the component trees rooted at the scripts' translation units and
    collects the variables the project introduces (assignment targets and count
    loop counters); each variable is offered as a ``Variable``-kind completion
    carrying the variable name as its keyword and its visibility annotation.
    """

    # Interface attribute holding the variable name a component introduces
    _NAME_FIELDS: Final[IDictionary[string, string]] = {
        'assign': 'edit_name',  # The assignment target
        'for': 'edit_counter',  # The count loop counter
    }

    def complete(self, at: Any = null) -> IList[Completion]:
        """
        Derive the variable completions of the loaded project.
        :param at: the edit requesting the completion; the suggestions are then
            restricted to the variables visible at that edit (see the module
            documentation); ``null`` asks for the whole-project view
        :return: one ``Variable``-kind completion per distinct visible name
        """
        completions: IList[Completion] = []
        seen: HashSet[string] = set()
        # The name being written in an introducer's own name field must never
        # suggest itself, even though the introducer already carries it
        owner = self._name_owner(at)
        if at is not null:
            # Scope-aware: only the script hosting the requesting edit contributes
            for script in self.project.scripts:
                chain = self._host_chain(script.tu, at)
                if chain is not null:
                    self._collect(script.tu, completions, seen, chain, owner,
                                  self._parent_map(script.tu))
                    self._collect_context(completions, chain)
                    return completions
        # Whole-project view, or the requesting edit could not be located
        # (detached edits): every introduced name is suggested
        for script in self.project.scripts:
            self._collect(script.tu, completions, seen, null, owner, null)
        return completions

    def lookup_type(self, name: string) -> string:
        """
        Look up the declared type of a variable the project defines: a C
        declaration in the scripts' free text (``int counter = 0;``...), a
        constant assignment of the same name, or the type annotation another
        assignment of the name already carries. Looked up in that order.
        :param name: name of the variable
        :return: the declared type, normalized (empty when unknown)
        """
        name = name.strip()
        if not name:
            return ''
        pattern = re.compile(rf'\b((?:(?:const|static|extern|unsigned|signed|volatile|struct)\s+)*'
                             rf'(?:int|real|float|double|char|bool|long|short|size_t)\s*\**)\s*'
                             rf'{re.escape(name)}\s*(?:=[^=]|\[|;|,)')
        for script in self.project.scripts:
            declared = self._declared_type(script.tu, pattern)
            if declared:
                return declared
            if self._const_assign_defines(script.tu, name):
                return 'const real'
            annotated = self._assign_type(script.tu, name)
            if annotated:
                return annotated
        return ''

    @final
    def _declared_type(self, component: Component, pattern: re.Pattern) -> string:
        """Depth-first scan of every edit text for a declaration the pattern matches."""
        edits = self._nested_edits(component)
        for edit in edits:
            match = pattern.search(edit.toPlainText())
            if match is not null:
                return ' '.join(match.group(1).split())
        for edit in edits:
            for child in list(edit.inserted_components):
                declared = self._declared_type(child, pattern)
                if declared:
                    return declared
        return ''

    @final
    def _const_assign_defines(self, component: Component, name: string) -> bool:
        """Whether a constant assignment of the component tree defines the name."""
        if component.meta().name == 'assign' \
                and component.interface.check_constant.isChecked() \
                and self._introduced_name(component, 'edit_name') == name:
            return True
        for edit in self._nested_edits(component):
            for child in list(edit.inserted_components):
                if self._const_assign_defines(child, name):
                    return True
        return False

    @final
    def _assign_type(self, component: Component, name: string) -> string:
        """The type annotation the first assignment of the name already carries."""
        if component.meta().name == 'assign' \
                and self._introduced_name(component, 'edit_name') == name:
            # noinspection broad-exception
            try:
                type_field = component.interface.edit_type
                annotated = type_field.currentData() if hasattr(type_field, 'currentData') \
                    else type_field.text()
                if annotated:
                    return string(annotated)
            except Exception:
                pass
        for edit in self._nested_edits(component):
            for child in list(edit.inserted_components):
                annotated = self._assign_type(child, name)
                if annotated:
                    return annotated
        return ''

    def type_options(self) -> IList[tuple[string, string]]:
        """
        The type options the UDF kit offers for the assignment's type field:
        the C scalar type families (``real``/``int``/``char``), localized.
        :return: the offered options (the assignment prepends the empty one)
        """
        return [(lt_type_real, 'real'), (lt_type_int, 'int'), (lt_type_char, 'char')]

    @final
    def _collect(self, component: Component, completions: IList[Completion],
                 seen: HashSet[string], host_chain: Nullable[tuple[Component, ...]],
                 excluded: Nullable[Component],
                 parents: Nullable[IDictionary[Component, Nullable[Component]]]) -> void:
        """
        Recursively collect the variables introduced in the tree of a component:
        an assignment contributes its target name and a count loop its counter
        name; the traversal then descends into every nested visual code edit of
        the component.
        :param host_chain: the components from the script root down to the one
            hosting the requesting edit (null for the whole-project view); names
            invisible at the chain are skipped
        :param excluded: the introducer whose name field is being written; its
            own name never completes
        :param parents: the container of every component of the script (null
            with a null chain); it locates the siblings sharing a block
        """
        name_field = self._NAME_FIELDS.get(component.meta().name, null)
        if name_field is not null:
            name = self._introduced_name(component, name_field)
            visibility = self._visibility(component)
            if name and component is not excluded and name not in seen \
                    and self._visible(visibility, component, host_chain, parents):
                seen.add(name)
                completions.append(Completion(keyword=name,
                                              kind=ComponentMetadata.Kind.Variable,
                                              visibility=visibility,
                                              description=self._description(component, visibility)))
        # Scope-bound suggestions the kit contributes (macro parameters,
        # translation-unit globals...): they count as introduced by the
        # component the contributor attaches them to
        if component is not excluded:
            for contributor in _scope_contributors:
                for completion in contributor(component):
                    if completion.keyword and completion.keyword not in seen \
                            and self._visible(completion.visibility, component,
                                              host_chain, parents):
                        seen.add(completion.keyword)
                        completions.append(completion)
        for edit in self._nested_edits(component):
            for child in list(edit.inserted_components):
                self._collect(child, completions, seen, host_chain, excluded, parents)

    @staticmethod
    def _context_roles(chain: tuple[Component, ...]) -> HashSet[string]:
        """
        :return: the semantic roles the components hosting the requesting edit
            provide: the union of the ``context_roles`` every component of the
            chain declares (components without the notion contribute nothing)
        """
        roles: HashSet[string] = set()
        for component in chain:
            provider = getattr(type(component), 'context_roles', null)
            if provider is not null:
                # noinspection broad-exception
                try:
                    roles.update(provider())
                except Exception:
                    continue
        return roles

    @final
    def _collect_context(self, completions: IList[Completion],
                         chain: tuple[Component, ...]) -> void:
        """
        Append the context completions whose required roles the hosting chain
        provides (see ``register_context_completion``): they only compile where
        the identifiers they bind to are in scope, so they never surface
        elsewhere (and never in the whole-project view).
        """
        if not _context_completions:
            return
        roles = self._context_roles(chain)
        for completion, required in _context_completions:
            if all(role in roles for role in required):
                completions.append(completion)

    @staticmethod
    def _description(component: Component, visibility: string) -> string:
        """
        :return: how an introduced variable is described in the popup detail pane
        """
        if component.meta().name == 'for':
            return lt_counter_var
        return lt_auto_var if visibility == 'auto' else lt_local_var

    @staticmethod
    def _visible(visibility: string, introducer: Component,
                 host_chain: Nullable[tuple[Component, ...]],
                 parents: Nullable[IDictionary[Component, Nullable[Component]]]) -> bool:
        """
        :param visibility: annotation of the introduced variable
        :param introducer: the component introducing the variable
        :param host_chain: the components hosting the requesting edit (null for
            the whole-project view)
        :param parents: the container of every component of the script (null
            with a null chain)
        :return: whether the variable is visible at the requesting edit: ``auto``
            variables are visible across their whole script, locally scoped ones
            inside the block that introduces them and at the siblings of the
            component hosting the edit (they share the same C scope level),
            ``scoped`` ones only inside the subtree of their introducer
        """
        if host_chain is null or visibility == 'auto':
            return True
        if introducer in host_chain:
            return True
        if visibility != 'local':
            return False
        container = parents.get(introducer, null) if parents is not null else null
        return container is not null and container in host_chain

    @staticmethod
    def _visibility(component: Component) -> string:
        """
        :return: the visibility annotation of the variable a component introduces:
            assignments are ``auto`` unless restricted to the local scope (the
            restriction always holds for constants, since they declare in place);
            every other introducer (count-loop counters) is inherently ``local``
        """
        if component.meta().name == 'assign':
            # noinspection broad-exception
            try:
                interface = component.interface
                check_local = getattr(interface, 'check_local', null)
                if check_local is not null and not check_local.isChecked() \
                        and not interface.check_constant.isChecked():
                    return 'auto'
            except Exception:
                pass
        return 'local'

    @final
    def _host_chain(self, component: Component, edit: Any,
                    chain: tuple[Component, ...] = ()) -> Nullable[tuple[Component, ...]]:
        """
        Locate the visual code edit requesting the completion in the tree of a
        component.
        :param component: root of the tree being searched
        :param edit: the requesting edit
        :param chain: the components from the script root down to ``component``
        :return: the chain extended down to the component whose interface holds
            the edit, or null when the edit is not part of this tree
        """
        # noinspection broad-exception
        try:
            attributes = vars(component.interface)
        except TypeError:
            attributes = {}
        if any(value is edit for value in attributes.values()):
            return chain + (component,)
        for nested_edit in self._nested_edits(component):
            for child in list(nested_edit.inserted_components):
                found = self._host_chain(child, edit, chain + (component,))
                if found is not null:
                    return found
        return null

    @final
    def _parent_map(self, root: Component) -> IDictionary[Component, Nullable[Component]]:
        """
        :return: the container of every component of a script tree (null for the
            root itself); it locates the siblings sharing a block (see ``_visible``)
        """
        parents: IDictionary[Component, Nullable[Component]] = {}
        stack: IList[tuple[Component, Nullable[Component]]] = [(root, null)]
        while stack:
            component, container = stack.pop()
            parents[component] = container
            for nested_edit in self._nested_edits(component):
                for child in list(nested_edit.inserted_components):
                    stack.append((child, component))
        return parents

    @final
    def _name_owner(self, edit: Any) -> Nullable[Component]:
        """
        :return: the introducer whose name field is the given edit (the user is
            writing that name right now); null when the edit belongs elsewhere
        """
        if edit is null:
            return null
        for script in self.project.scripts:
            owner = self._find_name_owner(script.tu, edit)
            if owner is not null:
                return owner
        return null

    @final
    def _find_name_owner(self, component: Component, edit: Any) -> Nullable[Component]:
        name_field = self._NAME_FIELDS.get(component.meta().name, null)
        if name_field is not null:
            # noinspection broad-exception
            try:
                if getattr(component.interface, name_field, null) is edit:
                    return component
            except Exception:
                pass
        for nested_edit in self._nested_edits(component):
            for child in list(nested_edit.inserted_components):
                owner = self._find_name_owner(child, edit)
                if owner is not null:
                    return owner
        return null

    @staticmethod
    def _introduced_name(component: Component, name_field: string) -> string:
        """
        :param component: the component introducing a variable
        :param name_field: attribute of the interface holding the variable name
        :return: the introduced variable name (stripped), or an empty string when
            it is empty, embeds components (a member access names no plain
            variable), or cannot be resolved
        """
        # noinspection broad-exception
        try:
            edit = getattr(component.interface, name_field, null)
        except Exception:
            return ''
        if edit is null:
            return ''
        if getattr(edit, 'inserted_components', null):
            return ''
        # Visual code edits expose toPlainText; single-line edits expose text
        text = edit.toPlainText() if hasattr(edit, 'toPlainText') else edit.text()
        return text.replace('\uFFFC', '').strip()

    @staticmethod
    def _nested_edits(component: Component) -> IList[Any]:
        """
        :return: the visual code edits nested in the interface of a component,
            detected structurally (any interface attribute that hosts inserted
            components), so both layout-held and directly-held edits are found
        """
        edits: IList[Any] = []
        # noinspection broad-exception
        try:
            attributes = vars(component.interface)
        except TypeError:
            return edits
        for value in attributes.values():
            if hasattr(value, 'inserted_components'):
                edits.append(value)
        return edits


# Contribute the analyzer to the environment so the editors consult it while
# completing (instantiated against the loaded project on demand)
Environment.instance().register_completer(FluentAnalyzer)
