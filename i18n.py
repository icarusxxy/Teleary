import json
import os
from pathlib import Path

from loguru import logger

log = logger.bind(module="i18n")

LOCALE_DIR = Path(__file__).parent / "locale"
DEFAULT_LANG = "eng"

_translations: dict[str, dict[str, str]] = {}
_available_langs: list[str] = []


def _load_translations():
    global _translations, _available_langs
    if _translations:
        return

    for file in LOCALE_DIR.glob("*.json"):
        lang_code = file.stem
        try:
            with open(file, "r", encoding="utf-8") as f:
                _translations[lang_code] = json.load(f)
            _available_langs.append(lang_code)
            log.debug("locale_loaded lang={} keys={}", lang_code, len(_translations[lang_code]))
        except (json.JSONDecodeError, OSError) as e:
            log.error("locale_load_failed lang={} error={}", lang_code, e)

    _available_langs.sort()
    if DEFAULT_LANG not in _translations:
        log.warning("default_locale_missing lang={}", DEFAULT_LANG)


def get_text(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Look up a translated string by key, with fallback to default language.

    Supports Python str.format() placeholders: get_text("greeting", lang, name="Alice").
    If the key is missing in the requested language, falls back to English.
    If still missing, returns the key itself as a last resort (fails visibly
    rather than silently showing empty strings).
    """
    _load_translations()

    translations = _translations.get(lang, {})
    text = translations.get(key)

    if text is None:
        fallback = _translations.get(DEFAULT_LANG, {})
        text = fallback.get(key, key)
        if lang != DEFAULT_LANG:
            log.debug("translation_fallback key={} lang={}", key, lang)

    # Format with kwargs if provided — allows dynamic values like counts, names, etc.
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError) as e:
            log.error("translation_format_error key={} error={}", key, e)

    return text


def get_lang_for_user(user_lang_code: str | None) -> str:
    """Map a Telegram user's language_code to an available locale.

    Telegram sends codes like "zh-TW" or "en-US". We try exact match first,
    then the base language ("zh" from "zh-TW"), then fall back to English.
    This handles cases where a user's language is a dialect we don't support.
    """
    _load_translations()

    if user_lang_code and user_lang_code in _translations:
        return user_lang_code

    base = user_lang_code.split("-")[0] if user_lang_code else ""
    if base in _translations:
        return base

    return DEFAULT_LANG


def get_available_langs() -> list[str]:
    _load_translations()
    return list(_available_langs)


def get_lang_name(lang_code: str) -> str:
    names = {
        "eng": "English",
        "zh-tw": "正體中文",
        "ja": "日本語",
        "ko": "한국어",
        "es": "Español",
        "fr": "Français",
        "de": "Deutsch",
        "ru": "Русский",
        "pt": "Português",
        "ar": "العربية",
    }
    return names.get(lang_code, lang_code.upper())
