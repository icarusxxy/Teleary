"""
Delete handlers for the diary bot.

These handlers manage the delete conversation flow:
1. /delete → cmd_delete → DELETE_SEARCH (choose search method)
2. Search by keyword/date/recent → EDIT_SELECT
3. Select entry → EDIT_TEXT (confirm)
4. Confirm delete → END (entry deleted)

Note: This flow reuses EDIT_SELECT and EDIT_TEXT states from the edit flow.
This is a known coupling issue that should be addressed in a future refactoring.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from loguru import logger
import core.database as db
from core.i18n import get_text
from utils.utils import db_to_local_date
from utils.validators import validate_date_input

from handlers.states import (
    DELETE_SEARCH, DELETE_KEYWORD, DELETE_DATE,
    EDIT_SELECT, EDIT_TEXT, CANCEL,
)
from handlers.common import lang

log = logger.bind(module="handlers.delete")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete command - show search options for finding entries."""
    log.debug("delete_started user_id={}", update.effective_user.id)
    user_lang = await lang(update)
    keyboard = [
        [InlineKeyboardButton(await get_text("del_search_keyword", user_lang), callback_data="delsearch:keyword")],
        [InlineKeyboardButton(await get_text("del_search_date", user_lang), callback_data="delsearch:date")],
        [InlineKeyboardButton(await get_text("del_recent_entries", user_lang), callback_data="delsearch:recent")],
        [InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)],
    ]
    await update.message.reply_text(
        await get_text("del_how_find", user_lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return DELETE_SEARCH


async def delete_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search type selection - route to keyword, date, or recent entries."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    search_type = query.data.split(":", 1)[1]

    if search_type == "keyword":
        await query.edit_message_text(await get_text("del_enter_keyword", user_lang))
        return DELETE_KEYWORD
    elif search_type == "date":
        await query.edit_message_text(await get_text("del_enter_date", user_lang))
        return DELETE_DATE
    elif search_type == "recent":
        entries = await db.get_recent_entries(10)
        if not entries:
            await query.edit_message_text(await get_text("del_no_entries", user_lang))
            return ConversationHandler.END

        context.user_data["delete_entries"] = entries
        keyboard = [
            [InlineKeyboardButton(
                f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
                callback_data=f"del:{e['id']}",
            )]
            for e in entries
        ]
        keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
        await query.edit_message_text(
            await get_text("del_which_entry", user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_SELECT


async def delete_keyword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle keyword search input - search entries by keyword."""
    query_text = update.message.text
    entries = await db.search_entries(query_text, limit=20)
    user_lang = await lang(update)

    if not entries:
        log.debug("delete_keyword_no_results query='{}' user_id={}", query_text, update.effective_user.id)
        await update.message.reply_text(await get_text("del_no_matching", user_lang, query=query_text))
        return ConversationHandler.END

    log.debug("delete_keyword_results query='{}' result_count={} user_id={}", query_text, len(entries), update.effective_user.id)
    context.user_data["delete_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"del:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
    await update.message.reply_text(
        await get_text("del_results_for", user_lang, count=len(entries), query=query_text),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date search input - search entries by date pattern."""
    date_str = update.message.text.strip()
    user_lang = await lang(update)
    
    # Validate date input
    is_valid, error_msg = validate_date_input(date_str)
    if not is_valid:
        log.debug("delete_date_invalid_format input='{}' user_id={}", date_str, update.effective_user.id)
        await update.message.reply_text(error_msg)
        return DELETE_DATE

    entries = await db.get_entries_by_date_pattern(date_str)

    if not entries:
        log.debug("delete_date_no_results date='{}' user_id={}", date_str, update.effective_user.id)
        await update.message.reply_text(await get_text("del_no_entries_for_date", user_lang, date=date_str))
        return ConversationHandler.END

    log.debug("delete_date_results date='{}' result_count={} user_id={}", date_str, len(entries), update.effective_user.id)
    context.user_data["delete_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"del:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
    await update.message.reply_text(
        await get_text("del_entries_for", user_lang, count=len(entries), date=date_str),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle entry selection - show confirmation prompt."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("delete_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text(await get_text("del_not_found", user_lang))
        return ConversationHandler.END

    log.debug("delete_confirm_prompt entry_id={} user_id={}", entry_id, update.effective_user.id)
    keyboard = [
        [
            InlineKeyboardButton(await get_text("yes_delete", user_lang), callback_data=f"delyes:{entry_id}"),
            InlineKeyboardButton(await get_text("cancel", user_lang), callback_data="delcancel"),
        ]
    ]
    confirm_text = await get_text("del_confirm", user_lang, mood=entry['mood'], date=entry['created_at'][:10], thought=entry['thought'])
    # Reply to the original diary message (like /list and /random do)
    if entry.get("message_id"):
        try:
            sent = await query.message.reply_text(
                confirm_text,
                reply_to_message_id=entry["message_id"],
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            log.warning("reply_to_original_failed entry_id={} error={}", entry_id, str(e))
            sent = await query.message.reply_text(
                confirm_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
    else:
        sent = await query.message.reply_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    # Remove the keyboard from the original list message
    await query.edit_message_text(query.message.text)
    return EDIT_TEXT


async def delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle delete confirmation - delete the entry."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == "delcancel":
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    await db.delete_entry(entry_id)
    log.info("entry_deleted entry_id={} user_id={}", entry_id, update.effective_user.id)
    await query.edit_message_text(await get_text("del_deleted", user_lang))
    return ConversationHandler.END
