# -*- coding: utf-8 -*-
"""
Headless check of theme loading (``core.theme.Theme``):

- ``Theme.from_resource`` loads the bundled light theme with every color group
  intact and the exact color values the JSON declares;
- the resource cache is populated, so repeated loads return the cached object;
- a missing theme file is refused with ``I2002``, malformed JSON with ``I2004``
  and structurally invalid content (missing color member) with ``I2005``;
- the theme round-trips through ``__serialize__``/``__deserialize__``;
- a misconfigured theme name in the preferences must not break the environment
  boot: it falls back to the default theme.
"""

import json
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

import tempfile
from pathlib import Path

from PySide6.QtGui import QColor

from alias import *
from core.environment import Environment
from core.resource import Resource
from core.theme import Theme


def main() -> void:
    # 1. The bundled light theme loads with every color group intact
    theme = Theme.from_resource('light.json')
    assert theme.name == 'Light', theme.name
    assert theme.display_name.get('en_US') == 'Light', theme.display_name
    assert theme.display_name.get('zh_CN'), theme.display_name
    colors = theme.colors
    assert colors.background.isValid() and colors.primary.isValid()
    assert colors.secondary.isValid() and colors.tertiary.isValid()
    assert colors.side.isValid() and colors.foreground.isValid()
    assert colors.selected.isValid()
    assert colors.components, 'theme declares no component color groups'
    for group in colors.components:
        assert group and all(color.isValid() for color in group), group
    print('light theme load ok:', len(colors.components), 'component color groups')

    # 2. The colors match the JSON on disk (no silent substitution)
    with open(Resource.resource_path('themes', 'light.json'), 'r', encoding='utf-8') as f:
        raw = json.load(f)['colors']
    assert colors.background.name() == QColor(raw['background']).name()
    assert colors.foreground.name() == QColor(raw['foreground']).name()
    assert [c.name() for c in colors.components[0]] == \
        [QColor(c).name() for c in raw['components'][0]]
    print('color values ok')

    # 3. The resource cache is populated: repeated loads return the same object
    assert Theme.from_resource('light.json') is theme, 'theme cache never hits'
    print('theme cache ok')

    # 4. A missing theme is refused (I2002)
    try:
        Theme.from_resource('no-such-theme.json')
        raise AssertionError('missing theme was accepted')
    except Resource.ResourceError as e:
        assert e.code == Resource.ResourceErrorCode.I2002, e.code
    print('missing theme rejection ok')

    themes_dir = Resource.resource_path('themes')
    broken_path = themes_dir / '_check_broken.json'
    invalid_path = themes_dir / '_check_invalid.json'
    try:
        # 5. Malformed JSON is refused (I2004)
        broken_path.write_text('{ this is not json', encoding='utf-8')
        try:
            Theme.from_resource('_check_broken.json')
            raise AssertionError('malformed theme was accepted')
        except Resource.ResourceError as e:
            assert e.code == Resource.ResourceErrorCode.I2004, e.code
        print('malformed theme rejection ok')

        # 6. Structurally invalid content (missing color member) is refused (I2005)
        invalid_path.write_text(json.dumps({'name': 'x', 'display_name': {}}), encoding='utf-8')
        try:
            Theme.from_resource('_check_invalid.json')
            raise AssertionError('invalid theme content was accepted')
        except Resource.ResourceError as e:
            assert e.code == Resource.ResourceErrorCode.I2005, e.code
        print('invalid content rejection ok')
    finally:
        broken_path.unlink(missing_ok=True)
        invalid_path.unlink(missing_ok=True)
        Resource._cache.get('themes', {}).pop('_check_broken.json', None)
        Resource._cache.get('themes', {}).pop('_check_invalid.json', None)

    # 7. Serialization round trip preserves every color
    data = serialize(theme)
    restored = deserialize(Theme, data)
    assert restored.name == theme.name
    assert restored.display_name == theme.display_name
    assert serialize(restored.colors) == serialize(theme.colors)
    print('theme round trip ok')

    # 8. Display name resolution: exact language wins, en_US is the fallback,
    #    the raw name is the last resort
    assert theme.get_display_name('zh_CN') == theme.display_name['zh_CN']
    assert theme.get_display_name('fr_FR') == theme.display_name['en_US']
    bare = Theme('bare', {}, theme.colors)
    assert bare.get_display_name('zh_CN') == 'bare'
    print('display name resolution ok')

    # 9. A misconfigured theme name must not break the environment boot:
    #    the environment falls back to the default theme
    import core.environment as env_module
    original_preferences = env_module.Preferences
    with tempfile.TemporaryDirectory() as tmp:
        class _BogusPreferences(original_preferences):
            def __init__(self):
                super().__init__(Path(tmp) / 'preferences.json')

        bogus = _BogusPreferences()
        bogus.set('theme', 'no-such-theme.json')
        bogus.save()
        env_module.Preferences = _BogusPreferences
        try:
            env = Environment()
            assert env.theme.name == 'Light', env.theme.name
            assert env.preferences.get('theme') == 'no-such-theme.json'
        finally:
            env_module.Preferences = original_preferences
            Environment()  # Re-run init against the real preferences
    print('environment fallback ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
