"""
Random entry handler for the diary bot.

This handler manages the /random command which shows a random diary entry.
"""

from telegram import Update
from telegram.ext import ContextTypes

from loguru import logger
import core.database as db
from core.i18n import get_text
from utils.utils import db_to_local, format_entry

from handlers.common import lang, reply_to_entry

log = logger.bind(module="handlers.random")


async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /random command - show a random diary entry."""
    entry = await db.get_random_entry()
    user_lang = await lang(update)
    if not entry:
        await update.message.reply_text(await get_text("list_no_entries", user_lang))
        return

    text = await format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
        lang=user_lang,
    )

    await reply_to_entry(update.message, entry, text, entry["id"])
