# -*- coding: utf-8 -*-

import gettext
import warnings

from alias import *
from core.preferences import Preferences
from path import BASE_DIR

_translations: IDictionary[string, Callable[[string], string]] = {}
# Installation arguments of the entries above, kept so ``set_language`` can
# reinstall every registered domain for the newly selected language
_translation_specs: IDictionary[string, tuple[string, string, IEnumerable[string]]] = {}


def get_language() -> string:
    """
    :return: the active language; resolution order: explicitly stored
        preference, legacy ``config/language`` plain-text file, default
    """
    prefs = Preferences()
    if prefs.contains('language'):
        return str(prefs.get('language'))
    try:
        with open(BASE_DIR / 'config' / 'language', 'r', encoding='utf-8') as f:
            lang = f.read().strip()
    except Exception:
        lang = str(Preferences.Defaults['language'])
    return lang


language = get_language()


def _catalog_languages(lang: string) -> IList[string]:
    return [lang] if lang == 'en_US' else [lang, 'en_US']


def get_translation() -> Callable[[string], string]:
    trans = gettext.translation(
        domain='messages',
        localedir=BASE_DIR / 'res' / 'locale',
        languages=_catalog_languages(language)
    )
    return trans.gettext


def install_translation(key: string, domain: string, path: string, languages: IEnumerable[string]) -> void:
    _translation_specs[key] = (domain, path, list(languages))
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


# Proxy rather than a bound gettext function: ``set_language`` swaps the
# underlying catalog, and every ``from core.localization import _`` keeps
# resolving through this module attribute, so old imports stay correct
_gettext: Callable[[string], string] = get_translation()


def _(message: string) -> string:
    return _gettext(message)


def set_language(lang: string) -> void:
    """
    Switch the application language without restarting.
    Persists the choice to the preferences file, reinstalls the application
    catalog and every kit translation domain registered via
    ``install_translation``, and mirrors the choice onto the running
    ``Environment`` (kits read ``env.local_language``).
    :param lang: language code with an available catalog (e.g. 'zh_CN')
    :raise ValueError: raise when no catalog exists for the language
    """
    global language, _gettext
    prefs = Preferences()
    if lang not in prefs.available_languages():
        raise ValueError(f'No translation catalog for language: {lang}')
    prefs.set('language', lang)
    prefs.save()
    language = lang
    _gettext = get_translation()
    # Reinstall the kit translation domains against the new language; keep the
    # previous one when the domain lacks a catalog for it
    for key, (domain, path, original) in _translation_specs.items():
        try:
            _translations[key] = gettext.translation(
                domain=domain,
                localedir=path,
                languages=_catalog_languages(lang)
            ).gettext
        except OSError:
            _translations[key] = gettext.translation(
                domain=domain,
                localedir=path,
                languages=original
            ).gettext
    # Mirroring: deferred import, environment imports this module at load time
    try:
        from core.environment import Environment
        env = Environment._instance
        if env is not null:
            env.local_language = lang
    except Exception:
        pass
