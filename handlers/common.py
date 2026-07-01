"""
Shared helper functions for diary bot handlers.

These functions are used across multiple feature flows (entry creation, edit,
delete, import, etc.). They handle common tasks like language resolution,
keyboard building, and media group buffering.
"""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from core.i18n import get_text, get_lang_for_user

log = logger.bind(module="handlers.common")

# Global state for media group (album) buffering.
# Telegram sends album items as separate messages with the same media_group_id.
# Buffer them with a 1.5s delay to collect all items before processing.
_media_group_buffers: dict[str, list] = {}
_media_group_locks: dict[str, bool] = {}


async def lang(update: Update) -> str:
    """Resolve user language: DB setting > Telegram client language > default.

    Checks the database first because the user may have explicitly chosen a
    language in /settings that differs from their Telegram client language.
    """
    user = update.effective_user
    if update.callback_query:
        user = update.callback_query.from_user

    saved = await db.get_setting("language")
    if saved:
        return saved

    lang_code = user.language_code if user else None
    return await get_lang_for_user(lang_code)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command or cancel button press."""
    log.debug("conversation_cancelled user_id={}", update.effective_user.id)
    user_lang = await lang(update)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(await get_text("cancelled", user_lang))
    else:
        await update.message.reply_text(await get_text("cancelled", user_lang))
    return ConversationHandler.END


async def mood_keyboard(lang: str, callback_prefix: str = "mood") -> InlineKeyboardMarkup:
    """Build an InlineKeyboardMarkup with mood emoji buttons."""
    moods = await emoji_config.get_moods()
    keyboard = [[InlineKeyboardButton(m, callback_data=f"{callback_prefix}:{m}")] for m in moods]
    keyboard.append([InlineKeyboardButton(await get_text("cancel", lang), callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


async def reply_to_entry(where, entry: dict, text: str, entry_id: int):
    """Reply to an entry's original message, falling back to a plain reply."""
    if entry.get("message_id"):
        try:
            await where.reply_text(text, reply_to_message_id=entry["message_id"])
        except Exception as e:
            log.warning("reply_to_original_failed entry_id={} error={}", entry_id, str(e))
            await where.reply_text(text)
    else:
        await where.reply_text(text)


async def handle_media_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buffer media group (album) messages and process them as a single entry.

    Telegram sends album items as separate messages, each with the same
    media_group_id. Don't know how many items are in the album until they
    all arrive, so buffer each for 1.5s and process the group as one entry.
    The lock prevents duplicate processing if multiple items arrive rapidly.
    """
    msg = update.message
    group_id = msg.media_group_id

    if group_id not in _media_group_buffers:
        _media_group_buffers[group_id] = []

    _media_group_buffers[group_id].append(msg)

    async def _process_group():
        # Wait 1.5s to collect all album items — Telegram sends them in rapid
        # succession but not atomically. This is a pragmatic trade-off between
        # latency and correctness.
        await asyncio.sleep(1.5)
        messages = _media_group_buffers.pop(group_id, [])
        _media_group_locks.pop(group_id, None)

        if not messages:
            log.warning("media_group_empty group_id={}", group_id)
            return

        messages.sort(key=lambda m: m.message_id)
        first_msg = messages[0]
        caption = first_msg.caption or ""
        message_ids = [m.message_id for m in messages]
        log.info("media_group_resolved group_id={} item_count={} caption_len={}", group_id, len(messages), len(caption))

        context.user_data["pending_text"] = caption
        context.user_data["pending_message_id"] = first_msg.message_id
        context.user_data["pending_media_group_ids"] = message_ids

        user_lang = await lang(update)
        await first_msg.reply_text(
            await get_text("album_items_how_feeling", user_lang, count=len(messages)),
            reply_markup=await mood_keyboard(user_lang),
        )

    if group_id not in _media_group_locks:
        _media_group_locks[group_id] = True
        task = asyncio.create_task(_process_group())
        task.add_done_callback(lambda t: log.error("media_group_task_failed group_id={} error={}", group_id, t.exception()) if t.exception() else None)


def build_entry_buttons(entries: list[dict], callback_prefix: str = "view", truncate: int = 40) -> list[list[InlineKeyboardButton]]:
    """Build a list of InlineKeyboardButtons from entry dicts."""
    from utils.utils import db_to_local_date

    return [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:truncate]}{'...' if len(e['thought']) > truncate else ''}",
            callback_data=f"{callback_prefix}:{e['id']}",
        )]
        for e in entries
    ]
