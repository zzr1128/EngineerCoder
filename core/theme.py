# -*- coding: utf-8 -*-

from dataclasses import dataclass
import json

from PySide6.QtGui import QColor

from alias import *
from core.resource import Resource


@dataclass
class Theme:
    @dataclass
    class ThemeColor:
        components: IList[QColor]
        primary: QColor
        secondary: QColor
        tertiary: QColor
        side: QColor
        foreground: QColor

        def __serialize__(self) -> IDictionary[string, Any]:
            return {
                'components': [c.name() for c in self.components],
                'primary': self.primary.name(),
                'secondary': self.secondary.name(),
                'tertiary': self.tertiary.name(),
                'side': self.side.name(),
                'foreground': self.foreground.name(),
            }

        @classmethod
        def __deserialize__(cls, data: IDictionary[string, Any]) -> Self:
            require_type(data, dict)
            require_member(data, 'components', 'primary', 'secondary', 'tertiary', 'side', 'foreground')
            require_type(data['components'], list)
            require_type(data['primary'], string)
            require_type(data['secondary'], string)
            require_type(data['tertiary'], string)
            require_type(data['side'], string)
            require_type(data['foreground'], string)
            components: IList[QColor] = []
            try:
                for c in data['components']:
                    require_type(c, string)
                    color = QColor(c)
                    components.append(color)
                return cls(
                    components=components,
                    primary=QColor(data['primary']),
                    secondary=QColor(data['secondary']),
                    tertiary=QColor(data['tertiary']),
                    side=QColor(data['side']),
                    foreground=QColor(data['foreground'])
                )
            except Exception:
                raise Exception(f'Invalid color')

    name: string
    display_name: IDictionary[string, string]
    colors: ThemeColor

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
