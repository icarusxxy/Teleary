import aiosqlite
from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import DB_PATH, TIMEZONE

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _init_schema(_db)
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def _init_schema(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            mood TEXT NOT NULL,
            thought TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    await db.commit()


async def save_entry(message_id: int, mood: str, thought: str) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO entries (message_id, mood, thought) VALUES (?, ?, ?)",
        (message_id, mood, thought),
    )
    await db.commit()
    return cursor.lastrowid


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


async def search_entries(query: str, limit: int = 20) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE thought LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{query}%", limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_entry(entry_id: int, mood: str | None = None, thought: str | None = None):
    db = await get_db()
    sets, vals = [], []
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


async def delete_entry(entry_id: int):
    db = await get_db()
    await db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    await db.commit()


async def get_entries_by_date(target_date: date) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE date(created_at) = date(?)",
        (target_date.isoformat(),),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entries_on_this_day(month: int, day: int) -> list[dict]:
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM entries WHERE strftime('%m', created_at) = ? AND strftime('%d', created_at) = ?",
        (f"{month:02d}", f"{day:02d}"),
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        entry_date = datetime.fromisoformat(d["created_at"]).replace(tzinfo=tz)
        if entry_date.year < now.year:
            results.append(d)
    return results


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
        from datetime import timedelta
        date_objs = [date.fromisoformat(d) for d in dates]
        current_streak = 1
        for i in range(len(date_objs) - 1, 0, -1):
            if (date_objs[i] - date_objs[i - 1]).days == 1:
                current_streak += 1
            else:
                break
        streak = 1
        for i in range(len(date_objs) - 1, 0, -1):
            if (date_objs[i] - date_objs[i - 1]).days == 1:
                streak += 1
            else:
                break

    return {
        "total": total,
        "this_month": this_month,
        "mood_dist": mood_dist,
        "longest_streak": streak,
        "current_streak": current_streak,
    }


async def get_setting(key: str) -> str | None:
    db = await get_db()
    cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    return row["value"] if row else None


async def set_setting(key: str, value: str):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    await db.commit()
