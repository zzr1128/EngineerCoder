# -*- coding: utf-8 -*-

import json
import warnings
from pathlib import Path

from alias import *
from path import BASE_DIR


@final
class Preferences:
    """
    Application-wide user preferences (theme, language, editor appearance...).
    Persisted as JSON in ``config/preferences.json``; missing keys fall back
    to ``Defaults``. Project-scoped settings live in ``Project`` instead.
    """
    Path = BASE_DIR / 'config' / 'preferences.json'
    Defaults: IDictionary[string, Any] = {
        'theme': 'light.json',
        'language': 'zh_CN',
        'editor_font_size': 10,
        'completion_list_width': 280,
        'completion_detail_width': 260,
        'completion_max_height': 240,
    }

    def __init__(self, path: Nullable[Path] = null):
        """
        :param path: file to load from / save to; defaults to ``Preferences.Path``
        """
        self.path: Path = Preferences.Path if path is null else path
        # Only explicitly set entries; ``get`` falls back to ``Defaults``
        self._values: IDictionary[string, Any] = {}
        self.load()

    def load(self) -> void:
        """
        (Re)load from ``self.path``. A missing or invalid file silently falls
        back to the defaults so the application always boots.
        """
        self._values = {}
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except Exception as e:
            warnings.warn(f'Invalid preferences file {self.path}: {e}; using defaults', UserWarning, stacklevel=2)
            return
        if not isinstance(data, dict):
            warnings.warn(f'Invalid preferences file {self.path}: not a JSON object; using defaults', UserWarning, stacklevel=2)
            return
        self._values = data

    def save(self) -> void:
        """
        Write the explicitly set entries to ``self.path``.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self._values, f, ensure_ascii=False, indent=4)

    def contains(self, key: string) -> bool:
        """
        :return: True if the key was explicitly set (in the file or via ``set``),
            not merely defaulted
        """
        return key in self._values

    def get(self, key: string, default: Any = null) -> Any:
        if key in self._values:
            return self._values[key]
        if key in Preferences.Defaults:
            return Preferences.Defaults[key]
        return default

    def set(self, key: string, value: Any) -> void:
        """
        Set an entry in memory; call ``save`` to persist it.
        """
        self._values[key] = value

    def available_languages(self) -> IList[string]:
        """
        :return: languages with a compiled catalog under ``res/locale``,
            e.g. ``['en_US', 'zh_CN']``
        """
        languages: IList[string] = []
        locale_dir = BASE_DIR / 'res' / 'locale'
        if locale_dir.is_dir():
            for d in sorted(locale_dir.iterdir()):
                if d.is_dir() and (d / 'LC_MESSAGES').is_dir():
                    languages.append(d.name)
        return languages or ['en_US']

    def available_themes(self) -> IList[IDictionary[string, Any]]:
        """
        :return: metadata of the bundled (``res/themes``) and user
            (``config/themes``) themes; a user theme of the same file name
            overrides the bundled one. Each entry carries ``name`` (resource
            file name), ``display_name`` (per-language names) and ``built_in``
            (bundled themes cannot be deleted by the user)
        """
        from core.theme import Theme  # Deferred: theme pulls Qt in
        entries: IDictionary[string, IDictionary[string, Any]] = {}
        themes_dir = BASE_DIR / 'res' / 'themes'
        if themes_dir.is_dir():
            for f in sorted(themes_dir.glob('*.json')):
                entries[f.name] = {'name': f.name, 'display_name': {}, 'built_in': True}
        user_dir = Theme.user_themes_dir()
        if user_dir.is_dir():
            for f in sorted(user_dir.glob('*.json')):
                entries[f.name] = {'name': f.name, 'display_name': {}, 'built_in': False}
        themes: IList[IDictionary[string, Any]] = []
        for entry in entries.values():
            try:
                entry['display_name'] = Theme.from_resource(entry['name']).display_name
            except Exception:
                pass  # Listed but unloadable; the UI shows the raw name
            themes.append(entry)
        return themes

    def __repr__(self) -> string:
        return f'Preferences<{self.path.name}: {len(self._values)} explicit entries>'
