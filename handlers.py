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
from config import TIMEZONE
import emoji_config
import database as db
from i18n import get_text, get_lang_for_user
from utils import db_to_local, db_to_local_date, format_entry, format_memory, get_now, parse_date, parse_date_pattern, parse_time
from scheduler import set_chat_id

log = logger.bind(module="handlers")


async def _lang(update: Update) -> str:
    user = update.effective_user
    if update.callback_query:
        user = update.callback_query.from_user
    
    saved = await db.get_setting("language")
    if saved:
        return saved
    
    lang_code = user.language_code if user else None
    return get_lang_for_user(lang_code)


MOOD_PICK, ENTRY_TEXT, EDIT_SELECT, EDIT_MOOD, EDIT_TEXT = range(5)
IMPORT_DATE, IMPORT_MOOD = range(5, 7)
SETTINGS_SELECT, SETTINGS_VALUE = range(7, 9)
DELETE_SEARCH, DELETE_KEYWORD, DELETE_DATE = range(9, 12)
EDIT_SEARCH, EDIT_KEYWORD, EDIT_DATE = range(12, 15)
EMOJI_SETTINGS_MAIN, EMOJI_ADD, EMOJI_REMOVE, EMOJI_EDIT = range(15, 19)

CANCEL = "cancel"

_media_group_buffers: dict[str, list] = {}
_media_group_locks: dict[str, bool] = {}


def _cancel_keyboard(lang: str = "eng") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)]])


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.debug("conversation_cancelled user_id={}", update.effective_user.id)
    lang = await _lang(update)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(get_text("cancelled", lang))
    else:
        await update.message.reply_text(get_text("cancelled", lang))
    return ConversationHandler.END


# ── /start ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    log.info("user_started user_id={} chat_id={}", update.effective_user.id, chat_id)
    set_chat_id(chat_id)
    lang = await _lang(update)
    await update.message.reply_text(get_text("welcome", lang))


# ── New Entry ───────────────────────────────────────────

