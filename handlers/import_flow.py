"""
Import handlers for the diary bot.

These handlers manage the import conversation flow:
1. /import YYYY-MM-DD [HHMM] → cmd_import → IMPORT_DATE
2. Send text/photo → import_text_receive/import_media_receive → IMPORT_MOOD
3. Select mood → import_mood_callback → END (entry imported with custom date)

Named 'import_flow' to avoid collision with Python's 'import' keyword.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from core.i18n import get_text
from core.config import TIMEZONE
from utils.utils import parse_date, parse_time

from handlers.states import IMPORT_DATE, IMPORT_MOOD, CANCEL
from handlers.common import lang, mood_keyboard, _media_group_buffers, _media_group_locks

log = logger.bind(module="handlers.import_flow")


async def cmd_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /import command - parse date and prompt for entry text."""
    args = context.args
    user_lang = await lang(update)
    if not args:
        log.debug("import_no_args user_id={}", update.effective_user.id)
        await update.message.reply_text(await get_text("import_usage", user_lang))
        return ConversationHandler.END

    try:
        target_date = parse_date(args[0])
    except (ValueError, TypeError):
        await update.message.reply_text(await get_text("import_invalid_date", user_lang))
        return ConversationHandler.END

    h, m, s = 12, 0, 0
    if len(args) > 1:
        try:
            h, m, s = parse_time(args[1])
        except ValueError:
            await update.message.reply_text(await get_text("import_invalid_time", user_lang))
            return ConversationHandler.END

    tz = ZoneInfo(TIMEZONE)
    target_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, s, tzinfo=tz)
    context.user_data["import_date"] = target_dt
    await update.message.reply_text(await get_text("import_send_text", user_lang))
    return IMPORT_DATE


async def import_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for import - store text and prompt for mood."""
    import_date = context.user_data.get('import_date')
    log.debug("import_text_received user_id={} import_date={}", update.effective_user.id, import_date)
    context.user_data["import_text"] = update.message.text
    context.user_data["import_message_id"] = update.message.message_id
    user_lang = await lang(update)
    await update.message.reply_text(await get_text("import_pick_mood", user_lang), reply_markup=await mood_keyboard(user_lang, "imood"))
    return IMPORT_MOOD


async def import_media_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media input for import - buffer media groups and prompt for mood."""
    msg = update.message
    import_date = context.user_data.get('import_date')
    log.debug("import_media_received user_id={} import_date={} has_group={}", update.effective_user.id, import_date, bool(msg.media_group_id))

    if msg.media_group_id:
        group_id = msg.media_group_id
        if group_id not in _media_group_buffers:
            _media_group_buffers[group_id] = []
        _media_group_buffers[group_id].append(msg)

        async def _process_import_group():
            await asyncio.sleep(1.5)
            messages = _media_group_buffers.pop(group_id, [])
            _media_group_locks.pop(group_id, None)

            if not messages:
                log.warning("import_media_group_empty group_id={}", group_id)
                return

            messages.sort(key=lambda m: m.message_id)
            first_msg = messages[0]
            caption = first_msg.caption or ""
            message_ids = [m.message_id for m in messages]
            log.info("import_media_group_resolved group_id={} item_count={} caption_len={}", group_id, len(messages), len(caption))

            context.user_data["import_text"] = caption
            context.user_data["import_message_id"] = first_msg.message_id
            context.user_data["import_media_group_ids"] = message_ids

            user_lang = await lang(update)
            await first_msg.reply_text(
                await get_text("import_album_pick_mood", user_lang, count=len(messages)),
                reply_markup=await mood_keyboard(user_lang, "imood"),
            )

        if group_id not in _media_group_locks:
            _media_group_locks[group_id] = True
            task = asyncio.create_task(_process_import_group())
            task.add_done_callback(lambda t: log.error("import_media_group_task_failed group_id={} error={}", group_id, t.exception()) if t.exception() else None)
    else:
        context.user_data["import_text"] = msg.caption or ""
        context.user_data["import_message_id"] = msg.message_id

        user_lang = await lang(update)
        await msg.reply_text(await get_text("import_pick_mood", user_lang), reply_markup=await mood_keyboard(user_lang, "imood"))
        return IMPORT_MOOD

    return IMPORT_MOOD


async def import_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mood selection for import - save entry with custom date."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    mood = query.data.split(":", 1)[1]
    target_dt = context.user_data["import_date"]
    text = context.user_data.get("import_text", "")

    # Convert local time to UTC for storage. SQLite stores timestamps without
    # timezone info, so we normalize to UTC before inserting.
    dt_utc = target_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    log.debug("import_saving user_id={} target_dt={} dt_utc={}", update.effective_user.id, target_dt, dt_utc)

    message_id = context.user_data.get("import_message_id")
    media_ids = context.user_data.pop("import_media_group_ids", None)

    if media_ids:
        log.debug("import_media_group_ids={} count={}", media_ids, len(media_ids))

    entry_id = await db.save_entry(message_id, mood, text, dt_utc.strftime("%Y-%m-%d %H:%M:%S"))

    log.debug("import_stored entry_id={} created_at={}", entry_id, dt_utc.strftime("%Y-%m-%d %H:%M:%S"))

    mood_labels = await emoji_config.get_mood_labels(user_lang)
    label = mood_labels.get(mood, "")
    log.info("entry_imported entry_id={} mood={} target_dt={} user_id={}", entry_id, mood, target_dt, update.effective_user.id)
    media_count = f" ({len(media_ids)} items)" if media_ids else ""
    await query.edit_message_text(await get_text("import_imported", user_lang, mood=mood, label=label, media=media_count, datetime=target_dt.strftime('%Y-%m-%d %H:%M:%S')))
    return ConversationHandler.END
