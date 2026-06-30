import random
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from zoneinfo import ZoneInfo

from loguru import logger
from core.config import TIMEZONE, get_reminder_pool
import core.database as db
from utils.utils import get_now
import bot_state

log = logger.bind(module="scheduler")

scheduler = AsyncIOScheduler(timezone=ZoneInfo(TIMEZONE))


def init_scheduler(bot, chat_id: int | None):
    """Start the scheduler with two jobs:

    1. Random reminder: fires every 15 min, 30% chance of sending a reminder
       message. Has a 2-hour cooldown between sends to avoid being annoying.

    2. Daily memory: fires every hour on the hour, but only actually sends
       at the user's configured memory_time. This avoids needing a precise
       cron expression for an arbitrary HH:MM.
    """
    bot_state.set_bot(bot)
    if chat_id is not None:
        bot_state.set_chat_id(chat_id)

    scheduler.add_job(
        _random_reminder,
        trigger=IntervalTrigger(minutes=15),
        id="random_reminder",
        replace_existing=True,
    )

    scheduler.add_job(
        _daily_memory,
        trigger=CronTrigger(hour="*", minute="0"),
        id="daily_memory",
        replace_existing=True,
    )

    scheduler.start()
    log.info("scheduler_started chat_id={}", chat_id)


async def _random_reminder():
    try:
        bot = bot_state.get_bot()
        chat_id = bot_state.get_chat_id()
        if not bot or not chat_id:
            return

        now = get_now()

        # Don't remind if the user already journaled today — the goal is to
        # encourage the habit, not nag when they've already done it.
        today_entries = await db.get_entries_by_date(now.date())
        if today_entries:
            log.debug("reminder_skipped already_jotted today_entry_count={}", len(today_entries))
            return

        settings = await db.get_settings(["last_reminder_sent", "reminder_start", "reminder_end", "language"])
        last_sent_str = settings.get("last_reminder_sent")
        if last_sent_str:
            last_sent = datetime.fromisoformat(last_sent_str)
            # 2-hour cooldown: prevents reminding too frequently if the user
            # is actively chatting but just not journaling.
            if (now - last_sent).total_seconds() < 7200:
                log.debug("reminder_skipped cooldown active last_sent='{}'", last_sent_str)
                return

        start = int(settings.get("reminder_start") or "9")
        end = int(settings.get("reminder_end") or "21")

        if start <= now.hour <= end:
            # 30% chance per tick (every 15 min) = ~5% chance per hour.
            # High enough to be noticed, low enough to not feel naggy.
            if random.random() < 0.30:
                lang = settings.get("language") or "eng"
                reminder_pool = await get_reminder_pool(lang)
                msg = random.choice(reminder_pool)
                await bot.send_message(chat_id=chat_id, text=msg)
                await db.set_setting("last_reminder_sent", now.isoformat())
                log.info("reminder_sent hour={} message='{}'", now.hour, msg[:40])
            else:
                log.debug("reminder_skipped hour={} probability_miss", now.hour)
        else:
            log.debug("reminder_outside_window hour={} window={}-{}", now.hour, start, end)
    except Exception as e:
        log.error("random_reminder_failed error={}", str(e))


async def _daily_memory():
    try:
        bot = bot_state.get_bot()
        chat_id = bot_state.get_chat_id()
        if not bot or not chat_id:
            return

        now = get_now()
        memory_time = await db.get_setting("memory_time") or "09:00"
        h, m = map(int, memory_time.split(":"))
        if now.hour != h:
            log.debug("memory_skip hour={} scheduled_hour={}", now.hour, h)
            return

        log.info("memory_fired hour={}", now.hour)
        from handlers.memory import send_memories

        await send_memories(bot, chat_id)
    except Exception as e:
        log.error("daily_memory_failed error={}", str(e))
