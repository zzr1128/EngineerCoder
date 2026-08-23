# -*- coding: utf-8 -*-

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor

from alias import *
from alias import IList
from core.resource import Resource
from path import BASE_DIR


class Theme:
    @dataclass
    class ThemeColor:
        components: IList[IList[QColor]]
        background: QColor
        primary: QColor
        secondary: QColor
        tertiary: QColor
        side: QColor
        foreground: QColor
        selected: QColor

        def __serialize__(self) -> IDictionary[string, Any]:
            return {
                'components': [[c.name() for c in l] for l in self.components],
                'background': self.background.name(),
                'primary': self.primary.name(),
                'secondary': self.secondary.name(),
                'tertiary': self.tertiary.name(),
                'side': self.side.name(),
                'foreground': self.foreground.name(),
                'selected': self.selected.name(),
            }

        @classmethod
        def __deserialize__(cls, data: IDictionary[string, Any]) -> Self:
            require_type(data, dict)
            require_member(data, 'components', 'background', 'primary', 'secondary', 'tertiary', 'side',
                           'foreground', 'selected')
            require_type(data['components'], list)
            require_type(data['background'], string)
            require_type(data['primary'], string)
            require_type(data['secondary'], string)
            require_type(data['tertiary'], string)
            require_type(data['side'], string)
            require_type(data['foreground'], string)
            require_type(data['selected'], string)
            components: IList[IList[QColor]] = []
            try:
                for l in data['components']:
                    if isinstance(l, string):  # Only a single color
                        components.append([QColor(l)])
                        continue
                    require_type(l, list)
                    this: IList[QColor] = []
                    for c in l:
                        require_type(c, string)
                        color = QColor(c)
                        this.append(color)
                    components.append(this)
                return cls(
                    components=components,
                    background=QColor(data['background']),
                    primary=QColor(data['primary']),
                    secondary=QColor(data['secondary']),
                    tertiary=QColor(data['tertiary']),
                    side=QColor(data['side']),
                    foreground=QColor(data['foreground']),
                    selected=QColor(data['selected'])
                )
            except Exception:
                raise Exception('Invalid color')

    def __init__(self, name: string, display_name: IDictionary[string, string], colors: ThemeColor):
        self.name: string = name
        self.display_name: IDictionary[string, string] = display_name
        self.colors: 'Theme.ThemeColor' = colors

    #     self._comp_color_map: IDictionary[int, tuple[int, int]] = {}  # RGBA -> (level_idx, color_idx)
    #     for level_idx, cs in enumerate(self.colors.components):
    #         for color_idx, color in enumerate(cs):
    #             self._comp_color_map[color.rgba()] = level_idx, color_idx
    #
    # def next_color(self, color: QColor) -> Nullable[QColor]:
    #     if color not in self._comp_color_map:
    #         return null
    #     level_idx, color_idx = self._comp_color_map[color.rgba()]
    #     cs = self.colors.components[level_idx]
    #     return cs[(color_idx + 1) % len(cs)]

    def __serialize__(self) -> IDictionary[string, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name,
            'colors': serialize(self.colors)
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Any]) -> Self:
        require_type(data, dict)
        require_member(data, 'name', 'display_name', 'colors')
        require_type(data['name'], string)
        require_type(data['display_name'], dict)
        for lang, name in data['display_name'].items():
            require_type(lang, string)
            require_type(name, string)
        return cls(
            name=data['name'],
            display_name=data['display_name'],
            colors=deserialize(cls.ThemeColor, data['colors'])
        )

    def __repr__(self) -> string:
        return f'Theme<{self.name}>'

    def get_display_name(self, lang: string) -> string:
        if lang in self.display_name:
            return self.display_name[lang]
        elif 'en_US' in self.display_name:
            return self.display_name['en_US']
        else:
            return self.name

    @staticmethod
    def user_themes_dir() -> Path:
        """
        :return: the directory holding user-created themes (``config/themes``);
            unlike ``res/themes`` its content may be created, edited and deleted
        """
        return BASE_DIR / 'config' / 'themes'

    @staticmethod
    def _normalize_theme_name(name: string) -> string:
        """
        Validate a theme name and turn it into a plain ``.json`` file name.
        :raise ValueError: raise when the name is blank or contains path separators
        """
        require_type(name, string)
        name = name.strip()
        if not name or '/' in name or '\\' in name:
            raise ValueError('Invalid theme name')
        if not name.lower().endswith('.json'):
            name = f'{name}.json'
        return name

    @staticmethod
    def _evict_cache(name: string) -> void:
        Resource._cache.setdefault('themes', {}).pop(name, None)

    @staticmethod
    def _resolve_theme_file(name: string) -> Nullable[Path]:
        """
        Resolve a theme file name against the user directory first (so a user
        theme may override a bundled one of the same name), then ``res/themes``.
        """
        if not name or '/' in name or '\\' in name:
            return null
        user_path = Theme.user_themes_dir() / name
        if user_path.is_file():
            return user_path
        path = Resource.resource_path('themes', name)
        if path.is_file():
            return path
        return null

    @staticmethod
    def from_resource(name: string) -> 'Theme':
        try:
            return Resource.load_cache('themes', name)
        except Resource.CacheMisses:
            if (path := Theme._resolve_theme_file(name)) is null:
                raise Resource.ResourceError(Resource.ResourceErrorCode.I2002, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    ser = json.load(f)
                theme = deserialize(Theme, ser)
            except OSError as e:
                raise Resource.ResourceError(Resource.ResourceErrorCode.I2003, 'I/O failed' if e.strerror is None else e.strerror)
            except json.JSONDecodeError:
                raise Resource.ResourceError(Resource.ResourceErrorCode.I2004, path.absolute().name)
            except SerializationError:
                raise Resource.ResourceError(Resource.ResourceErrorCode.I2005, path.absolute().name)
            except Exception:
                raise Resource.ResourceError(Resource.ResourceErrorCode.I2001)
            Resource.store_cache('themes', name, theme)
            return theme

    def save_to_user(self, name: Nullable[string] = null) -> Path:
        """
        Write this theme into ``config/themes`` (creating the directory on
        demand) and invalidate the cached copy. A user theme saved under the
        file name of a bundled theme overrides it.
        :param name: file name (or bare name) to save under; defaults to the
            theme's own name
        :return: the path written
        """
        file_name = Theme._normalize_theme_name(self.name if name is null else name)
        self.name = Path(file_name).stem
        path = Theme.user_themes_dir() / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(serialize(self), f, ensure_ascii=False, indent=4)
        Theme._evict_cache(file_name)
        return path

    @staticmethod
    def delete_user(name: string) -> void:
        """
        Delete a user theme; bundled themes under ``res/themes`` cannot be deleted.
        :raise Resource.ResourceError: I2002 when no user theme of that name exists
        """
        file_name = Theme._normalize_theme_name(name)
        path = Theme.user_themes_dir() / file_name
        if not path.is_file():
            raise Resource.ResourceError(Resource.ResourceErrorCode.I2002, file_name)
        path.unlink()
        Theme._evict_cache(file_name)

    @staticmethod
    def create_new(name: string, display_name: IDictionary[string, string]) -> 'Theme':
        """
        Create an unsaved theme initialized with the default theme's colors;
        ``save_to_user`` writes it into ``config/themes``. The colors are a deep
        copy, so later edits never leak into the source theme.
        """
        from core.preferences import Preferences  # Deferred: avoids the import cycle
        file_name = Theme._normalize_theme_name(name)
        base = Theme.from_resource(str(Preferences.Defaults['theme']))
        return Theme(
            name=Path(file_name).stem,
            display_name=dict(display_name),
            colors=deserialize(Theme.ThemeColor, serialize(base.colors)),
        )

    @staticmethod
    def duplicate(source: 'string | Theme', new_name: string,
                  new_display_name: IDictionary[string, string]) -> 'Theme':
        """
        Create an unsaved copy of an existing theme (given by file name or
        object) under a new name; ``save_to_user`` writes it into
        ``config/themes``. The colors are a deep copy of the source's.
        """
        theme = Theme.from_resource(source) if isinstance(source, string) else source
        file_name = Theme._normalize_theme_name(new_name)
        return Theme(
            name=Path(file_name).stem,
            display_name=dict(new_display_name),
            colors=deserialize(Theme.ThemeColor, serialize(theme.colors)),
        )
