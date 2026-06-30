import os
import sys
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# BOT_TOKEN is required — crash immediately if missing rather than failing at runtime.
BOT_TOKEN = os.environ["BOT_TOKEN"]
TIMEZONE = os.getenv("TIMEZONE", "Asia/Taipei")
DB_PATH = os.getenv("DB_PATH", "data/diary.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Loguru setup: remove default handler, add stderr with module context.
# Each module binds its own module name via logger.bind(module="...") for traceability.
logger.remove()
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan>:<cyan>{function}</cyan> | {message}",
    colorize=True,
)
logger = logger.bind(module="config")


async def get_reminder_pool(lang: str = "eng") -> list[str]:
    # Lazy import to avoid circular dependency: config -> i18n -> config is possible
    # if i18n ever needs config values at module level.
    from core.i18n import get_text
    reminders = await get_text("reminder_pool", lang)
    if isinstance(reminders, list):
        return reminders
    # Hardcoded fallback if locale file is missing or malformed.
    return [
        "Hey, don't forget to write something down today!",
        "How are you feeling? Take a moment to journal.",
        "Your diary misses you. Write something!",
        "A quick entry now = a memory later. Journal!",
        "What's on your mind? Drop a note in your diary.",
        "Even one line counts — write something today.",
    ]
