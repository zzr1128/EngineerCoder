# -*- coding: utf-8 -*-
"""
Headless check of the user theme storage APIs (``core.theme``):

- ``Theme.user_themes_dir`` points at ``config/themes``;
- ``Theme.create_new`` builds an unsaved theme on the default theme's colors
  (deep copy: later edits do not leak into the source);
- ``Theme.duplicate`` copies an existing theme given by file name or object;
- ``save_to_user`` writes into ``config/themes``, invalidates the resource
  cache and shows up in ``Preferences.available_themes`` as non-bundled;
- a user theme of the same file name overrides the bundled theme while the
  file exists; deleting it restores the bundled one;
- ``delete_user`` removes only user themes and refuses missing or bundled names;
- invalid theme names (blank, path separators) are rejected;
- the environment boots against a user theme configured in the preferences.
"""

import json
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtGui import QColor

from alias import *
from core.environment import Environment
from core.preferences import Preferences
from core.resource import Resource
from core.theme import Theme
from path import BASE_DIR

# User theme files this check creates; removed again in ``main``'s finally block
_CHECK_FILES: IList[string] = ['check_theme.json', 'check_renamed.json',
                               'check_dup.json', 'light.json']


def _cleanup_user_files() -> None:
    for name in _CHECK_FILES:
        (Theme.user_themes_dir() / name).unlink(missing_ok=True)
        Resource._cache.get('themes', {}).pop(name, None)


def _themes_by_name() -> IDictionary[string, IDictionary[string, Any]]:
    return {t['name']: t for t in Preferences().available_themes()}


def main() -> void:
    try:
        _run()
    finally:
        _cleanup_user_files()
        Environment()  # Re-run init against the real preferences


def _run() -> void:
    # 1. The user theme directory is config/themes
    assert Theme.user_themes_dir() == BASE_DIR / 'config' / 'themes'
    print('user themes dir ok')

    # 2. create_new builds an unsaved theme on the default theme's colors
    theme = Theme.create_new('check_theme', {'en_US': 'Check', 'zh_CN': '检查'})
    assert theme.name == 'check_theme', theme.name
    assert theme.display_name == {'en_US': 'Check', 'zh_CN': '检查'}
    base = Theme.from_resource(str(Preferences.Defaults['theme']))
    assert serialize(theme.colors) == serialize(base.colors), 'defaults not copied'
    theme.colors.background = QColor('#123456')
    assert base.colors.background.name() != '#123456', 'colors are not a deep copy'
    # Accepts a name given with the .json extension as well
    assert Theme.create_new('check_theme.json', {}).name == 'check_theme'
    print('create_new ok')

    # 3. save_to_user writes config/themes/<name>.json and evicts the cache
    path = theme.save_to_user()
    assert path == Theme.user_themes_dir() / 'check_theme.json', path
    assert path.is_file()
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert raw['name'] == 'check_theme' and raw['display_name']['zh_CN'] == '检查'
    loaded = Theme.from_resource('check_theme.json')
    assert loaded.name == 'check_theme'
    assert loaded.colors.background.name() == '#123456'
    assert Theme.from_resource('check_theme.json') is loaded, 'cache never hits'
    # Saving under an explicit file name renames the theme
    renamed = Theme.duplicate(theme, 'placeholder', {})
    renamed_path = renamed.save_to_user('check_renamed.json')
    assert renamed_path.name == 'check_renamed.json' and renamed.name == 'check_renamed'
    print('save_to_user ok')

    # 4. available_themes lists user themes as non-bundled, bundled ones as bundled
    by_name = _themes_by_name()
    assert by_name['light.json']['built_in'] is True, by_name['light.json']
    entry = by_name['check_theme.json']
    assert entry['built_in'] is False, entry
    assert entry['display_name'] == {'en_US': 'Check', 'zh_CN': '检查'}, entry
    print('available_themes merge ok')

    # 5. duplicate copies colors deeply, from a file name or a theme object
    dup = Theme.duplicate('check_theme.json', 'check_dup', {'en_US': 'Dup'})
    assert dup.name == 'check_dup'
    assert serialize(dup.colors) == serialize(theme.colors)
    dup.colors.background = QColor('#654321')
    assert theme.colors.background.name() == '#123456', 'duplicate leaked back'
    dup_from_object = Theme.duplicate(theme, 'check_dup2', {})
    assert dup_from_object.name == 'check_dup2'
    assert serialize(dup_from_object.colors) == serialize(theme.colors)
    print('duplicate ok')

    # 6. A same-named user theme overrides the bundled one while it exists
    override = Theme.duplicate('light.json', 'light', {'en_US': 'User Light'})
    override.colors.background = QColor('#000102')
    override.save_to_user()  # config/themes/light.json, evicts the cached built-in
    shadowed = Theme.from_resource('light.json')
    assert shadowed.colors.background.name() == '#000102', 'user theme did not override'
    assert _themes_by_name()['light.json']['built_in'] is False
    Theme.delete_user('light.json')
    restored = Theme.from_resource('light.json')
    assert restored.name == 'Light', restored.name
    assert serialize(restored.colors) == serialize(base.colors), 'built-in not restored'
    assert _themes_by_name()['light.json']['built_in'] is True
    print('user override + restore ok')

    # 7. delete_user refuses missing names and bundled themes
    for missing in ('no_such_theme.json', 'light.json'):
        try:
            Theme.delete_user(missing)
            raise AssertionError(f'delete_user accepted {missing!r}')
        except Resource.ResourceError as e:
            assert e.code == Resource.ResourceErrorCode.I2002, e.code
    assert (Resource.resource_path('themes') / 'light.json').is_file(), \
        'bundled theme was touched'
    print('delete_user protection ok')

    # 8. Invalid names are rejected; traversal never escapes the theme dirs
    for bad in ('', '   ', 'a/b', 'a\\b'):
        try:
            Theme.create_new(bad, {})
            raise AssertionError(f'invalid name accepted: {bad!r}')
        except ValueError:
            pass
        try:
            Theme.delete_user(bad)
            raise AssertionError(f'delete_user accepted: {bad!r}')
        except ValueError:
            pass
    for traversal in ('../light.json', 'themes/light.json'):
        try:
            Theme.from_resource(traversal)
            raise AssertionError(f'traversal accepted: {traversal!r}')
        except Resource.ResourceError as e:
            assert e.code == Resource.ResourceErrorCode.I2002, e.code
    print('name validation ok')

    # 9. The environment boots against a user theme from the preferences
    import core.environment as env_module
    original_preferences = env_module.Preferences
    with tempfile.TemporaryDirectory() as tmp:
        class _UserThemePreferences(original_preferences):
            def __init__(self):
                super().__init__(Path(tmp) / 'preferences.json')

        bogus = _UserThemePreferences()
        bogus.set('theme', 'check_theme.json')
        bogus.save()
        env_module.Preferences = _UserThemePreferences
        try:
            env = Environment()
            assert env.theme.name == 'check_theme', env.theme.name
            assert env.theme.colors.background.name() == '#123456'
        finally:
            env_module.Preferences = original_preferences
    print('environment user theme ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