async def receive_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_chat_id(update.effective_chat.id)
    msg = update.message
    user_id = update.effective_user.id

    if msg.media_group_id:
        log.debug("media_group_received user_id={} group_id={}", user_id, msg.media_group_id)
        await _handle_media_group(update, context)
        return MOOD_PICK

    text = msg.text or msg.caption or ""
    log.debug("entry_received user_id={} text_len={} has_media={}", user_id, len(text), bool(msg.photo or msg.video))
    context.user_data["pending_text"] = text
    context.user_data["pending_message_id"] = msg.message_id

    lang = await _lang(update)
    moods = await emoji_config.get_moods()
    keyboard = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in moods]
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await msg.reply_text(
        get_text("how_are_you_feeling", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MOOD_PICK


async def _handle_media_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    group_id = msg.media_group_id

    if group_id not in _media_group_buffers:
        _media_group_buffers[group_id] = []

    _media_group_buffers[group_id].append(msg)

    async def _process_group():
        await asyncio.sleep(1.5)
        messages = _media_group_buffers.pop(group_id, [])
        _media_group_locks.pop(group_id, None)

        if not messages:
            log.warning("media_group_empty group_id={}", group_id)
            return

        messages.sort(key=lambda m: m.message_id)
        first_msg = messages[0]
        caption = first_msg.caption or ""
        message_ids = [m.message_id for m in messages]
        log.info("media_group_resolved group_id={} item_count={} caption_len={}", group_id, len(messages), len(caption))

        context.user_data["pending_text"] = caption
        context.user_data["pending_message_id"] = first_msg.message_id
        context.user_data["pending_media_group_ids"] = message_ids

        lang = await _lang(first_msg)
        moods = await emoji_config.get_moods()
        keyboard = [[InlineKeyboardButton(m, callback_data=f"mood:{m}")] for m in moods]
        keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
        await first_msg.reply_text(
            get_text("album_items_how_feeling", lang, count=len(messages)),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    if group_id not in _media_group_locks:
        _media_group_locks[group_id] = True
        asyncio.create_task(_process_group())


async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mood = query.data.split(":", 1)[1]
    text = context.user_data.pop("pending_text", "")
    message_id = context.user_data.pop("pending_message_id")
    context.user_data.pop("pending_media_group_ids", None)

    entry_id = await db.save_entry(message_id, mood, text)
    lang = await _lang(update)
    mood_labels = await emoji_config.get_mood_labels()
    label = mood_labels.get(mood, "")
    log.info("entry_saved entry_id={} mood={} text_len={} user_id={}", entry_id, mood, len(text), update.effective_user.id)
    await query.edit_message_text(get_text("saved_mood", lang, mood=mood, label=label))
    return ConversationHandler.END


# ── /edit ───────────────────────────────────────────────

async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update)
    keyboard = [
        [InlineKeyboardButton(get_text("edit_search_keyword", lang), callback_data="editsearch:keyword")],
        [InlineKeyboardButton(get_text("edit_search_date", lang), callback_data="editsearch:date")],
        [InlineKeyboardButton(get_text("edit_recent_entries", lang), callback_data="editsearch:recent")],
        [InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)],
    ]
    await update.message.reply_text(
        get_text("edit_how_find", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SEARCH


async def edit_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    search_type = query.data.split(":", 1)[1]

    if search_type == "keyword":
        await query.edit_message_text(get_text("edit_enter_keyword", lang))
        return EDIT_KEYWORD
    elif search_type == "date":
        await query.edit_message_text(get_text("edit_enter_date", lang))
        return EDIT_DATE
    elif search_type == "recent":
        entries = await db.get_recent_entries(10)
        if not entries:
            await query.edit_message_text(get_text("edit_no_entries", lang))
            return ConversationHandler.END

        context.user_data["edit_entries"] = entries
        keyboard = [
            [InlineKeyboardButton(
                f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
                callback_data=f"edit:{e['id']}",
            )]
            for e in entries
        ]
        keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
        await query.edit_message_text(
            get_text("edit_which_entry", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_SELECT


async def edit_keyword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    entries = await db.search_entries(query_text, limit=20)
    lang = await _lang(update)

    if not entries:
        await update.message.reply_text(get_text("edit_no_matching", lang, query=query_text))
        return ConversationHandler.END

    context.user_data["edit_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"edit:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await update.message.reply_text(
        get_text("edit_results_for", lang, count=len(entries), query=query_text),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def edit_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text.strip()
    lang = await _lang(update)
    
    # Validate format: YYYY, YYYY-MM, or YYYY-MM-DD
    import re
    if not re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", date_str):
        await update.message.reply_text(get_text("edit_invalid_date", lang))
        return EDIT_DATE

    entries = await db.get_entries_by_date_pattern(date_str)

    if not entries:
        await update.message.reply_text(get_text("edit_no_entries_for_date", lang, date=date_str))
        return ConversationHandler.END

    context.user_data["edit_entries"] = {e["id"]: e for e in entries}
    keyboard = [
        [InlineKeyboardButton(
            f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
            callback_data=f"edit:{e['id']}",
        )]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await update.message.reply_text(
        get_text("edit_entries_for", lang, count=len(entries), date=date_str),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("edit_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text(get_text("edit_not_found", lang))
        return ConversationHandler.END

    log.debug("edit_entry_selected entry_id={} user_id={}", entry_id, update.effective_user.id)
    context.user_data["editing_entry"] = entry
    moods = await emoji_config.get_moods()
    keyboard = [[InlineKeyboardButton(m, callback_data=f"emood:{m}")] for m in moods]
    keyboard.append([InlineKeyboardButton(get_text("keep_current", lang), callback_data="emood:keep")])
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await query.edit_message_text(
        get_text("edit_current", lang, mood=entry['mood'], thought=entry['thought']),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_MOOD


async def edit_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    mood = query.data.split(":", 1)[1]
    entry = context.user_data["editing_entry"]

    if mood != "keep":
        context.user_data["editing_mood"] = mood
    else:
        context.user_data["editing_mood"] = entry["mood"]

    log.debug("edit_mood_selected entry_id={} mood={}", entry["id"], mood)
    await query.edit_message_text(
        get_text("edit_new_text_prompt", lang, thought=entry['thought'])
    )
    return EDIT_TEXT


async def edit_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    thought = update.message.text
    lang = await _lang(update)

    await db.update_entry(entry["id"], mood=mood, thought=thought)
    log.info("entry_updated entry_id={} mood={} text_len={} user_id={}", entry["id"], mood, len(thought), update.effective_user.id)
    await update.message.reply_text(get_text("edit_updated", lang))
    return ConversationHandler.END


async def edit_text_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = context.user_data["editing_entry"]
    mood = context.user_data["editing_mood"]
    lang = await _lang(update)
    await db.update_entry(entry["id"], mood=mood)
    log.info("entry_mood_updated entry_id={} mood={} user_id={}", entry["id"], mood, update.effective_user.id)
    await update.message.reply_text(get_text("edit_updated", lang))
    return ConversationHandler.END


# ── /delete ─────────────────────────────────────────────

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.debug("delete_started user_id={}", update.effective_user.id)
    lang = await _lang(update)
    keyboard = [
        [InlineKeyboardButton(get_text("del_search_keyword", lang), callback_data="delsearch:keyword")],
        [InlineKeyboardButton(get_text("del_search_date", lang), callback_data="delsearch:date")],
        [InlineKeyboardButton(get_text("del_recent_entries", lang), callback_data="delsearch:recent")],
        [InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)],
    ]
    await update.message.reply_text(
        get_text("del_how_find", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return DELETE_SEARCH


async def delete_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    search_type = query.data.split(":", 1)[1]

    if search_type == "keyword":
        await query.edit_message_text(get_text("del_enter_keyword", lang))
        return DELETE_KEYWORD
    elif search_type == "date":
        await query.edit_message_text(get_text("del_enter_date", lang))
        return DELETE_DATE
    elif search_type == "recent":
        entries = await db.get_recent_entries(10)
        if not entries:
            await query.edit_message_text(get_text("del_no_entries", lang))
            return ConversationHandler.END

        context.user_data["delete_entries"] = entries
        keyboard = [
            [InlineKeyboardButton(
                f"{e['mood']} {db_to_local_date(e['created_at'])} — {e['thought'][:30]}...",
                callback_data=f"del:{e['id']}",
            )]
            for e in entries
        ]
        keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
        await query.edit_message_text(
            get_text("del_which_entry", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_SELECT


async def delete_keyword_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    entries = await db.search_entries(query_text, limit=20)
    lang = await _lang(update)

    if not entries:
        log.debug("delete_keyword_no_results query='{}' user_id={}", query_text, update.effective_user.id)
        await update.message.reply_text(get_text("del_no_matching", lang, query=query_text))
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
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await update.message.reply_text(
        get_text("del_results_for", lang, count=len(entries), query=query_text),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text.strip()
    lang = await _lang(update)
    
    # Validate format: YYYY, YYYY-MM, or YYYY-MM-DD
    import re
    if not re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", date_str):
        log.debug("delete_date_invalid_format input='{}' user_id={}", date_str, update.effective_user.id)
        await update.message.reply_text(get_text("del_invalid_date", lang))
        return DELETE_DATE

    entries = await db.get_entries_by_date_pattern(date_str)

    if not entries:
        log.debug("delete_date_no_results date='{}' user_id={}", date_str, update.effective_user.id)
        await update.message.reply_text(get_text("del_no_entries_for_date", lang, date=date_str))
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
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await update.message.reply_text(
        get_text("del_entries_for", lang, count=len(entries), date=date_str),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_SELECT


async def delete_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("delete_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text(get_text("del_not_found", lang))
        return ConversationHandler.END

    log.debug("delete_confirm_prompt entry_id={} user_id={}", entry_id, update.effective_user.id)
    keyboard = [
        [
            InlineKeyboardButton(get_text("yes_delete", lang), callback_data=f"delyes:{entry_id}"),
            InlineKeyboardButton(get_text("cancel", lang), callback_data="delcancel"),
        ]
    ]
    await query.edit_message_text(
        get_text("del_confirm", lang, mood=entry['mood'], date=entry['created_at'][:10], thought=entry['thought']),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_TEXT


async def delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == "delcancel":
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    entry_id = int(query.data.split(":", 1)[1])
    await db.delete_entry(entry_id)
    log.info("entry_deleted entry_id={} user_id={}", entry_id, update.effective_user.id)
    await query.edit_message_text(get_text("del_deleted", lang))
    return ConversationHandler.END


# ── /import ─────────────────────────────────────────────

async def cmd_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    lang = await _lang(update)
    if not args:
        log.debug("import_no_args user_id={}", update.effective_user.id)
        await update.message.reply_text(get_text("import_usage", lang))
        return ConversationHandler.END

    try:
        target_date = parse_date(args[0])
    except (ValueError, TypeError):
        await update.message.reply_text(get_text("import_invalid_date", lang))
        return ConversationHandler.END

    h, m, s = 12, 0, 0
    if len(args) > 1:
        try:
            h, m, s = parse_time(args[1])
        except ValueError:
            await update.message.reply_text(get_text("import_invalid_time", lang))
            return ConversationHandler.END

    tz = ZoneInfo(TIMEZONE)
    target_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, s, tzinfo=tz)
    context.user_data["import_date"] = target_dt
    await update.message.reply_text(get_text("import_send_text", lang))
    return IMPORT_DATE


async def import_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import_date = context.user_data.get('import_date')
    log.debug("import_text_received user_id={} import_date={}", update.effective_user.id, import_date)
    context.user_data["import_text"] = update.message.text
    context.user_data["import_message_id"] = update.message.message_id
    lang = await _lang(update)
    moods = await emoji_config.get_moods()
    keyboard = [[InlineKeyboardButton(m, callback_data=f"imood:{m}")] for m in moods]
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    await update.message.reply_text(get_text("import_pick_mood", lang), reply_markup=InlineKeyboardMarkup(keyboard))
    return IMPORT_MOOD


async def import_media_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    import_date = context.user_data.get('import_date')
    log.debug("import_media_received user_id={} import_date={} has_group={}", update.effective_user.id, import_date, bool(msg.media_group_id))

    if msg.media_group_id:
        group_id = msg.media_group_id
        if group_id not in _media_group_buffers:
            _media_group_buffers[group_id] = []
        _media_group_buffers[group_id].append(msg)

        async def _process_import_group():
            await asyncio.sleep(1.5)
            messages = _media_group_buffers.pop(group_id, [])
            _media_group_locks.pop(group_id, None)

            if not messages:
                log.warning("import_media_group_empty group_id={}", group_id)
                return

            messages.sort(key=lambda m: m.message_id)
            first_msg = messages[0]
            caption = first_msg.caption or ""
            message_ids = [m.message_id for m in messages]
            log.info("import_media_group_resolved group_id={} item_count={} caption_len={}", group_id, len(messages), len(caption))

            context.user_data["import_text"] = caption
            context.user_data["import_message_id"] = first_msg.message_id
            context.user_data["import_media_group_ids"] = message_ids

            lang = await _lang(first_msg)
            moods = await emoji_config.get_moods()
            keyboard = [[InlineKeyboardButton(m, callback_data=f"imood:{m}")] for m in moods]
            keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
            await first_msg.reply_text(
                get_text("import_album_pick_mood", lang, count=len(messages)),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        if group_id not in _media_group_locks:
            _media_group_locks[group_id] = True
            asyncio.create_task(_process_import_group())
    else:
        context.user_data["import_text"] = msg.caption or ""
        context.user_data["import_message_id"] = msg.message_id

        lang = await _lang(msg)
        moods = await emoji_config.get_moods()
        keyboard = [[InlineKeyboardButton(m, callback_data=f"imood:{m}")] for m in moods]
        keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
        await msg.reply_text(get_text("import_pick_mood", lang), reply_markup=InlineKeyboardMarkup(keyboard))
        return IMPORT_MOOD

    return IMPORT_MOOD


async def import_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    mood = query.data.split(":", 1)[1]
    target_dt = context.user_data["import_date"]
    text = context.user_data.get("import_text", "")

    dt_utc = target_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    log.debug("import_saving user_id={} target_dt={} dt_utc={}", update.effective_user.id, target_dt, dt_utc)

    message_id = context.user_data.get("import_message_id")
    media_ids = context.user_data.pop("import_media_group_ids", None)

    if media_ids:
        log.debug("import_media_group_ids={} count={}", media_ids, len(media_ids))

    db_conn = await db.get_db()
    cursor = await db_conn.execute(
        "INSERT INTO entries (message_id, mood, thought, created_at) VALUES (?, ?, ?, ?)",
        (message_id, mood, text, dt_utc.strftime("%Y-%m-%d %H:%M:%S")),
    )
    await db_conn.commit()

    row = await db_conn.execute("SELECT created_at FROM entries WHERE id = ?", (cursor.lastrowid,))
    stored = await row.fetchone()
    log.debug("import_stored entry_id={} created_at={}", cursor.lastrowid, stored[0] if stored else "N/A")

    mood_labels = await emoji_config.get_mood_labels()
    label = mood_labels.get(mood, "")
    log.info("entry_imported entry_id={} mood={} target_dt={} user_id={}", cursor.lastrowid, mood, target_dt, update.effective_user.id)
    media_count = f" ({len(media_ids)} items)" if media_ids else ""
    await query.edit_message_text(get_text("import_imported", lang, mood=mood, label=label, media=media_count, datetime=target_dt.strftime('%Y-%m-%d %H:%M:%S')))
    return ConversationHandler.END


# ── /settings ───────────────────────────────────────────

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.debug("settings_opened user_id={}", update.effective_user.id)
    return await _show_settings_menu(update, context)


async def _show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update)
    current_start = await db.get_setting("reminder_start") or "9"
    current_end = await db.get_setting("reminder_end") or "21"
    current_memory = await db.get_setting("memory_time") or "09:00"

    keyboard = [
        [InlineKeyboardButton(get_text("settings_remind_window", lang, start=current_start, end=current_end), callback_data="set:remind")],
        [InlineKeyboardButton(get_text("settings_memory_time", lang, time=current_memory), callback_data="set:memory")],
        [InlineKeyboardButton(get_text("settings_emojis", lang), callback_data="set:emoji")],
        [InlineKeyboardButton(get_text("settings_language", lang), callback_data="set:language")],
        [InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)],
    ]

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            get_text("settings_title", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            get_text("settings_title", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return SETTINGS_SELECT


async def settings_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(get_text("cancelled", lang))
        return ConversationHandler.END

    setting = query.data.split(":", 1)[1]
    context.user_data["setting_type"] = setting

    if setting == "remind":
        await query.edit_message_text(get_text("settings_remind_prompt", lang))
    elif setting == "memory":
        await query.edit_message_text(get_text("settings_memory_prompt", lang))
    elif setting == "emoji":
        return await _show_emoji_list(update, context)
    elif setting == "language":
        return await _show_language_menu(update, context)
    return SETTINGS_VALUE


async def settings_value_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting_type = context.user_data.get("setting_type")
    value = update.message.text.strip()
    lang = await _lang(update)

    if setting_type == "remind":
        parts = value.split()
        if len(parts) != 2:
            await update.message.reply_text(get_text("settings_invalid_two_numbers", lang))
            return SETTINGS_VALUE
        try:
            start_h, end_h = int(parts[0]), int(parts[1])
            if not (0 <= start_h <= 23 and 0 <= end_h <= 23):
                raise ValueError
        except ValueError:
            await update.message.reply_text(get_text("settings_invalid_hours", lang))
            return SETTINGS_VALUE
        await db.set_setting("reminder_start", str(start_h))
        await db.set_setting("reminder_end", str(end_h))
        log.info("settings_updated user_id={} setting=reminder value='{}-{}'", update.effective_user.id, start_h, end_h)
        await update.message.reply_text(get_text("settings_remind_set", lang, start=start_h, end=end_h))

    elif setting_type == "memory":
        try:
            h, m = value.split(":")
            h, m = int(h), int(m)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except ValueError:
            await update.message.reply_text(get_text("settings_invalid_time", lang))
            return SETTINGS_VALUE
        await db.set_setting("memory_time", f"{h:02d}:{m:02d}")
        log.info("settings_updated user_id={} setting=memory value='{}'", update.effective_user.id, f"{h:02d}:{m:02d}")
        await update.message.reply_text(get_text("settings_memory_set", lang, time=f"{h:02d}:{m:02d}"))

    return ConversationHandler.END


# ── Language settings (part of /settings) ────────────────

LANGUAGE_SELECT = 19

async def _show_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from i18n import get_available_langs, get_lang_name
    lang = await _lang(update)
    
    available = get_available_langs()
    current = await db.get_setting("language") or lang
    
    keyboard = []
    for lang_code in available:
        name = get_lang_name(lang_code)
        prefix = "✓ " if lang_code == current else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"lang:{lang_code}")])
    
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            get_text("language_select", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            get_text("language_select", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return LANGUAGE_SELECT


async def language_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        return await _show_settings_menu(update, context)

    selected_lang = query.data.split(":", 1)[1]
    await db.set_setting("language", selected_lang)
    
    from i18n import get_lang_name
    lang_name = get_lang_name(selected_lang)
    log.info("language_set user_id={} language={}", update.effective_user.id, selected_lang)
    
    await query.edit_message_text(get_text("language_set", lang, language=lang_name))
    return ConversationHandler.END


# ── Emoji settings (part of /settings) ─────────────────

async def _show_emoji_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update)
    moods_full = await emoji_config.get_moods_full()
    text_lines = [get_text("emoji_current", lang)]
    keyboard = []

    for item in moods_full:
        text_lines.append(f"  {item['emoji']} {item['label']}")
        keyboard.append([
            InlineKeyboardButton(f"{item['emoji']} {item['label']}", callback_data=f"emojiset:edit:{item['emoji']}"),
            InlineKeyboardButton(get_text("emoji_remove_btn", lang), callback_data=f"emojiset:remove:{item['emoji']}"),
        ])

    keyboard.append([InlineKeyboardButton(get_text("emoji_add_btn", lang), callback_data="emojiset:add")])
    keyboard.append([InlineKeyboardButton(get_text("emoji_reset_btn", lang), callback_data="emojiset:reset")])
    keyboard.append([InlineKeyboardButton(get_text("cancel", lang), callback_data=CANCEL)])

    text = "\n".join(text_lines) + "\n\n" + get_text("emoji_tap_prompt", lang)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    return EMOJI_SETTINGS_MAIN


async def emoji_settings_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == CANCEL:
        return await _show_settings_menu(update, context)

    action = query.data.split(":", 1)[1]

    if action == "add":
        await query.edit_message_text(get_text("emoji_add_prompt", lang))
        return EMOJI_ADD

    if action == "reset":
        default_list = "\n".join(f"  {m['emoji']} {m['label']}" for m in emoji_config.DEFAULT_MOODS)
        keyboard = [
            [
                InlineKeyboardButton(get_text("yes_reset", lang), callback_data="emojiset:confirmreset"),
                InlineKeyboardButton(get_text("cancel", lang), callback_data="emojiset:cancelreset"),
            ]
        ]
        await query.edit_message_text(
            get_text("emoji_reset_confirm", lang, defaults=default_list),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EMOJI_REMOVE

    if action.startswith("edit:"):
        emoji = action.split(":", 1)[1]
        moods_full = await emoji_config.get_moods_full()
        item = next((m for m in moods_full if m["emoji"] == emoji), None)
        if not item:
            await query.edit_message_text(get_text("emoji_not_found", lang))
            return await _show_settings_menu(update, context)

        context.user_data["editing_emoji"] = emoji
        await query.edit_message_text(
            get_text("emoji_edit_prompt", lang, emoji=item['emoji'], label=item['label'])
        )
        return EMOJI_EDIT

    if action.startswith("remove:"):
        emoji = action.split(":", 1)[1]
        moods_full = await emoji_config.get_moods_full()
        item = next((m for m in moods_full if m["emoji"] == emoji), None)
        if not item:
            await query.edit_message_text(get_text("emoji_not_found", lang))
            return await _show_settings_menu(update, context)

        keyboard = [
            [
                InlineKeyboardButton(get_text("yes_remove", lang), callback_data=f"emojiset:confirmremove:{emoji}"),
                InlineKeyboardButton(get_text("cancel", lang), callback_data="emojiset:cancelremove"),
            ]
        ]
        await query.edit_message_text(
            get_text("emoji_remove_confirm", lang, emoji=item['emoji'], label=item['label']),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EMOJI_REMOVE

    return EMOJI_SETTINGS_MAIN


async def emoji_add_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    lang = await _lang(update)

    if len(parts) < 2:
        await update.message.reply_text(get_text("emoji_send_emoji_label", lang))
        return EMOJI_ADD

    emoji, label = parts[0], parts[1]

    moods_full = await emoji_config.get_moods_full()
    if any(m["emoji"] == emoji for m in moods_full):
        await update.message.reply_text(get_text("emoji_already_exists", lang, emoji=emoji))
        return EMOJI_ADD

    moods_full.append({"emoji": emoji, "label": label})
    await emoji_config.set_moods(moods_full)
    log.info("emoji_added emoji={} label={} user_id={}", emoji, label, update.effective_user.id)
    await update.message.reply_text(get_text("emoji_added", lang, emoji=emoji, label=label))

    return await _show_settings_menu(update, context)


async def emoji_edit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    old_emoji = context.user_data.pop("editing_emoji", None)
    lang = await _lang(update)
    if not old_emoji:
        await update.message.reply_text(get_text("emoji_something_wrong", lang))
        return await _show_settings_menu(update, context)

    text = update.message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await update.message.reply_text(get_text("emoji_send_emoji_label", lang))
        return EMOJI_EDIT

    new_emoji, new_label = parts[0], parts[1]

    moods_full = await emoji_config.get_moods_full()
    if new_emoji != old_emoji and any(m["emoji"] == new_emoji for m in moods_full):
        await update.message.reply_text(get_text("emoji_already_exists", lang, emoji=new_emoji))
        return EMOJI_EDIT

    for item in moods_full:
        if item["emoji"] == old_emoji:
            item["emoji"] = new_emoji
            item["label"] = new_label
            break

    await emoji_config.set_moods(moods_full)
    log.info("emoji_updated old_emoji={} new_emoji={} new_label={} user_id={}", old_emoji, new_emoji, new_label, update.effective_user.id)
    await update.message.reply_text(get_text("emoji_updated", lang, old_emoji=old_emoji, new_emoji=new_emoji, new_label=new_label))

    return await _show_settings_menu(update, context)


async def emoji_remove_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)

    if query.data == "emojiset:cancelremove":
        return await _show_settings_menu(update, context)

    if query.data == "emojiset:cancelreset":
        return await _show_emoji_list(update, context)

    if query.data == "emojiset:confirmreset":
        await emoji_config.set_moods(emoji_config.DEFAULT_MOODS)
        log.info("emojis_reset_to_default user_id={}", update.effective_user.id)
        return await _show_emoji_list(update, context)

    emoji = query.data.split(":", 2)[2]
    moods_full = await emoji_config.get_moods_full()
    moods_full = [m for m in moods_full if m["emoji"] != emoji]
    await emoji_config.set_moods(moods_full)
    log.info("emoji_removed emoji={} user_id={}", emoji, update.effective_user.id)
    await query.edit_message_text(get_text("emoji_removed", lang, emoji=emoji))

    return await _show_settings_menu(update, context)


# ── /stats ──────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db.get_stats()
    lang = await _lang(update)
    log.debug("stats_retrieved user_id={} total={} this_month={} streak={}", update.effective_user.id, stats["total"], stats["this_month"], stats["current_streak"])

    mood_labels = await emoji_config.get_mood_labels()
    mood_lines = []
    for mood, count in sorted(stats["mood_dist"].items(), key=lambda x: -x[1]):
        label = mood_labels.get(mood, "?")
        mood_lines.append(f"  {mood} {label}: {count}")

    text = get_text("stats_title", lang, total=stats['total'], this_month=stats['this_month'], streak=stats['current_streak'], longest=stats['longest_streak']) + "\n".join(mood_lines if mood_lines else [get_text("stats_no_data", lang)])
    await update.message.reply_text(text)


# ── /list ───────────────────────────────────────────────

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = get_now()
    entries = await db.get_all_entries_for_month(now.year, now.month, limit=31)
    lang = await _lang(update)
    log.debug("list_viewed user_id={} year={} month={} entry_count={}", update.effective_user.id, now.year, now.month, len(entries))

    if entries:
        context.user_data["list_mode"] = "month"
        context.user_data["list_year"] = now.year
        context.user_data["list_month"] = now.month
        context.user_data["list_offset"] = 0

        keyboard = _build_entry_buttons(entries)
        keyboard.append([InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev")])

        await update.message.reply_text(
            get_text("list_month_header", lang, month=now.strftime('%B %Y'), count=len(entries)),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    older = await db.get_entries_before(now.year, now.month, limit=10)
    if not older:
        await update.message.reply_text(get_text("list_no_entries", lang))
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
        get_text("list_older_shown", lang, count=len(older)),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def list_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)
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
                await query.edit_message_text(get_text("list_no_more", lang))
                return

            keyboard = _build_entry_buttons(older)
            nav_row = [
                InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
            ]
            keyboard.append(nav_row)

            await query.edit_message_text(
                get_text("list_older_shown", lang, count=len(older)),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            new_offset = offset + 10
            entries = await db.get_entries_before(year, month, limit=10, offset=new_offset)
            if not entries:
                await query.edit_message_text(get_text("list_no_more", lang))
                return

            context.user_data["list_offset"] = new_offset

            keyboard = _build_entry_buttons(entries)
            nav_row = [
                InlineKeyboardButton("\u2b05\ufe0f", callback_data="listprev"),
                InlineKeyboardButton("\u27a1\ufe0f", callback_data="listnext"),
            ]
            keyboard.append(nav_row)

            await query.edit_message_text(
                get_text("list_older_shown", lang, count=len(entries)),
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

                await query.edit_message_text(
                    get_text("list_month_header", lang, month=now.strftime('%B %Y'), count=len(entries)),
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
                    get_text("list_newer_shown", lang, count=len(entries)),
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

    lang = await _lang(update)
    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("view_entry_not_found entry_id={}", entry_id)
        await query.edit_message_text(get_text("search_not_found", lang))
        return

    text = await format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
        lang=lang,
    )

    if entry["message_id"]:
        try:
            await query.message.reply_text(text, reply_to_message_id=entry["message_id"])
        except Exception as e:
            log.warning("view_reply_failed entry_id={} error={}", entry_id, str(e))
            await query.message.reply_text(text)
    else:
        await query.message.reply_text(text)


# ── /search ─────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = " ".join(context.args) if context.args else ""
    lang = await _lang(update)
    if not query_text:
        await update.message.reply_text(get_text("search_usage", lang))
        return

    entries = await db.search_entries(query_text, limit=20)
    log.debug("search_completed user_id={} query='{}' result_count={}", update.effective_user.id, query_text, len(entries))
    if not entries:
        await update.message.reply_text(get_text("search_no_matching", lang, query=query_text))
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
        get_text("search_results", lang, count=len(entries), query=query_text),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def search_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = await _lang(update)
    entry_id = int(query.data.split(":", 1)[1])
    entry = await db.get_entry(entry_id)
    if not entry:
        log.warning("search_result_not_found entry_id={}", entry_id)
        await query.edit_message_text(get_text("search_not_found", lang))
        return

    text = await format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
        lang=lang,
    )

    if entry["message_id"]:
        try:
            await query.message.reply_text(text, reply_to_message_id=entry["message_id"])
        except Exception as e:
            log.warning("search_reply_failed entry_id={} error={}", entry_id, str(e))
            await query.message.reply_text(text)
    else:
        await query.message.reply_text(text)


# ── /random ─────────────────────────────────────────────

async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry = await db.get_random_entry()
    lang = await _lang(update)
    if not entry:
        await update.message.reply_text(get_text("list_no_entries", lang))
        return

    text = await format_entry(
        db_to_local(entry["created_at"]),
        entry["mood"],
        entry["thought"],
        lang=lang,
    )

    if entry["message_id"]:
        try:
            await update.message.reply_text(text, reply_to_message_id=entry["message_id"])
        except Exception as e:
            log.warning("random_reply_failed entry_id={} error={}", entry["id"], str(e))
            await update.message.reply_text(text)
    else:
        await update.message.reply_text(text)


# ── /search_by_date ─────────────────────────────────────

async def cmd_search_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    raw = " ".join(context.args) if context.args else ""
    lang = await _lang(update)
    if not raw:
        await update.message.reply_text(get_text("search_by_date_usage", lang))
        return

    try:
        pattern = parse_date_pattern(raw)
    except ValueError:
        await update.message.reply_text(get_text("search_by_date_invalid", lang, raw=raw))
        return

    entries = await db.get_entries_by_date_pattern(pattern, limit=30)
    log.debug("search_by_date user_id={} pattern='{}' result_count={}", update.effective_user.id, pattern, len(entries))

    if not entries:
        await update.message.reply_text(get_text("search_by_date_no_matching", lang, pattern=pattern))
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
        get_text("search_by_date_results", lang, count=len(entries), pattern=pattern),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Memory (called by scheduler) ────────────────────────

async def send_memories(context):
    now = get_now()
    entries = await db.get_entries_on_this_day(now.month, now.day)
    chat_id = context.chat_id

    log.info("memory_check month={} day={} found_entries={}", now.month, now.day, len(entries))

    for entry in entries:
        text = await format_memory(
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
                log.warning("memory_reply_failed entry_id={} error={}", entry["id"], str(e))
                await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)

    if entries:
        log.info("memories_sent count={}", len(entries))
