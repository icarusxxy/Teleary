"""
List/browse handlers for the diary bot.

These handlers manage the /list command and entry browsing:
1. /list → cmd_list (show current month or recent entries)
2. listprev/listnext → list_more_callback (pagination)
3. view:<id> → view_entry_callback (show single entry)
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from loguru import logger
import core.database as db
from core.i18n import get_text
from utils.utils import db_to_local, format_entry, get_now

from handlers.common import lang, reply_to_entry, build_entry_buttons

log = logger.bind(module="handlers.list")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command - show entries for current month or recent history."""
    now = get_now()
    entries = await db.get_all_entries_for_month(now.year, now.month, limit=31)
    user_lang = await lang(update)
    log.debug("list_viewed user_id={} year={} month={} entry_count={}", update.effective_user.id, now.year, now.month, len(entries))

    if entries:
        context.user_data["list_mode"] = "month"
        context.user_data["list_year"] = now.year
        context.user_data["list_month"] = now.month
        context.user_data["list_offset"] = 0

        keyboard = build_entry_buttons(entries)
        keyboard.append([InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev")])

        await update.message.reply_text(
            await get_text("list_month_header", user_lang, month=now.strftime('%B %Y'), count=len(entries)),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    older = await db.get_entries_before(now.year, now.month, limit=10)
    if not older:
        await update.message.reply_text(await get_text("list_no_entries", user_lang))
        return

    context.user_data["list_mode"] = "history"
    first_local = db_to_local(older[0]["created_at"])
    context.user_data["list_year"] = first_local.year
    context.user_data["list_month"] = first_local.month
    context.user_data["list_offset"] = 10

    keyboard = build_entry_buttons(older)
    nav_row = []
    nav_row.append(InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"))
    nav_row.append(InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"))
    keyboard.append(nav_row)

    await update.message.reply_text(
        await get_text("list_older_shown", user_lang, count=len(older)),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def list_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle listprev/listnext callbacks - paginate through entries."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)
    callback_data = query.data
    mode = context.user_data.get("list_mode", "month")
    year = context.user_data.get("list_year")
    month = context.user_data.get("list_month")
    offset = context.user_data.get("list_offset", 0)

    if callback_data == "listprev":
        if mode == "month":
            context.user_data["list_mode"] = "history"
            context.user_data["list_offset"] = 10
            older = await db.get_entries_before(year, month, limit=10)
            if not older:
                try:
                    await query.edit_message_text(await get_text("list_no_more", user_lang))
                except BadRequest:
                    pass  # Message already shows this content
                return

            keyboard = build_entry_buttons(older)
            nav_row = [
                InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
            ]
            keyboard.append(nav_row)

            await query.edit_message_text(
                await get_text("list_older_shown", user_lang, count=len(older)),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            new_offset = offset + 10
            entries = await db.get_entries_before(year, month, limit=10, offset=new_offset)
            if not entries:
                try:
                    await query.edit_message_text(await get_text("list_no_more", user_lang))
                except BadRequest:
                    pass  # Message already shows this content
                return

            context.user_data["list_offset"] = new_offset

            keyboard = build_entry_buttons(entries)
            nav_row = [
                InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
            ]
            keyboard.append(nav_row)

            await query.edit_message_text(
                await get_text("list_older_shown", user_lang, count=len(entries)),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif callback_data == "listnext":
        if mode == "history":
            if offset <= 10:
                now = get_now()
                entries = await db.get_all_entries_for_month(now.year, now.month, limit=31)
                context.user_data["list_mode"] = "month"
                context.user_data["list_year"] = now.year
                context.user_data["list_month"] = now.month
                context.user_data["list_offset"] = 0

                keyboard = build_entry_buttons(entries)
                keyboard.append([InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev")])

                await query.edit_message_text(
                    await get_text("list_month_header", user_lang, month=now.strftime('%B %Y'), count=len(entries)),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                new_offset = offset - 10
                entries = await db.get_entries_before(year, month, limit=10, offset=new_offset)
                context.user_data["list_offset"] = new_offset

                keyboard = build_entry_buttons(entries)
                nav_row = [
                    InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                    InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
                ]
                keyboard.append(nav_row)

                await query.edit_message_text(
                    await get_text("list_newer_shown", user_lang, count=len(entries)),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )


async def view_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle view:<id> callback - show a single entry."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)
    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("view_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text(await get_text("search_not_found", user_lang))
        return

    text = await format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
        lang=user_lang,
    )

    await reply_to_entry(query.message, entry, text, entry_id)
