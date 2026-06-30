import aiosqlite
from datetime import date, datetime
from zoneinfo import ZoneInfo

from loguru import logger
from core.config import DB_PATH, TIMEZONE
from core.cache import get_cached_setting, cache_setting, invalidate_setting

log = logger.bind(module="database")

# Module-level singleton connection. Using a global avoids passing the connection
# through every function call, but means only one connection exists at a time.
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        log.debug("db_connecting path={}", DB_PATH)
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        # WAL mode allows concurrent reads while writing — important because
        # the scheduler sends reminders on a timer while the user may be saving entries.
        await _db.execute("PRAGMA journal_mode=WAL")
        await _init_schema(_db)
        log.info("db_connected path={}", DB_PATH)
    return _db


async def close_db():
    global _db
    if _db:
        log.debug("db_closing")
        await _db.close()
        _db = None
        log.info("db_closed")


async def _init_schema(db: aiosqlite.Connection):
    log.debug("db_schema_init")
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            mood TEXT NOT NULL,
            thought TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Index for sorting by creation time
        CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);
        
        -- Index for date-based queries (used by get_entries_by_date, get_entries_on_this_day)
        CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(strftime('%Y-%m-%d', created_at));
        
        -- Index for mood-based queries (used by get_stats)
        CREATE INDEX IF NOT EXISTS idx_entries_mood ON entries(mood);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    await db.commit()


async def save_entry(message_id: int, mood: str, thought: str, created_at: str | None = None) -> int:
    db = await get_db()
    if created_at:
        cursor = await db.execute(
            "INSERT INTO entries (message_id, mood, thought, created_at) VALUES (?, ?, ?, ?)",
            (message_id, mood, thought, created_at),
        )
    else:
        cursor = await db.execute(
            "INSERT INTO entries (message_id, mood, thought) VALUES (?, ?, ?)",
            (message_id, mood, thought),
        )
    await db.commit()
    entry_id = cursor.lastrowid
    log.debug("db_save_entry entry_id={} mood={} text_len={}", entry_id, mood, len(thought))
    return entry_id


async def get_entry(entry_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_recent_entries(limit: int = 10) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entries_page(year: int, month: int, limit: int = 10, offset: int = 0) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE strftime('%Y-%m', created_at) = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (f"{year}-{month:02d}", limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_all_entries_for_month(year: int, month: int, limit: int = 31) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE strftime('%Y-%m', created_at) = ? ORDER BY created_at DESC LIMIT ?",
        (f"{year}-{month:02d}", limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entries_before(year: int, month: int, limit: int = 10, offset: int = 0) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE created_at < ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (f"{year}-{month:02d}-01", limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


def escape_like(string: str) -> str:
    """Escape special characters for SQLite LIKE patterns.
    
    LIKE patterns use % and _ as wildcards. If user input contains these
    characters, they should be treated as literals, not wildcards.
    """
    return string.replace('%', '\\%').replace('_', '\\_')


async def search_entries(query: str, limit: int = 20) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE thought LIKE ? ESCAPE '\\' ORDER BY created_at DESC LIMIT ?",
        (f"%{escape_like(query)}%", limit),
    )
    rows = await cursor.fetchall()
    log.debug("db_search query='{}' result_count={}", query, len(rows))
    return [dict(r) for r in rows]


async def update_entry(entry_id: int, mood: str | None = None, thought: str | None = None):
    db = await get_db()
    sets: list[str] = []
    vals: list[str | int] = []
    if mood is not None:
        sets.append("mood = ?")
        vals.append(mood)
    if thought is not None:
        sets.append("thought = ?")
        vals.append(thought)
    if not sets:
        return
    vals.append(entry_id)
    await db.execute(f"UPDATE entries SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    log.debug("db_update_entry entry_id={} fields={}", entry_id, [s.split(" =")[0] for s in sets])


async def delete_entry(entry_id: int):
    db = await get_db()
    await db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    await db.commit()
    log.debug("db_delete_entry entry_id={}", entry_id)


async def get_entries_by_date(target_date: date) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE date(created_at) = date(?)",
        (target_date.isoformat(),),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entries_by_date_pattern(pattern: str, limit: int = 30) -> list[dict]:
    """Search entries by date pattern (YYYY, YYYY-MM, or YYYY-MM-DD)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE created_at LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"{pattern}%", limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entries_on_this_day(month: int, day: int) -> list[dict]:
    """Fetch entries from previous years on the same calendar day.

    Used by the daily memory feature to resurface "on this day" entries.
    Only returns entries from years before the current year — showing today's
    entry from this morning isn't a useful memory.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    current_year = now.year
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE strftime('%m', created_at) = ? AND strftime('%d', created_at) = ? AND strftime('%Y', created_at) < ?",
        (f"{month:02d}", f"{day:02d}", str(current_year)),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_random_entry() -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM entries ORDER BY RANDOM() LIMIT 1")
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_stats() -> dict:
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) FROM entries")
    total = (await cursor.fetchone())[0]

    now = datetime.now(ZoneInfo(TIMEZONE))
    cursor = await db.execute(
        "SELECT COUNT(*) FROM entries WHERE strftime('%Y-%m', created_at) = ?",
        (now.strftime("%Y-%m"),),
    )
    this_month = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT mood, COUNT(*) as cnt FROM entries GROUP BY mood")
    mood_rows = await cursor.fetchall()
    mood_dist = {r["mood"]: r["cnt"] for r in mood_rows}

    cursor = await db.execute(
        "SELECT DISTINCT date(created_at) as d FROM entries ORDER BY d"
    )
    dates = [row["d"] for row in await cursor.fetchall()]

    streak = 0
    current_streak = 0
    if dates:
        today = now.date()
        date_objs = [date.fromisoformat(d) for d in dates]

        # Current streak: only counts if the last entry is today or yesterday.
        last_date = date_objs[-1]
        if (today - last_date).days <= 1:
            current_streak = 1
            for i in range(len(date_objs) - 1, 0, -1):
                if (date_objs[i] - date_objs[i - 1]).days == 1:
                    current_streak += 1
                else:
                    break

        # Longest streak: scan forward for max consecutive run.
        streak = 1
        run = 1
        for i in range(1, len(date_objs)):
            if (date_objs[i] - date_objs[i - 1]).days == 1:
                run += 1
                streak = max(streak, run)
            else:
                run = 1

    return {
        "total": total,
        "this_month": this_month,
        "mood_dist": mood_dist,
        "longest_streak": streak,
        "current_streak": current_streak,
    }


async def get_setting(key: str) -> str | None:
    # Check cache first
    cached = get_cached_setting(key)
    if cached is not None:
        return cached
    
    db = await get_db()
    cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    value = row["value"] if row else None
    
    # Cache the result
    if value is not None:
        cache_setting(key, value)
    
    return value


async def get_settings(keys: list[str]) -> dict[str, str | None]:
    """Fetch multiple settings in a single query.

    Returns a dict mapping each key to its value (or None if not found).
    More efficient than calling get_setting() in a loop for each key.
    """
    db = await get_db()
    placeholders = ",".join("?" for _ in keys)
    cursor = await db.execute(
        f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
        keys,
    )
    rows = await cursor.fetchall()
    found = {row["key"]: row["value"] for row in rows}
    return {key: found.get(key) for key in keys}


async def set_setting(key: str, value: str):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    await db.commit()
    
    # Invalidate cache for this key
    invalidate_setting(key)
