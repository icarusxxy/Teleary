import os
import sys
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
TIMEZONE = os.getenv("TIMEZONE", "Asia/Taipei")
DB_PATH = os.getenv("DB_PATH", "diary.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logger.remove()
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan>:<cyan>{function}</cyan> | {message}",
    colorize=True,
)
logger = logger.bind(module="config")

MOODS = ["😊", "😢", "😐", "😤", "😴"]
MOOD_LABELS = {
    "😊": "Happy",
    "😢": "Sad",
    "😐": "Neutral",
    "😤": "Frustrated",
    "😴": "Tired",
}

REMINDER_POOL = [
    "Hey, don't forget to write something down today!",
    "How are you feeling? Take a moment to journal.",
    "Your diary misses you. Write something!",
    "A quick entry now = a memory later. Journal!",
    "What's on your mind? Drop a note in your diary.",
    "Even one line counts — write something today.",
]
