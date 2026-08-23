# -*- coding: utf-8 -*-

from dataclasses import dataclass
import json

from PySide6.QtGui import QColor

from alias import *
from alias import IList
from core.resource import Resource


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
    def from_resource(name: string) -> 'Theme':
        try:
            return Resource.load_cache('themes', name)
        except Resource.CacheMisses:
            if not (path := Resource.resource_path('themes', name)).is_file():
                raise Resource.ResourceError(Resource.ResourceErrorCode.I2002, path.absolute().name)
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
            Resource.store_cache('theme', name, theme)
            return theme
