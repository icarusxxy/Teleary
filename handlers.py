from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)
from datetime import date, datetime
from zoneinfo import ZoneInfo
import asyncio

from loguru import logger
from config import MOODS, MOOD_LABELS, TIMEZONE
import database as db
from utils import db_to_local, db_to_local_date, format_entry, format_memory, get_now, parse_date, parse_time
from scheduler import set_chat_id

log = logger.bind(module="handlers")


MOOD_PICK, ENTRY_TEXT, EDIT_SELECT, EDIT_MOOD, EDIT_TEXT = range(5)
IMPORT_DATE, IMPORT_MOOD = range(5, 7)
SETTINGS_SELECT, SETTINGS_VALUE = range(7, 9)
DELETE_SEARCH, DELETE_KEYWORD, DELETE_DATE = range(9, 12)

CANCEL = "cancel"

_media_group_buffers: dict[str, list] = {}
_media_group_locks: dict[str, asyncio.Event] = {}


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)]])


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.debug("conversation_cancelled user_id={}", update.effective_user.id)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Cancelled.")
    else:
        await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── /start ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    log.info("user_started user_id={} chat_id={}", update.effective_user.id, chat_id)
    set_chat_id(chat_id)
    await update.message.reply_text(
        "📖 Welcome to your Diary Bot!\n\n"
        "Send me any message — text, photo, video, or album — and I'll help you log it with a mood.\n\n"
        "Commands:\n"
        "/list — Browse your entries\n"
        "/search <text> — Search your diary\n"
        "/edit — Edit a past entry\n"
        "/delete — Delete a past entry\n"
        "/import YYYY-MM-DD — Import a past entry\n"
        "/settings — Configure reminders & memory\n"
        "/stats — View your journaling stats"
    )


# ── New Entry ───────────────────────────────────────────

