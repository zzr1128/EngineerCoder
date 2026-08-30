# -*- coding: utf-8 -*-
"""
Headless check of the application preferences backend:

- ``Preferences`` loads/saves ``config/preferences.json`` with per-key defaults;
- invalid files fall back to the defaults instead of crashing;
- ``available_languages`` / ``available_themes`` enumerate the UI choices;
- ``get_language`` honors the legacy ``config/language`` file while no
  preference is stored;
- ``set_language`` persists the choice and hot-swaps the global ``_`` function
  and the running environment's ``local_language``.
"""

import os
import sys
import tempfile
import warnings

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in (_root, os.path.join(_root, 'core'), os.path.join(_root, 'interface'),
             os.path.join(_root, 'sdk')):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from pathlib import Path

from PySide6.QtWidgets import QApplication

from alias import *
import core.localization as localization
from core.environment import Environment
from core.preferences import Preferences


def main() -> void:
    app = QApplication(sys.argv)
    maybe_unused(app)  # Keep the application instance alive during the check
    env = Environment()

    # 1. Defaults apply when no file exists; `contains` distinguishes them
    with tempfile.TemporaryDirectory() as tmp:
        prefs = Preferences(Path(tmp) / 'nested' / 'preferences.json')
        assert prefs.get('theme') == 'light.json'
        assert prefs.get('language') == 'zh_CN'
        assert prefs.get('editor_font_size') == 10
        assert prefs.get('completion_list_width') == 280
        assert prefs.get('completion_detail_width') == 260
        assert prefs.get('completion_max_height') == 240
        assert prefs.get('nonexistent', 'fallback') == 'fallback'
        assert not prefs.contains('theme')

        # 2. set/save/load round trip
        prefs.set('theme', 'dark.json')
        prefs.set('editor_font_size', 14)
        prefs.save()
        reloaded = Preferences(prefs.path)
        assert reloaded.get('theme') == 'dark.json'
        assert reloaded.get('editor_font_size') == 14
        assert reloaded.contains('theme')
        assert reloaded.get('language') == 'zh_CN'  # Unset keys keep their default

        # 3. Invalid content falls back to defaults with a warning, never crashes
        prefs.path.write_text('{not json', encoding='utf-8')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            broken = Preferences(prefs.path)
        assert broken.get('theme') == 'light.json'
        prefs.path.write_text('[1, 2, 3]', encoding='utf-8')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            broken = Preferences(prefs.path)
        assert broken.get('theme') == 'light.json'
    print('preferences load/save ok')

    # 4. Enumeration of the choices the Settings dialog presents
    prefs = Preferences()
    languages = prefs.available_languages()
    assert 'zh_CN' in languages and 'en_US' in languages, languages
    themes = prefs.available_themes()
    theme_names = [t['name'] for t in themes]
    assert 'light.json' in theme_names, theme_names
    light = next(t for t in themes if t['name'] == 'light.json')
    assert isinstance(light['display_name'], dict) and light['display_name'], light
    print('preference enumeration ok')

    # 5. Environment integration: preferences attached, theme from preferences
    assert isinstance(env.preferences, Preferences)
    assert env.theme.name == 'Light'
    print('environment integration ok')

    # 6. Legacy config/language fallback while no language preference is stored
    prefs_path = Preferences.Path
    backup = prefs_path.read_text(encoding='utf-8') if prefs_path.is_file() else null
    original_language = localization.language
    try:
        if prefs_path.is_file():
            prefs_path.unlink()
        legacy = (Path(_root) / 'config' / 'language').read_text(encoding='utf-8').strip()
        assert localization.get_language() == legacy
        # set_language persists the choice and hot-swaps the translation
        localization.set_language('en_US')
        assert prefs_path.is_file(), 'set_language must persist the preference'
        assert Preferences().get('language') == 'en_US'
        assert localization.language == 'en_US'
        assert localization.get_language() == 'en_US'
        assert localization._('I2001') == 'Unresolved resource error.'
        assert env.local_language == 'en_US'
        # Modules that imported `_` earlier resolve through the same proxy
        from core.localization import _ as imported_underscore
        assert imported_underscore('I2002') == 'Resource not found: {1}'
        localization.set_language('zh_CN')
        assert localization._('I2001') == '未知的资源错误。'
        assert env.local_language == 'zh_CN'
        # Unknown languages are rejected without touching the stored preference
        try:
            localization.set_language('xx_XX')
            raise AssertionError('set_language accepted an unavailable language')
        except ValueError:
            pass
        assert Preferences().get('language') == 'zh_CN'
    finally:
        if backup is not null:
            prefs_path.write_text(backup, encoding='utf-8')
        elif prefs_path.is_file():
            prefs_path.unlink()
        if localization.language != original_language:
            localization.set_language(original_language)
            if backup is null and prefs_path.is_file():
                prefs_path.unlink()
    print('language switching ok')

    print('ALL PASSED')


if __name__ == '__main__':
    main()
