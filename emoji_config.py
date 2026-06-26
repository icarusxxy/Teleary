import json
from loguru import logger

import database as db

log = logger.bind(module="emoji_config")

DEFAULT_MOODS = [
    {"emoji": "😊", "label": "Happy"},
    {"emoji": "😢", "label": "Sad"},
    {"emoji": "😐", "label": "Neutral"},
    {"emoji": "😤", "label": "Frustrated"},
    {"emoji": "😴", "label": "Tired"},
]


async def get_moods() -> list[str]:
    raw = await db.get_setting("moods")
    if raw:
        try:
            items = json.loads(raw)
            return [item["emoji"] for item in items]
        except (json.JSONDecodeError, KeyError):
            log.warning("invalid_moods_json_falling_back_to_defaults")
    return [item["emoji"] for item in DEFAULT_MOODS]


async def get_mood_labels() -> dict[str, str]:
    raw = await db.get_setting("moods")
    if raw:
        try:
            items = json.loads(raw)
            return {item["emoji"]: item["label"] for item in items}
        except (json.JSONDecodeError, KeyError):
            log.warning("invalid_mood_labels_json_falling_back_to_defaults")
    return {item["emoji"]: item["label"] for item in DEFAULT_MOODS}


async def get_moods_full() -> list[dict]:
    raw = await db.get_setting("moods")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, KeyError):
            log.warning("invalid_moods_json_falling_back_to_defaults")
    return list(DEFAULT_MOODS)


async def set_moods(moods: list[dict]):
    await db.set_setting("moods", json.dumps(moods))
    log.info("moods_updated count={}", len(moods))
