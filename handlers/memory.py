"""
Memory handler for the diary bot.

This handler manages the send_memories function which is called by the scheduler
to send 'on this day' entries from previous years.
"""

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from utils.utils import db_to_local, format_memory, get_now

log = logger.bind(module="handlers.memory")


async def send_memories(bot, chat_id: int):
    """Send 'on this day' entries from previous years as replies to original messages.

    Called by the scheduler at the configured memory_time. Each entry is sent
    as a reply to its original message_id so the user sees the memory in context.
    If the original message was deleted, falls back to a standalone message.
    """
    now = get_now()
    entries = await db.get_entries_on_this_day(now.month, now.day)

    log.info("memory_check month={} day={} found_entries={}", now.month, now.day, len(entries))

    if not entries:
        return

    user_lang = await db.get_setting("language") or "eng"
    mood_labels = await emoji_config.get_mood_labels(user_lang)

    for entry in entries:
        text = await format_memory(
            db_to_local(entry["created_at"]),
            entry["mood"],
            entry["thought"],
            lang=user_lang,
            mood_labels=mood_labels,
        )
        if entry["message_id"]:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_to_message_id=entry["message_id"],
                )
            except Exception as e:
                log.warning("memory_reply_failed entry_id={} error={}", entry["id"], str(e))
                await bot.send_message(chat_id=chat_id, text=text)
        else:
            await bot.send_message(chat_id=chat_id, text=text)

    log.info("memories_sent count={}", len(entries))
