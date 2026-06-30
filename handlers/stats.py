"""
Stats handler for the diary bot.

This handler manages the /stats command which displays user statistics.
"""

from telegram import Update
from telegram.ext import ContextTypes

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from core.i18n import get_text

from handlers.common import lang

log = logger.bind(module="handlers.stats")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command - display user statistics."""
    stats = await db.get_stats()
    user_lang = await lang(update)
    log.debug("stats_retrieved user_id={} total={} this_month={} streak={}", update.effective_user.id, stats["total"], stats["this_month"], stats["current_streak"])

    mood_labels = await emoji_config.get_mood_labels(user_lang)
    mood_lines = []
    for mood, count in sorted(stats["mood_dist"].items(), key=lambda x: -x[1]):
        label = mood_labels.get(mood, "?")
        mood_lines.append(f"  {mood} {label}: {count}")

    text = await get_text("stats_title", user_lang, total=stats['total'], this_month=stats['this_month'], streak=stats['current_streak'], longest=stats['longest_streak']) + "\n".join(mood_lines if mood_lines else [await get_text("stats_no_data", user_lang)])
    await update.message.reply_text(text)
