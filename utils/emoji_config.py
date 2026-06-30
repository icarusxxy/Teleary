import json
import time
from loguru import logger

import core.database as db
from core.i18n import get_text

log = logger.bind(module="emoji_config")

# Default moods shipped with the bot. Users can customize these via /settings,
# but these serve as the initial set and the "reset to defaults" target.
DEFAULT_MOODS = [
    {"emoji": "😁", "label": "Happy"},
    {"emoji": "☺️", "label": "Good"},
    {"emoji": "😐", "label": "Not much"},
    {"emoji": "🫤", "label": "Meh"},
    {"emoji": "😢", "label": "Sad"},
    {"emoji": "😡", "label": "Angry"},
]

# Maps default emojis to i18n keys for translated labels.
# Custom emojis added by the user won't be in this map — they keep their
# user-provided label as-is (see get_mood_labels for the merge logic).
MOOD_KEYS = {
    "😁": "mood_happy",
    "☺️": "mood_good",
    "😐": "mood_neutral",
    "🫤": "mood_meh",
    "😢": "mood_sad",
    "😡": "mood_angry",
}

# Cache for raw moods JSON from DB to avoid repeated DB reads + JSON parsing.
# Invalidated on set_moods() or after TTL expires.
_raw_moods_cache: str | None = None
_raw_moods_cache_time: float = 0
_MOODS_CACHE_TTL: float = 60.0  # 60 seconds


def _invalidate_cache():
    global _raw_moods_cache, _raw_moods_cache_time
    _raw_moods_cache = None
    _raw_moods_cache_time = 0


async def _get_raw_moods() -> str | None:
    global _raw_moods_cache, _raw_moods_cache_time
    now = time.monotonic()
    if _raw_moods_cache is not None and (now - _raw_moods_cache_time) < _MOODS_CACHE_TTL:
        return _raw_moods_cache
    _raw_moods_cache = await db.get_setting("moods")
    _raw_moods_cache_time = now
    return _raw_moods_cache


async def _load_moods() -> list[dict] | None:
    """Load custom moods from DB, returns None if none configured or invalid."""
    raw = await _get_raw_moods()
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, KeyError):
            log.warning("invalid_moods_json_falling_back_to_defaults")
    return None


async def _resolve_label(item: dict, lang: str) -> str:
    """Resolve display label: i18n key for default emojis, stored label for custom ones.

    For default emojis (in MOOD_KEYS), uses i18n translation unless the stored label
    has been customized by the user (differs from the original default label), in which
    case the user-provided label is used.
    """
    if item["emoji"] in MOOD_KEYS:
        default = next((d for d in DEFAULT_MOODS if d["emoji"] == item["emoji"]), None)
        if default is None or item["label"] == default["label"]:
            return await get_text(MOOD_KEYS[item["emoji"]], lang)
    return item["label"]


async def get_moods() -> list[str]:
    items = await _load_moods()
    if items is None:
        items = DEFAULT_MOODS
    return [item["emoji"] for item in items]


async def get_mood_labels(lang: str = "eng") -> dict[str, str]:
    """Return emoji → translated label mapping.

    For default emojis, uses i18n translation keys via MOOD_KEYS.
    For custom user-added emojis, uses the label stored at creation time.
    This lets default moods translate automatically while custom ones stay as-is.
    """
    items = await _load_moods()
    if items is None:
        items = DEFAULT_MOODS
    return {item["emoji"]: await _resolve_label(item, lang) for item in items}


async def get_moods_full(lang: str = "eng") -> list[dict]:
    items = await _load_moods()
    if items is None:
        items = DEFAULT_MOODS
    result = []
    for item in items:
        result.append({"emoji": item["emoji"], "label": await _resolve_label(item, lang)})
    return result


async def get_raw_moods() -> list[dict]:
    """Return the raw mood list from DB without label resolution.

    Use this for read-modify-write CRUD operations (add/edit/remove) to
    avoid overwriting stored labels with i18n-resolved translations.
    """
    items = await _load_moods()
    if items is None:
        items = DEFAULT_MOODS
    return [dict(item) for item in items]  # shallow-copy each dict


async def set_moods(moods: list[dict]):
    await db.set_setting("moods", json.dumps(moods))
    _invalidate_cache()
    log.info("moods_updated count={}", len(moods))


async def get_default_moods_full(lang: str = "eng") -> list[dict]:
    return [{"emoji": item["emoji"], "label": await _resolve_label(item, lang)} for item in DEFAULT_MOODS]
