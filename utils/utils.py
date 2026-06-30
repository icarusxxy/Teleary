from datetime import date, datetime
from re import fullmatch
from zoneinfo import ZoneInfo

from core.config import TIMEZONE
import utils.emoji_config as emoji_config
from core.i18n import get_text

_UTC = ZoneInfo("UTC")
_LOCAL_TZ = ZoneInfo(TIMEZONE)


def get_now() -> datetime:
    return datetime.now(_LOCAL_TZ)


def parse_date(raw: str) -> date:
    """Parse a date string from common formats.

    Accepted: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD
    """
    cleaned = raw.strip()

    # YYYYMMDD (digits only, 8 chars)
    if fullmatch(r"\d{8}", cleaned):
        y, m, d = int(cleaned[:4]), int(cleaned[4:6]), int(cleaned[6:8])
        return date(y, m, d)

    # Try common separators (YYYY-MM-DD / YYYY/MM/DD)
    for sep in ("-", "/"):
        parts = cleaned.split(sep)
        if len(parts) == 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return date(y, m, d)

    # Fallback to ISO format (YYYY-MM-DD) via stdlib
    return date.fromisoformat(cleaned)


def parse_date_pattern(raw: str) -> str:
    """Normalize a date string into a prefix for LIKE queries.

    Accepted: YYYY, YYYYMM, YYYY-MM, YYYYMMDD, YYYY-MM-DD, YYYY/MM/DD
    Returns: 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD'
    Raises ValueError if the input doesn't match a known pattern.
    """
    cleaned = raw.strip()

    # 4 digits → YYYY
    if fullmatch(r"\d{4}", cleaned):
        return cleaned

    # 6 digits → YYYY-MM (from YYYYMM)
    if fullmatch(r"\d{6}", cleaned):
        return f"{cleaned[:4]}-{cleaned[4:6]}"

    # 8 digits → YYYY-MM-DD (from YYYYMMDD)
    if fullmatch(r"\d{8}", cleaned):
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"

    # With separators
    for sep in ("-", "/"):
        parts = cleaned.split(sep)
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return f"{parts[0]}-{parts[1]}"
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return f"{parts[0]}-{parts[1]}-{parts[2]}"

    raise ValueError(f"Invalid date pattern: {raw}")


def parse_time(raw: str) -> tuple[int, int, int]:
    """Parse a time string.

    Accepted: HHMM, HH:MM (→ HH:MM:00), HHMMSS, HH:MM:SS (→ HH:MM:SS)
    """
    cleaned = raw.strip()

    # HHMM (digits only, 4 chars)
    if fullmatch(r"\d{4}", cleaned):
        h, m = int(cleaned[:2]), int(cleaned[2:4])
        return h, m, 0

    # HH:MM (with colon)
    if fullmatch(r"\d{2}:\d{2}", cleaned):
        h, m = int(cleaned[:2]), int(cleaned[3:5])
        return h, m, 0

    # HHMMSS (digits only, 6 chars)
    if fullmatch(r"\d{6}", cleaned):
        h, m, s = int(cleaned[:2]), int(cleaned[2:4]), int(cleaned[4:6])
        return h, m, s

    # HH:MM:SS (with colons)
    if fullmatch(r"\d{2}:\d{2}:\d{2}", cleaned):
        h, m, s = int(cleaned[:2]), int(cleaned[3:5]), int(cleaned[6:8])
        return h, m, s

    raise ValueError(f"Invalid time format: {raw}")


def db_to_local(utc_str: str) -> datetime:
    """Convert a UTC timestamp string from the database to the configured timezone.

    IMPORTANT: SQLite stores timestamps as plain strings without timezone info.
    We assume they're UTC (the convention used when inserting via import),
    then convert to the user's configured timezone for display.
    """
    return datetime.fromisoformat(utc_str).replace(tzinfo=_UTC).astimezone(_LOCAL_TZ)


def db_to_local_date(utc_str: str) -> str:
    """Return the date portion (YYYY-MM-DD) of a UTC string in local timezone."""
    return db_to_local(utc_str).strftime("%Y-%m-%d")


async def format_entry(date: datetime, mood: str, thought: str, lang: str = "eng") -> str:
    mood_labels = await emoji_config.get_mood_labels(lang)
    label = mood_labels.get(mood, "")
    return await get_text("format_entry", lang, mood=mood, label=label, datetime=date.strftime('%A, %Y-%m-%d %H:%M'), thought=thought)


async def format_memory(date: datetime, mood: str, thought: str, lang: str = "eng", mood_labels: dict[str, str] | None = None) -> str:
    """Format an entry for the 'on this day' memory feature.

    Includes a header like "1 year ago today" to give context, followed by
    the mood emoji + label and the original thought text.
    """
    if mood_labels is None:
        mood_labels = await emoji_config.get_mood_labels(lang)
    label = mood_labels.get(mood, "")
    years_ago = get_now().year - date.year
    suffix = await get_text("format_memory_year", lang) if years_ago == 1 else await get_text("format_memory_years", lang)
    header = await get_text("format_memory_header", lang, years=years_ago, suffix=suffix, date=date.strftime('%A, %Y-%m-%d'))
    return f"{header}\n{mood} {label}\n\n{thought}"


async def safe_db_operation(operation, error_key: str, lang: str, update) -> any:
    """Execute database operation with error handling.
    
    Args:
        operation: Async callable to execute
        error_key: i18n key for error message
        lang: Language code
        update: Telegram Update object for sending replies
        
    Returns:
        Result of operation or None if error occurred
    """
    from loguru import logger
    log = logger.bind(module="utils")
    
    try:
        return await operation()
    except Exception as e:
        log.error("db_operation_failed error={}", str(e))
        try:
            if update.message:
                await update.message.reply_text(await get_text(error_key, lang))
            elif update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(await get_text(error_key, lang))
        except Exception as reply_error:
            log.error("reply_failed error={}", str(reply_error))
        return None
