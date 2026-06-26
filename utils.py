from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import TIMEZONE, MOOD_LABELS


def get_now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


def parse_date(raw: str) -> date:
    """Parse a date string from common formats.

    Accepted: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD
    """
    from re import fullmatch

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


def parse_time(raw: str) -> tuple[int, int, int]:
    """Parse a time string.

    Accepted: HHMM, HH:MM (→ HH:MM:00), HHMMSS, HH:MM:SS (→ HH:MM:SS)
    """
    from re import fullmatch

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
    """Convert a UTC timestamp string from the database to the configured timezone."""
    return datetime.fromisoformat(utc_str).replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(TIMEZONE))


def db_to_local_date(utc_str: str) -> str:
    """Return the date portion (YYYY-MM-DD) of a UTC string in local timezone."""
    return db_to_local(utc_str).strftime("%Y-%m-%d")


def format_entry(date: datetime, mood: str, thought: str) -> str:
    label = MOOD_LABELS.get(mood, "")
    return f"{mood} {label} — {date.strftime('%Y-%m-%d %H:%M')}\n\n{thought}"


def format_memory(date: datetime, mood: str, thought: str) -> str:
    label = MOOD_LABELS.get(mood, "")
    years_ago = get_now().year - date.year
    suffix = "year" if years_ago == 1 else "years"
    header = f"🗓 {years_ago} {suffix} ago — {date.strftime('%Y-%m-%d')}"
    return f"{header}\n{mood} {label}\n\n{thought}"
