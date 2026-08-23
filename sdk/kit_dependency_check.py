# -*- coding: utf-8 -*-
"""
Headless check of kit dependency resolution and version constraints:

- ``Version.satisfy`` / ``KitMetadata.satisfy_version`` honor the inclusive
  lowest/highest bounds, missing bounds and impossible windows;
- the bundled kits declare the expected inter-kit dependencies (fluent needs
  clk and cbased) and every dependency resolves once all kits are imported;
- the delegation buffers resolve regardless of the kit importation order:
  importing the dependent kit first parks its delegations in the buffer and
  drains them when the remaining kits arrive (two child processes exercise
  the canonical and the reversed order with fresh singletons);
- re-importing an already imported kit is refused with ``KitImported``;
- ``Environment.satisfy`` reports ``KIT_VERSION_UNSATISFIED`` for a required
  kit whose version window the platform cannot meet and
  ``LANGUAGE_UNSUPPORTED`` for a target language no kit provides.
"""

import os
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from alias import *
from core.component import ComponentMetadata
from core.environment import Environment
from core.kit import Kit, KitManager, KitMetadata
from core.meta import AuthorInfo, SupportedLanguage, Version
from core.project import Project
from kits.fluent.fluent import UDF

_KIT_PATHS: Final[IDictionary[string, string]] = {
    'cbased': os.path.join(_root, 'kits', 'cbased'),
    'common': os.path.join(_root, 'kits', 'common'),
    'fluent': os.path.join(_root, 'kits', 'fluent'),
}


def _run_child(scenario: string) -> void:
    """Re-execute this script as a child so the KitManager singleton is fresh."""
    env = os.environ.copy()
    env['EC_KIT_SCENARIO'] = scenario
    result = subprocess.run([sys.executable, os.path.abspath(__file__)],
                            cwd=_root, env=env, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=180)
    sys.stdout.write(result.stdout)
    assert result.returncode == 0, f'{scenario} scenario failed:\n{result.stderr}'
    assert 'SCENARIO OK' in result.stdout, f'{scenario} scenario produced no confirmation'
    print(f'import order ok: {scenario}')


def _child_main() -> void:
    scenario = os.environ.get('EC_KIT_SCENARIO', 'canonical')
    env = Environment()
    order = ('cbased', 'common', 'fluent') if scenario == 'canonical' \
        else ('fluent', 'common', 'cbased')

    for index, name in enumerate(order):
        env.import_kit(_KIT_PATHS[name])
        if scenario == 'reversed' and index == 0:
            # Fluent arrived before the kits it delegates to: every delegation
            # must park in the buffer and stay invisible to building
            fluent_kit = env.kit_manager['fluent']
            assert fluent_kit.delegation_buffer, \
                'delegations resolved before their targets were imported'
            try:
                env.kit_manager.lookup('clk.br')
                raise AssertionError('clk resolvable before the common kit was imported')
            except KitManager.KitNotFoundError:
                pass
            print('reversed order: delegations buffered while dependencies are missing')

    # All kits imported: every buffer drains and every UDF delegation resolves
    manager = env.kit_manager
    assert len(manager) == 3, len(manager)
    for kit in manager:
        assert not kit.delegation_buffer, \
            f'kit {kit.meta.name} keeps {len(kit.delegation_buffer)} unresolved delegations'
    checked = 0
    for meta in manager['clk']:
        if meta.delegations.valid(UDF) == ComponentMetadata.Delegation.VALID:
            checked += 1
    assert checked >= 10, f'only {checked} clk components gained a UDF delegation'
    print(f'{scenario} order: buffers drained, {checked} clk delegations valid')

    # Every declared inter-kit dependency is actually registered
    for kit in manager:
        for dep in kit.meta.dependencies:
            assert dep in manager, f'{kit.meta.name} declares an unimported dependency: {dep}'
    assert manager['fluent'].meta.dependencies == ['clk', 'cbased'], \
        manager['fluent'].meta.dependencies

    # Re-importing an already imported kit is refused, nothing duplicated
    try:
        manager.import_package_kit(_KIT_PATHS['common'])
        raise AssertionError('duplicate import was accepted')
    except KitManager.KitImportError as e:
        assert e.error_code == KitManager.KitImportError.ErrorCode.KitImported, e.error_code
    assert len(manager) == 3, len(manager)
    print('duplicate import refusal ok')

    print('SCENARIO OK')