async def receive_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    msg = update.message
    user_id = update.effective_user.id

    if msg.media_group_id:
        log.debug("media_group_received user_id={} group_id={}", user_id, msg.media_group_id)
        await _handle_media_group(update, context)
        return

    text = msg.text or msg.caption or ""
    log.debug("entry_received user_id={} text_len={} has_media={}", user_id, len(text), bool(msg.photo or msg.video))
    context.user_data["pending_text"] = text
    context.user_data["pending_message_id"] = msg.message_id

    keyboard = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in MOODS]
    keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
    await msg.reply_text(
        "How are you feeling?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MOOD_PICK


async def _handle_media_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    group_id = msg.media_group_id

    if group_id not in _media_group_buffers:
        _media_group_buffers[group_id] = []
        _media_group_locks[group_id] = asyncio.Event()

    _media_group_buffers[group_id].append(msg)

    async def _process_group():
        await asyncio.sleep(1.5)
        messages = _media_group_buffers.pop(group_id, [])
        _media_group_locks.pop(group_id, None)

        if not messages:
            log.warn("media_group_empty group_id={}", group_id)
            return

        messages.sort(key=lambda m: m.message_id)
        first_msg = messages[0]
        caption = first_msg.caption or ""
        message_ids = [m.message_id for m in messages]
        log.info("media_group_resolved group_id={} item_count={} caption_len={}", group_id, len(messages), len(caption))

        context.user_data["pending_text"] = caption
        context.user_data["pending_message_id"] = first_msg.message_id
        context.user_data["pending_media_group_ids"] = message_ids

        keyboard = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in MOODS]
        keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
        await first_msg.reply_text(
            f"📸 Album with {len(messages)} items received. How are you feeling?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    if group_id not in _media_group_locks or not _media_group_locks[group_id].is_set():
        _media_group_locks[group_id] = asyncio.Event()
        asyncio.create_task(_process_group())


async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mood = query.data.split(":", 1)[1]
    text = context.user_data.pop("pending_text", "")
    message_id = context.user_data.pop("pending_message_id")
    context.user_data.pop("pending_media_group_ids", None)

    entry_id = await db.save_entry(message_id, mood, text)
    label = MOOD_LABELS.get(mood, "")
    log.info("entry_saved entry_id={} mood={} text_len={} user_id={}", entry_id, mood, len(text), update.effective_user.id)
    await query.edit_message_text(f"✓ Saved! {mood} {label}")
    return ConversationHandler.END


# ── /edit ───────────────────────────────────────────────

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = await db.get_recent_entries(10)
    if not entries:
        log.debug("edit_no_entries user_id={}", update.effective_user.id)
        await update.message.reply_text("No entries to edit.")
        return ConversationHandler.END

    log.debug("edit_started user_id={} entry_count={}", update.effective_user.id, len(entries))
    context.user_data["edit_entries"] = entries
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"edit:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
    await update.message.reply_text(
        "Which entry do you want to edit?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warn("edit_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text("Entry not found.")
        return ConversationHandler.END

    log.debug("edit_entry_selected entry_id={} user_id={}", entry_id, update.effective_user.id)
    context.user_data["editing_entry"] = entry
    keyboard = [[InlineKeyboardButton(m, callback_data=f"emood:{m}")] for m in MOODS]
    keyboard.append([InlineKeyboardButton("Keep current", callback_data="emood:keep")])
    keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
    await query.edit_message_text(
        f"Current: {entry['mood']} {entry['thought']}\n\nPick a new mood:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_MOOD


async def edit_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    mood = query.data.split(":", 1)[1]
    entry = context.user_data["editing_entry"]

    if mood != "keep":
        context.user_data["editing_mood"] = mood
    else:
        context.user_data["editing_mood"] = entry["mood"]

    log.debug("edit_mood_selected entry_id={} mood={}", entry["id"], mood)
    await query.edit_message_text(
        f"Current thought: {entry['thought']}\n\nSend me the new text (or /skip to keep current, /cancel to abort):"
    )
    return EDIT_TEXT


async def edit_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    thought = update.message.text

    await db.update_entry(entry["id"], mood=mood, thought=thought)
    log.info("entry_updated entry_id={} mood={} text_len={} user_id={}", entry["id"], mood, len(thought), update.effective_user.id)
    await update.message.reply_text("✓ Entry updated!")
    return ConversationHandler.END


async def edit_text_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    await db.update_entry(entry["id"], mood=mood)
    log.info("entry_mood_updated entry_id={} mood={} user_id={}", entry["id"], mood, update.effective_user.id)
    await update.message.reply_text("✓ Entry updated!")
    return ConversationHandler.END


# ── /delete ─────────────────────────────────────────────

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.debug("delete_started user_id={}", update.effective_user.id)
    keyboard = [
        [InlineKeyboardButton("🔍 Search by keyword", callback_data="delsearch:keyword")],
        [InlineKeyboardButton("📅 Search by date", callback_data="delsearch:date")],
        [InlineKeyboardButton("📋 Recent entries", callback_data="delsearch:recent")],
        [InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)],
    ]
    await update.message.reply_text(
        "How would you like to find the entry to delete?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return DELETE_SEARCH


async def delete_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    search_type = query.data.split(":", 1)[1]

    if search_type == "keyword":
        await query.edit_message_text("Enter a keyword to search for:")
        return DELETE_KEYWORD
    elif search_type == "date":
        await query.edit_message_text(
            "Enter a date (YYYY, YYYY-MM, or YYYY-MM-DD):"
        )
        return DELETE_DATE
    elif search_type == "recent":
        entries = await db.get_recent_entries(10)
        if not entries:
            await query.edit_message_text("No entries to delete.")
            return ConversationHandler.END

        context.user_data["delete_entries"] = entries
        keyboard = [
            [InlineKeyboardButton(
                f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
                callback_data=f"del:{e['id']}",
            )]
            for e in entries
        ]
        keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
        await query.edit_message_text(
            "Which entry do you want to delete?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_SELECT


async def delete_keyword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    entries = await db.search_entries(query_text, limit=20)

    if not entries:
        log.debug("delete_keyword_no_results query='{}' user_id={}", query_text, update.effective_user.id)
        await update.message.reply_text(f'No entries matching "{query_text}".')
        return ConversationHandler.END

    log.debug("delete_keyword_results query='{}' result_count={} user_id={}", query_text, len(entries), update.effective_user.id)
    context.user_data["delete_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"del:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
    await update.message.reply_text(
        f'🔍 {len(entries)} result(s) for "{query_text}"\n\nWhich entry do you want to delete?',
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text.strip()
    
    # Validate format: YYYY, YYYY-MM, or YYYY-MM-DD
    import re
    if not re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", date_str):
        log.debug("delete_date_invalid_format input='{}' user_id={}", date_str, update.effective_user.id)
        await update.message.reply_text(
            "Invalid date format. Use YYYY, YYYY-MM, or YYYY-MM-DD."
        )
        return DELETE_DATE

    entries = await db.get_entries_by_date_pattern(date_str)

    if not entries:
        log.debug("delete_date_no_results date='{}' user_id={}", date_str, update.effective_user.id)
        await update.message.reply_text(f"No entries found for {date_str}.")
        return ConversationHandler.END

    log.debug("delete_date_results date='{}' result_count={} user_id={}", date_str, len(entries), update.effective_user.id)
    context.user_data["delete_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"del:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
    await update.message.reply_text(
        f"📅 {len(entries)} entry(ies) for {date_str}\n\nWhich entry do you want to delete?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warn("delete_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text("Entry not found.")
        return ConversationHandler.END

    log.debug("delete_confirm_prompt entry_id={} user_id={}", entry_id, update.effective_user.id)
    keyboard = [
        [
            InlineKeyboardButton("Yes, delete", callback_data=f"delyes:{entry_id}"),
            InlineKeyboardButton("Cancel", callback_data="delcancel"),
        ]
    ]
    await query.edit_message_text(
        f"Delete this entry?\n\n{entry['mood']} {entry['created_at'][:10]}\n{entry['thought']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_TEXT


async def delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "delcancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    await db.delete_entry(entry_id)
    log.info("entry_deleted entry_id={} user_id={}", entry_id, update.effective_user.id)
    await query.edit_message_text("✓ Entry deleted!")
    return ConversationHandler.END


# ── /import ─────────────────────────────────────────────

async def cmd_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        log.debug("import_no_args user_id={}", update.effective_user.id)
        await update.message.reply_text(
            "Usage: /import YYYY-MM-DD [HHMM]\n"
            "Accepts YYYY-MM-DD, YYYY/MM/DD, or YYYYMMDD.\n"
            "Optional time: HHMM, HH:MM, HHMMSS, or HH:MM:SS.\n"
            "Then send the text on the next line."
        )
        return ConversationHandler.END

    try:
        target_date = parse_date(args[0])
    except (ValueError, TypeError):
        await update.message.reply_text("Invalid date format. Use YYYY-MM-DD, YYYY/MM/DD, or YYYYMMDD.")
        return ConversationHandler.END

    h, m, s = 12, 0, 0
    if len(args) > 1:
        try:
            h, m, s = parse_time(args[1])
        except ValueError:
            await update.message.reply_text("Invalid time format. Use HHMM or HHMMSS.")
            return ConversationHandler.END

    tz = ZoneInfo(TIMEZONE)
    target_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, s, tzinfo=tz)
    context.user_data["import_date"] = target_dt
    await update.message.reply_text("Send me the entry text (or /cancel to abort):")
    return IMPORT_DATE


async def import_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import_date = context.user_data.get('import_date')
    log.debug("import_text_received user_id={} import_date={}", update.effective_user.id, import_date)
    context.user_data["import_text"] = update.message.text
    context.user_data["import_message_id"] = update.message.message_id
    keyboard = [[InlineKeyboardButton(m, callback_data=f"imood:{m}")] for m in MOODS]
    keyboard.append([InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)])
    await update.message.reply_text("Pick a mood:", reply_markup=InlineKeyboardMarkup(keyboard))
    return IMPORT_MOOD


async def import_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    mood = query.data.split(":", 1)[1]
    target_dt = context.user_data["import_date"]
    text = context.user_data["import_text"]

    dt_utc = target_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    log.debug("import_saving user_id={} target_dt={} dt_utc={}", update.effective_user.id, target_dt, dt_utc)

    message_id = context.user_data.get("import_message_id")

    db_conn = await db.get_db()
    cursor = await db_conn.execute(
        "INSERT INTO entries (message_id, mood, thought, created_at) VALUES (?, ?, ?, ?)",
        (message_id, mood, text, dt_utc.strftime("%Y-%m-%d %H:%M:%S")),
    )
    await db_conn.commit()

    # verify what was stored
    row = await db_conn.execute("SELECT created_at FROM entries WHERE id = ?", (cursor.lastrowid,))
    stored = await row.fetchone()
    log.debug("import_stored entry_id={} created_at={}", cursor.lastrowid, stored[0] if stored else "N/A")

    label = MOOD_LABELS.get(mood, "")
    log.info("entry_imported entry_id={} mood={} target_dt={} user_id={}", cursor.lastrowid, mood, target_dt, update.effective_user.id)
    await query.edit_message_text(f"✓ Imported! {mood} {label} — {target_dt:%Y-%m-%d %H:%M:%S}")
    return ConversationHandler.END


# ── /settings ───────────────────────────────────────────

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.debug("settings_opened user_id={}", update.effective_user.id)
    current_start = await db.get_setting("reminder_start") or "9"
    current_end = await db.get_setting("reminder_end") or "21"
    current_memory = await db.get_setting("memory_time") or "09:00"

    keyboard = [
        [InlineKeyboardButton(f"Remind window: {current_start}:00 – {current_end}:00", callback_data="set:remind")],
        [InlineKeyboardButton(f"Memory time: {current_memory}", callback_data="set:memory")],
        [InlineKeyboardButton("✖ Cancel", callback_data=CANCEL)],
    ]
    await update.message.reply_text(
        "⚙️ Settings\n\nTap to change:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETTINGS_SELECT


async def settings_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    setting = query.data.split(":", 1)[1]
    context.user_data["setting_type"] = setting

    if setting == "remind":
        await query.edit_message_text(
            "Send reminder start and end hours, separated by a space.\n"
            "Example: 9 21 (means 9:00 AM to 9:00 PM)\n"
            "Hours are in your timezone (0-23).\n\n/cancel to abort."
        )
    elif setting == "memory":
        await query.edit_message_text(
            "Send the time for daily memory (HH:MM format).\n"
            "Example: 09:00\n\n/cancel to abort."
        )
    return SETTINGS_VALUE


async def settings_value_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting_type = context.user_data.get("setting_type")
    value = update.message.text.strip()

    if setting_type == "remind":
        parts = value.split()
        if len(parts) != 2:
            await update.message.reply_text("Please send two numbers separated by a space (e.g., 9 21).")
            return SETTINGS_VALUE
        try:
            start_h, end_h = int(parts[0]), int(parts[1])
            if not (0 <= start_h <= 23 and 0 <= end_h <= 23):
                raise ValueError
        except ValueError:
            await update.message.reply_text("Invalid hours. Use 0-23.")
            return SETTINGS_VALUE
        await db.set_setting("reminder_start", str(start_h))
        await db.set_setting("reminder_end", str(end_h))
        log.info("settings_updated user_id={} setting=reminder value='{}-{}'", update.effective_user.id, start_h, end_h)
        await update.message.reply_text(f"✓ Reminder window set to {start_h}:00 – {end_h}:00")

    elif setting_type == "memory":
        try:
            h, m = value.split(":")
            h, m = int(h), int(m)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except ValueError:
            await update.message.reply_text("Invalid time. Use HH:MM (e.g., 09:00).")
            return SETTINGS_VALUE
        await db.set_setting("memory_time", f"{h:02d}:{m:02d}")
        log.info("settings_updated user_id={} setting=memory value='{}'", update.effective_user.id, f"{h:02d}:{m:02d}")
        await update.message.reply_text(f"✓ Memory time set to {h:02d}:{m:02d}")

    return ConversationHandler.END


# ── /stats ──────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db.get_stats()
    log.debug("stats_retrieved user_id={} total={} this_month={} streak={}", update.effective_user.id, stats["total"], stats["this_month"], stats["current_streak"])

    mood_lines = []
    for mood, count in sorted(stats["mood_dist"].items(), key=lambda x: -x[1]):
        label = MOOD_LABELS.get(mood, "?")
        mood_lines.append(f"  {mood} {label}: {count}")

    text = (
        f"📊 Your Stats\n\n"
        f"Total entries: {stats['total']}\n"
        f"This month: {stats['this_month']}\n"
        f"Current streak: {stats['current_streak']} days\n"
        f"Longest streak: {stats['longest_streak']} days\n\n"
        f"Mood breakdown:\n" + "\n".join(mood_lines if mood_lines else ["  No data yet"])
    )
    await update.message.reply_text(text)


# ── /list ───────────────────────────────────────────────

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = get_now()
    entries = await db.get_all_entries_for_month(now.year, now.month, limit=31)
    log.debug("list_viewed user_id={} year={} month={} entry_count={}", update.effective_user.id, now.year, now.month, len(entries))

    if entries:
        context.user_data["list_mode"] = "month"
        context.user_data["list_year"] = now.year
        context.user_data["list_month"] = now.month
        context.user_data["list_offset"] = 0

        keyboard = _build_entry_buttons(entries)
        keyboard.append([InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev")])
        # keyboard.append([InlineKeyboardButton("\u2716 Cancel", callback_data="cancel")])

        await update.message.reply_text(
            f"\U0001f4d6 {now.strftime('%B %Y')} \u2014 {len(entries)} entries",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    older = await db.get_entries_before(now.year, now.month, limit=10)
    if not older:
        await update.message.reply_text(
            "No diary entries yet. Start writing by sending me a message! \U0001f4dd"
        )
        return

    context.user_data["list_mode"] = "history"
    first_local = db_to_local(older[0]["created_at"])
    context.user_data["list_year"] = first_local.year
    context.user_data["list_month"] = first_local.month
    context.user_data["list_offset"] = 10

    keyboard = _build_entry_buttons(older)
    nav_row = []
    nav_row.append(InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"))
    nav_row.append(InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"))
    keyboard.append(nav_row)

    await update.message.reply_text(
        f"\U0001f4d6 Older entries \u2014 {len(older)} shown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def list_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    mode = context.user_data.get("list_mode", "month")
    year = context.user_data.get("list_year")
    month = context.user_data.get("list_month")
    offset = context.user_data.get("list_offset", 0)

    if callback_data == "listprev":
        if mode == "month":
            context.user_data["list_mode"] = "history"
            context.user_data["list_offset"] = 10
            older = await db.get_entries_before(year, month, limit=10)
            if not older:
                await query.edit_message_text("No more entries.")
                return

            keyboard = _build_entry_buttons(older)
            nav_row = [
                InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
            ]
            keyboard.append(nav_row)

            await query.edit_message_text(
                f"\U0001f4d6 Older entries \u2014 {len(older)} shown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            new_offset = offset + 10
            entries = await db.get_entries_before(year, month, limit=10, offset=new_offset)
            if not entries:
                await query.edit_message_text("No more entries.")
                return

            context.user_data["list_offset"] = new_offset

            keyboard = _build_entry_buttons(entries)
            nav_row = [
                InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
            ]
            keyboard.append(nav_row)

            await query.edit_message_text(
                f"\U0001f4d6 Older entries \u2014 {len(entries)} shown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif callback_data == "listnext":
        if mode == "history":
            if offset <= 10:
                now = get_now()
                entries = await db.get_all_entries_for_month(now.year, now.month, limit=31)
                context.user_data["list_mode"] = "month"
                context.user_data["list_year"] = now.year
                context.user_data["list_month"] = now.month
                context.user_data["list_offset"] = 0

                keyboard = _build_entry_buttons(entries)
                keyboard.append([InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev")])
                # nav_row = [
                #     InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                #     InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
                # ]
                # keyboard.append(nav_row)


                await query.edit_message_text(
                    f"\U0001f4d6 {now.strftime('%B %Y')} \u2014 {len(entries)} entries",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                new_offset = offset - 10
                entries = await db.get_entries_before(year, month, limit=10, offset=new_offset)
                context.user_data["list_offset"] = new_offset

                keyboard = _build_entry_buttons(entries)
                nav_row = [
                    InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                    InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
                ]
                keyboard.append(nav_row)

                await query.edit_message_text(
                    f"\U0001f4d6 Newer entries \u2014 {len(entries)} shown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )


def _build_entry_buttons(entries: list[dict]) -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:40]}{'...' if len(e['thought']) > 40 else ''}",
            callback_data=f"view:{e['id']}",
        )]
        for e in entries
    ]


async def view_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warn("view_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text("Entry not found.")
        return

    text = format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
    )

    if entry["message_id"]:
        try:
            await query.message.reply_text(text, reply_to_message_id=entry["message_id"])
        except Exception as e:
            log.warn("view_reply_failed entry_id={} error={}", entry_id, str(e))
            await query.message.reply_text(text)
    else:
        await query.message.reply_text(text)


# ── /search ─────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Usage: /search <text>")
        return

    entries = await db.search_entries(query_text, limit=20)
    log.debug("search_completed user_id={} query='{}' result_count={}", update.effective_user.id, query_text, len(entries))
    if not entries:
        await update.message.reply_text(f'No entries matching "{query_text}".')
        return

    context.user_data["search_entries"] = {e["id"]: e for e in entries}

    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:40]}{'...' if len(e['thought']) > 40 else ''}",
            callback_data=f"srch:{e['id']}",
        )]
        for e in entries
    ]

    await update.message.reply_text(
        f'🔍 {len(entries)} result(s) for "{query_text}"',
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def search_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warn("search_result_not_found entry_id={}", entry_id)
        await query.edit_message_text("Entry not found.")
        return

    text = format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
    )

    if entry["message_id"]:
        try:
            await query.message.reply_text(text, reply_to_message_id=entry["message_id"])
        except Exception as e:
            log.warn("search_reply_failed entry_id={} error={}", entry_id, str(e))
            await query.message.reply_text(text)
    else:
        await query.message.reply_text(text)


# ── Memory (called by scheduler) ────────────────────────

async def send_memories(context):
    now = get_now()
    entries = await db.get_entries_on_this_day(now.month, now.day)
    chat_id = context.chat_id

    log.info("memory_check month={} day={} found_entries={}", now.month, now.day, len(entries))

    for entry in entries:
        text = format_memory(
            db_to_local(entry["created_at"]),
            entry["mood"],
            entry["thought"],
        )
        if entry["message_id"]:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_to_message_id=entry["message_id"],
                )
            except Exception as e:
                log.warn("memory_reply_failed entry_id={} error={}", entry["id"], str(e))
                await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)

    if entries:
        log.info("memories_sent count={}", len(entries))
