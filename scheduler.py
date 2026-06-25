import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from zoneinfo import ZoneInfo

from config import TIMEZONE, REMINDER_POOL
import database as db
from utils import get_now


scheduler = AsyncIOScheduler(timezone=ZoneInfo(TIMEZONE))
_bot = None
_chat_id = None


def init_scheduler(bot, chat_id: int):
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


def set_chat_id(chat_id: int):
    global _chat_id
    _chat_id = chat_id


async def _random_reminder():
    if not _bot or not _chat_id:
        return

    now = get_now()
    start = int(await db.get_setting("reminder_start") or "9")
    end = int(await db.get_setting("reminder_end") or "21")

    if start <= now.hour <= end:
        if random.random() < 0.30:
            msg = random.choice(REMINDER_POOL)
            await _bot.send_message(chat_id=_chat_id, text=msg)


async def _daily_memory():
    if not _bot or not _chat_id:
        return

    now = get_now()
    memory_time = await db.get_setting("memory_time") or "09:00"
    h, m = map(int, memory_time.split(":"))
    if now.hour != h:
        return

    from handlers import send_memories

    class FakeContext:
        def __init__(self, bot, chat_id):
            self.bot = bot
            self.chat_id = chat_id

    await send_memories(FakeContext(_bot, _chat_id))
