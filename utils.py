from datetime import datetime
from zoneinfo import ZoneInfo

from config import TIMEZONE, MOOD_LABELS


def get_now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


def format_entry(date: datetime, mood: str, thought: str) -> str:
    label = MOOD_LABELS.get(mood, "")
    return f"{mood} {label} — {date.strftime('%Y-%m-%d %H:%M')}\n\n{thought}"


def format_memory(date: datetime, mood: str, thought: str) -> str:
    label = MOOD_LABELS.get(mood, "")
    years_ago = get_now().year - date.year
    suffix = "year" if years_ago == 1 else "years"
    header = f"🗓 {years_ago} {suffix} ago — {date.strftime('%Y-%m-%d')}"
    return f"{header}\n{mood} {label}\n\n{thought}"
