# -*- coding: utf-8 -*-

import json

from alias import *
from core.environment import Environment
from core.resource import Resource
from path import BASE_DIR


def init_translation() -> Callable[[string], string]:
    this = BASE_DIR / 'kits' / 'common'
    env = Environment.instance()
    lang = env.local_language if (BASE_DIR / 'kits' / 'common' / 'locale' / f'{env.local_language}.json').is_file() else 'en_US'
    path = this / 'locale' / f'{lang}.json'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            ser = json.load(f)
    except OSError as e:
        raise Resource.ResourceError(Resource.ResourceErrorCode.I2003, f'{path.absolute()} ({e.strerror})')
    except json.JSONDecodeError:
        raise Resource.ResourceError(Resource.ResourceErrorCode.I2004, path.absolute())
    except Exception:
        raise Resource.ResourceError(Resource.ResourceErrorCode.I2001)
    if not isinstance(ser, dict):
        raise Resource.ResourceError(Resource.ResourceErrorCode.I2004, path.absolute())
    return lambda key: str(ser.get(key, key))


_ = init_translation()
