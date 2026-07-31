# -*- coding: utf-8 -*-

import warnings
import gettext

from alias import *
from path import BASE_DIR

_translations: IDictionary[string, Callable[[string], string]] = {}


def get_language() -> string:
    try:
        with open(BASE_DIR / 'config' / 'language', 'r', encoding='utf-8') as f:
            lang = f.read().strip()
    except Exception:
        try:
            with open(BASE_DIR / 'config' / 'language', 'w', encoding='utf-8') as f:
                f.write('en_US')
        except Exception:
            pass
        finally:
            lang = 'en_US'
    return lang


language = get_language()


def get_translation() -> Callable[[string], string]:
    languages = [language] if language == 'en_US' else [language, 'en_US']
    trans = gettext.translation(
        domain='messages',
        localedir=BASE_DIR / 'res' / 'locale',
        languages=languages
    )
    return trans.gettext


def install_translation(key: string, domain: string, path: string, languages: IEnumerable[string]) -> void:
    _translations[key] = gettext.translation(
        domain=domain,
        localedir=path,
        languages=languages
    ).gettext


def get_translator(key: string) -> Callable[[string], string]:
    """
    Get a translator by its key.
    Usually, the key is the unique name of the kit.
    :param key: the key of installation of the translator
    :return: translation function ``(string)->string``

    Example:
    _ = get_translator(kit.name)
    """
    if key in _translations:
        return _translations[key]
    else:
        warnings.warn("Translation not installed: " + key, UserWarning, stacklevel=2)
        return lambda x: x


_ = get_translation()
