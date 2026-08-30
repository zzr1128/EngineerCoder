# -*- coding: utf-8 -*-

import enum
from pathlib import Path

from alias import *
from core.localization import _
from path import BASE_DIR
from core.localization import _


@final
class Resource:
    _cache: IDictionary[string, IDictionary[string, Any]] = {
        'themes': {}
    }

    class CacheMisses(Exception):
        pass

    # noinspection GrazieInspection
    class ResourceErrorCode(enum.Enum):  # I2xxx for internal resource error
        I2001 = _('I2001')  # Unresolved resource error.
        I2002 = _('I2002')  # Resource not found: {1}
        I2003 = _('I2003')  # Resource I/O error: {1}
        I2004 = _('I2004')  # Invalid resource format: {1}
        I2005 = _('I2005')  # Invalid resource content: {1}

    class ResourceError(Exception):
        def __init__(self, code: 'Resource.ResourceErrorCode', *fmt: string):
            self.code: Resource.ResourceErrorCode = code
            self.fmt: tuple[string, ...] = fmt

        def __str__(self) -> string:
            return f'[{self.code.name}] {self.code.value.format(*self.fmt)}'

    @staticmethod
    def resource_path(*name: string) -> Path:
        path = BASE_DIR / 'res'
        for n in name:
            path /= n
        return path

    @classmethod
    def load_cache(cls, group: string, key: string) -> Any:
        if group in Resource._cache and key in Resource._cache[group]:
            return Resource._cache[group][key]
        raise Resource.CacheMisses()

    @classmethod
    def store_cache(cls, group: string, key: string, value: Any) -> void:
        Resource._cache.setdefault(group, {})[key] = value
