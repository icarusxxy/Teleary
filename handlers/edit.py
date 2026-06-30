"""
Edit handlers for the diary bot.

These handlers manage the edit conversation flow:
1. /edit → cmd_edit → EDIT_SEARCH (choose search method)
2. Search by keyword/date/recent → EDIT_SELECT
3. Select entry → EDIT_MOOD
4. Choose mood → EDIT_TEXT
5. Enter new text (or /skip) → END (entry updated)
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from core.i18n import get_text
from utils.utils import db_to_local_date
from utils.validators import validate_date_input

from handlers.states import (
    EDIT_SEARCH, EDIT_KEYWORD, EDIT_DATE,
    EDIT_SELECT, EDIT_MOOD, EDIT_TEXT, CANCEL,
)
from handlers.common import lang

log = logger.bind(module="handlers.edit")


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /edit command - show search options for finding entries."""
    user_lang = await lang(update)
    keyboard = [
        [InlineKeyboardButton(await get_text("edit_search_keyword", user_lang), callback_data="editsearch:keyword")],
        [InlineKeyboardButton(await get_text("edit_search_date", user_lang), callback_data="editsearch:date")],
        [InlineKeyboardButton(await get_text("edit_recent_entries", user_lang), callback_data="editsearch:recent")],
        [InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)],
    ]
    await update.message.reply_text(
        await get_text("edit_how_find", user_lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SEARCH


async def edit_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search type selection - route to keyword, date, or recent entries."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    search_type = query.data.split(":", 1)[1]

    if search_type == "keyword":
        await query.edit_message_text(await get_text("edit_enter_keyword", user_lang))
        return EDIT_KEYWORD
    elif search_type == "date":
        await query.edit_message_text(await get_text("edit_enter_date", user_lang))
        return EDIT_DATE
    elif search_type == "recent":
        entries = await db.get_recent_entries(10)
        if not entries:
            await query.edit_message_text(await get_text("edit_no_entries", user_lang))
            return ConversationHandler.END

        context.user_data["edit_entries"] = entries
        keyboard = [
            [InlineKeyboardButton(
                f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
                callback_data=f"edit:{e['id']}",
            )]
            for e in entries
        ]
        keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
        await query.edit_message_text(
            await get_text("edit_which_entry", user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_SELECT


async def edit_keyword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle keyword search input - search entries by keyword."""
    query_text = update.message.text
    entries = await db.search_entries(query_text, limit=20)
    user_lang = await lang(update)

    if not entries:
        await update.message.reply_text(await get_text("edit_no_matching", user_lang, query=query_text))
        return ConversationHandler.END

    context.user_data["edit_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"edit:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
    await update.message.reply_text(
        await get_text("edit_results_for", user_lang, count=len(entries), query=query_text),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def edit_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date search input - search entries by date pattern."""
    date_str = update.message.text.strip()
    user_lang = await lang(update)
    
    # Validate date input
    is_valid, error_msg = validate_date_input(date_str)
    if not is_valid:
        await update.message.reply_text(error_msg)
        return EDIT_DATE

    entries = await db.get_entries_by_date_pattern(date_str)

    if not entries:
        await update.message.reply_text(await get_text("edit_no_entries_for_date", user_lang, date=date_str))
        return ConversationHandler.END

    context.user_data["edit_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"edit:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
    await update.message.reply_text(
        await get_text("edit_entries_for", user_lang, count=len(entries), date=date_str),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle entry selection - show current entry and mood options."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("edit_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text(await get_text("edit_not_found", user_lang))
        return ConversationHandler.END

    log.debug("edit_entry_selected entry_id={} user_id={}", entry_id, update.effective_user.id)
    context.user_data["editing_entry"] = entry
    moods = await emoji_config.get_moods()
    keyboard = [[InlineKeyboardButton(m, callback_data=f"emood:{m}")] for m in moods]
    keyboard.append([InlineKeyboardButton(await get_text("keep_current", user_lang), callback_data="emood:keep")])
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
    await query.edit_message_text(
        await get_text("edit_current", user_lang, mood=entry['mood'], thought=entry['thought']),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_MOOD


async def edit_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mood selection - prompt for new text."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    mood = query.data.split(":", 1)[1]
    entry = context.user_data["editing_entry"]

    if mood != "keep":
        context.user_data["editing_mood"] = mood
    else:
        context.user_data["editing_mood"] = entry["mood"]

    log.debug("edit_mood_selected entry_id={} mood={}", entry["id"], mood)
    await query.edit_message_text(
        await get_text("edit_new_text_prompt", user_lang, thought=entry['thought'])
    )
    return EDIT_TEXT


async def edit_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new text input - update the entry."""
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    thought = update.message.text
    user_lang = await lang(update)

    await db.update_entry(entry["id"], mood=mood, thought=thought)
    log.info("entry_updated entry_id={} mood={} text_len={} user_id={}", entry["id"], mood, len(thought), update.effective_user.id)
    await update.message.reply_text(await get_text("edit_updated", user_lang))
    return ConversationHandler.END


async def edit_text_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /skip command - update mood only, keep current text."""
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    user_lang = await lang(update)
    await db.update_entry(entry["id"], mood=mood)
    log.info("entry_mood_updated entry_id={} mood={} user_id={}", entry["id"], mood, update.effective_user.id)
    await update.message.reply_text(await get_text("edit_updated", user_lang))
    return ConversationHandler.END
