"""
Entry creation handlers for the diary bot.

These handlers manage the core diary entry creation flow:
1. User sends text/photo/media → receive_entry → MOOD_PICK
2. User taps mood emoji → mood_callback → END (entry saved)
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from core.i18n import get_text
import bot_state

from handlers.states import MOOD_PICK
from handlers.common import lang, mood_keyboard, handle_media_group

log = logger.bind(module="handlers.entry")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - initialize user and show welcome message."""
    chat_id = update.effective_chat.id
    log.info("user_started user_id={} chat_id={}", update.effective_user.id, chat_id)
    bot_state.set_chat_id(chat_id)
    user_lang = await lang(update)
    await update.message.reply_text(await get_text("welcome", user_lang))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - show welcome/help message."""
    user_lang = await lang(update)
    await update.message.reply_text(await get_text("welcome", user_lang))


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /language command - show language selection menu."""
    from handlers.settings import _show_language_menu
    return await _show_language_menu(update, context)


async def receive_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text/photo/video messages as new diary entries.

    This is the entry point for the entry creation conversation flow.
    Media groups (albums) are buffered and processed as a single entry.
    """
    bot_state.set_chat_id(update.effective_chat.id)
    msg = update.message
    user_id = update.effective_user.id

    if msg.media_group_id:
        log.debug("media_group_received user_id={} group_id={}", user_id, msg.media_group_id)
        await handle_media_group(update, context)
        return MOOD_PICK

    text = msg.text or msg.caption or ""
    log.debug("entry_received user_id={} text_len={} has_media={}", user_id, len(text), bool(msg.photo or msg.video))
    context.user_data["pending_text"] = text
    context.user_data["pending_message_id"] = msg.message_id

    user_lang = await lang(update)
    await msg.reply_text(
        await get_text("how_are_you_feeling", user_lang),
        reply_markup=await mood_keyboard(user_lang),
    )
    return MOOD_PICK


async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mood emoji button press - save the entry with selected mood."""
    query = update.callback_query
    await query.answer()

    mood = query.data.split(":", 1)[1]
    text = context.user_data.pop("pending_text", "")
    message_id = context.user_data.pop("pending_message_id")
    context.user_data.pop("pending_media_group_ids", None)

    entry_id = await db.save_entry(message_id, mood, text)
    user_lang = await lang(update)
    mood_labels = await emoji_config.get_mood_labels(user_lang)
    label = mood_labels.get(mood, "")
    log.info("entry_saved entry_id={} mood={} text_len={} user_id={}", entry_id, mood, len(text), update.effective_user.id)
    await query.edit_message_text(await get_text("saved_mood", user_lang, mood=mood, label=label))
    return ConversationHandler.END
