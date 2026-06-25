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

from config import MOODS, MOOD_LABELS, TIMEZONE
import database as db
from utils import format_entry, format_memory, get_now
from scheduler import set_chat_id


MOOD_PICK, ENTRY_TEXT, EDIT_SELECT, EDIT_MOOD, EDIT_TEXT = range(5)
IMPORT_DATE, IMPORT_MOOD = range(5, 7)
SETTINGS_SELECT, SETTINGS_VALUE = range(7, 9)

_media_group_buffers: dict[str, list] = {}
_media_group_locks: dict[str, asyncio.Event] = {}


# ── /start ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "📖 Welcome to your Diary Bot!\n\n"
        "Send me any message — text, photo, video, or album — and I'll help you log it with a mood.\n\n"
        "Commands:\n"
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

    if msg.media_group_id:
        await _handle_media_group(update, context)
        return

    text = msg.text or msg.caption or ""
    context.user_data["pending_text"] = text
    context.user_data["pending_message_id"] = msg.message_id

    keyboard = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in MOODS]
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
            return

        messages.sort(key=lambda m: m.message_id)
        first_msg = messages[0]
        caption = first_msg.caption or ""
        message_ids = [m.message_id for m in messages]

        context.user_data["pending_text"] = caption
        context.user_data["pending_message_id"] = first_msg.message_id
        context.user_data["pending_media_group_ids"] = message_ids

        keyboard = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in MOODS]
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
    await query.edit_message_text(f"✓ Saved! {mood} {label}")
    return ConversationHandler.END


# ── /edit ───────────────────────────────────────────────

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = await db.get_recent_entries(10)
    if not entries:
        await update.message.reply_text("No entries to edit.")
        return ConversationHandler.END

    context.user_data["edit_entries"] = entries
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {e['created_at'][:10]} — {e['thought'][:30]}...",
            callback_data=f"edit:{e['id']}",
        )]
        for e in entries
    ]
    await update.message.reply_text(
        "Which entry do you want to edit?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        await query.edit_message_text("Entry not found.")
        return ConversationHandler.END

    context.user_data["editing_entry"] = entry
    keyboard = [[InlineKeyboardButton(m, callback_data=f"emood:{m}")] for m in MOODS]
    keyboard.append([InlineKeyboardButton("Keep current", callback_data="emood:keep")])
    await query.edit_message_text(
        f"Current: {entry['mood']} {entry['thought']}\n\nPick a new mood:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_MOOD


async def edit_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mood = query.data.split(":", 1)[1]
    entry = context.user_data["editing_entry"]

    if mood != "keep":
        context.user_data["editing_mood"] = mood
    else:
        context.user_data["editing_mood"] = entry["mood"]

    await query.edit_message_text(
        f"Current thought: {entry['thought']}\n\nSend me the new text (or /skip to keep current):"
    )
    return EDIT_TEXT


async def edit_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    thought = update.message.text

    await db.update_entry(entry["id"], mood=mood, thought=thought)
    await update.message.reply_text("✓ Entry updated!")
    return ConversationHandler.END


async def edit_text_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    await db.update_entry(entry["id"], mood=mood)
    await update.message.reply_text("✓ Entry updated!")
    return ConversationHandler.END


# ── /delete ─────────────────────────────────────────────

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = await db.get_recent_entries(10)
    if not entries:
        await update.message.reply_text("No entries to delete.")
        return ConversationHandler.END

    context.user_data["delete_entries"] = entries
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {e['created_at'][:10]} — {e['thought'][:30]}...",
            callback_data=f"del:{e['id']}",
        )]
        for e in entries
    ]
    await update.message.reply_text(
        "Which entry do you want to delete?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        await query.edit_message_text("Entry not found.")
        return ConversationHandler.END

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
    await query.edit_message_text("✓ Entry deleted!")
    return ConversationHandler.END


# ── /import ─────────────────────────────────────────────

async def cmd_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /import YYYY-MM-DD\nThen send the text on the next line.")
        return ConversationHandler.END

    try:
        target_date = date.fromisoformat(args[0])
    except ValueError:
        await update.message.reply_text("Invalid date format. Use YYYY-MM-DD.")
        return ConversationHandler.END

    context.user_data["import_date"] = target_date
    await update.message.reply_text("Send me the entry text:")
    return IMPORT_DATE


async def import_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["import_text"] = update.message.text
    keyboard = [[InlineKeyboardButton(m, callback_data=f"imood:{m}")] for m in MOODS]
    await update.message.reply_text("Pick a mood:", reply_markup=InlineKeyboardMarkup(keyboard))
    return IMPORT_MOOD


async def import_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mood = query.data.split(":", 1)[1]
    target_date = context.user_data["import_date"]
    text = context.user_data["import_text"]

    tz = ZoneInfo(TIMEZONE)
    dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, tzinfo=tz)

    db_conn = await db.get_db()
    cursor = await db_conn.execute(
        "INSERT INTO entries (mood, thought, created_at) VALUES (?, ?, ?)",
        (mood, text, dt.isoformat()),
    )
    await db_conn.commit()

    label = MOOD_LABELS.get(mood, "")
    await query.edit_message_text(f"✓ Imported! {mood} {label} — {target_date.isoformat()}")
    return ConversationHandler.END


# ── /settings ───────────────────────────────────────────

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_start = await db.get_setting("reminder_start") or "9"
    current_end = await db.get_setting("reminder_end") or "21"
    current_memory = await db.get_setting("memory_time") or "09:00"

    keyboard = [
        [InlineKeyboardButton(f"Remind window: {current_start}:00 – {current_end}:00", callback_data="set:remind")],
        [InlineKeyboardButton(f"Memory time: {current_memory}", callback_data="set:memory")],
    ]
    await update.message.reply_text(
        "⚙️ Settings\n\nTap to change:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETTINGS_SELECT


async def settings_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    setting = query.data.split(":", 1)[1]
    context.user_data["setting_type"] = setting

    if setting == "remind":
        await query.edit_message_text(
            "Send reminder start and end hours, separated by a space.\n"
            "Example: 9 21 (means 9:00 AM to 9:00 PM)\n"
            "Hours are in your timezone (0-23)."
        )
    elif setting == "memory":
        await query.edit_message_text(
            "Send the time for daily memory (HH:MM format).\n"
            "Example: 09:00"
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
        await update.message.reply_text(f"✓ Memory time set to {h:02d}:{m:02d}")

    return ConversationHandler.END


# ── /stats ──────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db.get_stats()

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


# ── Memory (called by scheduler) ────────────────────────

async def send_memories(context):
    now = get_now()
    entries = await db.get_entries_on_this_day(now.month, now.day)
    chat_id = context.chat_id

    for entry in entries:
        text = format_memory(
            datetime.fromisoformat(entry["created_at"]).replace(tzinfo=ZoneInfo(TIMEZONE)),
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
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)
