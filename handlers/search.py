"""
Search handlers for the diary bot.

These handlers manage search functionality:
1. /search <text> → cmd_search (search entries by keyword)
2. srch:<id> → search_result_callback (view search result)
3. /search_by_date <date> → cmd_search_by_date (search by date pattern)
"""

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from loguru import logger
import core.database as db
from core.i18n import get_text
from utils.utils import db_to_local, format_entry, parse_date_pattern

from handlers.common import lang, reply_to_entry, build_entry_buttons

log = logger.bind(module="handlers.search")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command - search entries by keyword."""
    query_text = " ".join(context.args) if context.args else ""
    user_lang = await lang(update)
    if not query_text:
        await update.message.reply_text(await get_text("search_usage", user_lang))
        return

    entries = await db.search_entries(query_text, limit=20)
    log.debug("search_completed user_id={} query='{}' result_count={}", update.effective_user.id, query_text, len(entries))
    if not entries:
        await update.message.reply_text(await get_text("search_no_matching", user_lang, query=query_text))
        return

    context.user_data["search_entries"] = {e["id"]: e for e in entries}

    await update.message.reply_text(
        await get_text("search_results", user_lang, count=len(entries), query=query_text),
        reply_markup=InlineKeyboardMarkup(build_entry_buttons(entries, "srch")),
    )


async def search_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle srch:<id> callback - show a search result entry."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)
    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("search_result_not_found entry_id={}", entry_id)
        await query.edit_message_text(await get_text("search_not_found", user_lang))
        return

    text = await format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
        lang=user_lang,
    )

    await reply_to_entry(query.message, entry, text, entry_id)


async def cmd_search_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search_by_date command - search entries by date pattern."""
    if not update.message:
        return

    raw = " ".join(context.args) if context.args else ""
    user_lang = await lang(update)
    if not raw:
        await update.message.reply_text(await get_text("search_by_date_usage", user_lang))
        return

    try:
        pattern = parse_date_pattern(raw)
    except ValueError:
        await update.message.reply_text(await get_text("search_by_date_invalid", user_lang, raw=raw))
        return

    entries = await db.get_entries_by_date_pattern(pattern, limit=30)
    log.debug("search_by_date user_id={} pattern='{}' result_count={}", update.effective_user.id, pattern, len(entries))

    if not entries:
        await update.message.reply_text(await get_text("search_by_date_no_matching", user_lang, pattern=pattern))
        return

    context.user_data["search_entries"] = {e["id"]: e for e in entries}

    await update.message.reply_text(
        await get_text("search_by_date_results", user_lang, count=len(entries), pattern=pattern),
        reply_markup=InlineKeyboardMarkup(build_entry_buttons(entries, "srch")),
    )
