import random
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from zoneinfo import ZoneInfo

from loguru import logger
from config import TIMEZONE, REMINDER_POOL
import database as db
from utils import get_now

log = logger.bind(module="scheduler")

scheduler = AsyncIOScheduler(timezone=ZoneInfo(TIMEZONE))
_bot = None
_chat_id = None


def init_scheduler(bot, chat_id: int | None):
    global _bot, _chat_id
    _bot = bot
    _chat_id = chat_id

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


def set_chat_id(chat_id: int):
    global _chat_id
    _chat_id = chat_id


async def _random_reminder():
    if not _bot or not _chat_id:
        return

    now = get_now()

    today_entries = await db.get_entries_by_date(now.date())
    if today_entries:
        log.debug("reminder_skipped already_jotted today_entry_count={}", len(today_entries))
        return

    last_sent_str = await db.get_setting("last_reminder_sent")
    if last_sent_str:
        last_sent = datetime.fromisoformat(last_sent_str)
        if (now - last_sent).total_seconds() < 7200:
            log.debug("reminder_skipped cooldown active last_sent='{}'", last_sent_str)
            return

    start = int(await db.get_setting("reminder_start") or "9")
    end = int(await db.get_setting("reminder_end") or "21")

    if start <= now.hour <= end:
        if random.random() < 0.30:
            msg = random.choice(REMINDER_POOL)
            await _bot.send_message(chat_id=_chat_id, text=msg)
            await db.set_setting("last_reminder_sent", now.isoformat())
            log.info("reminder_sent hour={} message='{}'", now.hour, msg[:40])
        else:
            log.debug("reminder_skipped hour={} probability_miss", now.hour)
    else:
        log.debug("reminder_outside_window hour={} window={}-{}", now.hour, start, end)


async def _daily_memory():
    if not _bot or not _chat_id:
        return

    now = get_now()
    memory_time = await db.get_setting("memory_time") or "09:00"
    h, m = map(int, memory_time.split(":"))
    if now.hour != h:
        log.debug("memory_skip hour={} scheduled_hour={}", now.hour, h)
        return

    log.info("memory_fired hour={}", now.hour)
    from handlers import send_memories

    class FakeContext:
        def __init__(self, bot, chat_id):
            self.bot = bot
            self.chat_id = chat_id

    await send_memories(FakeContext(_bot, _chat_id))