def _parent_main() -> void:
    # 1. Version windows: bounds are inclusive, missing bounds never constrain
    v5 = Version(0, 0, 5)
    assert Version.satisfy(v5, null, null)
    assert Version.satisfy(v5, Version(0, 0, 5), null)
    assert Version.satisfy(v5, null, Version(0, 0, 5))
    assert not Version.satisfy(v5, Version(0, 0, 6), null)
    assert not Version.satisfy(v5, null, Version(0, 0, 4))
    assert Version.satisfy(v5, Version(0, 0, 1), Version(0, 0, 9))
    assert not Version.satisfy(v5, Version(0, 0, 6), Version(0, 0, 9))
    assert not Version.satisfy(v5, Version(0, 0, 8), Version(0, 0, 4))  # impossible window
    author = AuthorInfo('EngineerCoder Project', 'zzr4028@163.com', 'Test author')
    meta = KitMetadata('probe', 'Probe', 'version window probe', Version(0, 0, 5), [],
                       Version(0, 0, 3), Version(0, 0, 7), [], [author], [])
    assert meta.satisfy_version(Version(0, 0, 3))
    assert meta.satisfy_version(Version(0, 0, 7))
    assert meta.satisfy_version(Version(0, 0, 5))
    assert not meta.satisfy_version(Version(0, 0, 2))
    assert not meta.satisfy_version(Version(0, 0, 8))
    print('version constraints ok')

    # 2. Import order independence: fresh singleton per child process
    _run_child('canonical')
    _run_child('reversed')

    env = Environment()
    for name in ('cbased', 'common', 'fluent'):
        env.import_kit(_KIT_PATHS[name])

    # 3. The bundled kits satisfy the current platform version
    for kit in env.kit_manager:
        assert env.satisfy_kit_version(kit), kit.meta.name
    print('platform version satisfaction ok')

    # 4. Environment.satisfy: happy path, unsatisfiable kit version, missing language
    project = Project('dependency-check', UDF)
    env.project = project
    assert env.satisfy(project) == Environment.SatisfactionError.SATISFIED

    future_kit = Kit.create_empty(KitMetadata(
        'future', 'Future Kit', 'requires a newer platform', Version(0, 0, 1), [],
        Version(99, 0, 2), null, [], [author], []))
    project.required_kits.append(future_kit)
    assert env.satisfy(project) == Environment.SatisfactionError.KIT_VERSION_UNSATISFIED
    assert not env.satisfy_kit_version(future_kit)
    project.required_kits.remove(future_kit)

    project.target_lang = SupportedLanguage('unsupported', 'Unsupported', 'n/a')
    assert env.satisfy(project) == Environment.SatisfactionError.LANGUAGE_UNSUPPORTED
    project.target_lang = UDF
    assert env.satisfy(project) == Environment.SatisfactionError.SATISFIED
    print('environment satisfaction ok')

    # 5. Component name plumbing guards the dependency lookups
    assert KitManager.split_name('fluent.source') == ('fluent', 'source')
    assert KitManager.merge_names('clk', 'br') == 'clk.br'
    for bad in ('no-separator', 'a.b.c', '1bad.name', 'name.1bad'):
        try:
            KitManager.split_name(bad)
            raise AssertionError(f'invalid component name accepted: {bad}')
        except KitManager.InvalidComponentNameError:
            pass
    print('name plumbing ok')

    print('ALL PASSED')


if __name__ == '__main__':
    if os.environ.get('EC_KIT_SCENARIO'):
        _child_main()
    else:
        _parent_main()
