"""
Settings handlers for the diary bot.

These handlers manage the settings conversation flow and its sub-flows:
1. /settings → cmd_settings → SETTINGS_SELECT
2. Select setting → SETTINGS_VALUE (for remind/memory) or sub-flow
3. Emoji management sub-flow (EMOJI_SETTINGS_MAIN → EMOJI_ADD/EDIT/REMOVE)
4. Language selection sub-flow (LANGUAGE_SELECT)
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from loguru import logger
import utils.emoji_config as emoji_config
import core.database as db
from core.i18n import get_text, get_available_langs, get_lang_name
from utils.validators import validate_reminder_window, validate_memory_time

from handlers.states import (
    SETTINGS_SELECT, SETTINGS_VALUE,
    EMOJI_SETTINGS_MAIN, EMOJI_ADD, EMOJI_REMOVE, EMOJI_EDIT,
    LANGUAGE_SELECT, CANCEL,
)
from handlers.common import lang

log = logger.bind(module="handlers.settings")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command - show settings menu."""
    log.debug("settings_opened user_id={}", update.effective_user.id)
    return await _show_settings_menu(update, context)


async def _show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the main settings menu with options."""
    user_lang = await lang(update)
    settings = await db.get_settings(["reminder_start", "reminder_end", "memory_time"])
    current_start = settings.get("reminder_start") or "9"
    current_end = settings.get("reminder_end") or "21"
    current_memory = settings.get("memory_time") or "09:00"

    keyboard = [
        [InlineKeyboardButton(await get_text("settings_remind_window", user_lang, start=current_start, end=current_end), callback_data="set:remind")],
        [InlineKeyboardButton(await get_text("settings_memory_time", user_lang, time=current_memory), callback_data="set:memory")],
        [InlineKeyboardButton(await get_text("settings_emojis", user_lang), callback_data="set:emoji")],
        [InlineKeyboardButton(await get_text("settings_language", user_lang), callback_data="set:language")],
        [InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)],
    ]

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            await get_text("settings_title", user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            await get_text("settings_title", user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return SETTINGS_SELECT


async def settings_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings menu selection - route to appropriate sub-flow."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        await query.edit_message_text(await get_text("cancelled", user_lang))
        return ConversationHandler.END

    setting = query.data.split(":", 1)[1]
    context.user_data["setting_type"] = setting

    if setting == "remind":
        await query.edit_message_text(await get_text("settings_remind_prompt", user_lang))
    elif setting == "memory":
        await query.edit_message_text(await get_text("settings_memory_prompt", user_lang))
    elif setting == "emoji":
        return await _show_emoji_list(update, context)
    elif setting == "language":
        return await _show_language_menu(update, context)
    return SETTINGS_VALUE


async def settings_value_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setting value input - update the setting."""
    setting_type = context.user_data.get("setting_type")
    value = update.message.text.strip()
    user_lang = await lang(update)

    if setting_type == "remind":
        parts = value.split()
        if len(parts) != 2:
            await update.message.reply_text(await get_text("settings_invalid_two_numbers", user_lang))
            return SETTINGS_VALUE
        
        is_valid, error_key = validate_reminder_window(parts[0], parts[1])
        if not is_valid:
            await update.message.reply_text(await get_text(error_key, user_lang))
            return SETTINGS_VALUE
        
        start_h, end_h = int(parts[0]), int(parts[1])
        await db.set_setting("reminder_start", str(start_h))
        await db.set_setting("reminder_end", str(end_h))
        log.info("settings_updated user_id={} setting=reminder value='{}-{}'", update.effective_user.id, start_h, end_h)
        await update.message.reply_text(await get_text("settings_remind_set", user_lang, start=start_h, end=end_h))

    elif setting_type == "memory":
        is_valid, error_key = validate_memory_time(value)
        if not is_valid:
            await update.message.reply_text(await get_text(error_key, user_lang))
            return SETTINGS_VALUE
        
        h, m = map(int, value.split(":"))
        await db.set_setting("memory_time", f"{h:02d}:{m:02d}")
        log.info("settings_updated user_id={} setting=memory value='{}'", update.effective_user.id, f"{h:02d}:{m:02d}")
        await update.message.reply_text(await get_text("settings_memory_set", user_lang, time=f"{h:02d}:{m:02d}"))

    return ConversationHandler.END


# ── Language settings (part of /settings) ────────────────

async def _show_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection menu."""
    user_lang = await lang(update)
    
    available = await get_available_langs()
    current = await db.get_setting("language") or user_lang
    
    keyboard = []
    for lang_code in available:
        name = get_lang_name(lang_code)
        prefix = "✓ " if lang_code == current else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"lang:{lang_code}")])
    
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            await get_text("language_select", user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            await get_text("language_select", user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return LANGUAGE_SELECT


async def language_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection - update user's language setting."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        return await _show_settings_menu(update, context)

    selected_lang = query.data.split(":", 1)[1]
    await db.set_setting("language", selected_lang)
    
    lang_name = get_lang_name(selected_lang)
    log.info("language_set user_id={} language={}", update.effective_user.id, selected_lang)
    
    await query.edit_message_text(await get_text("language_set", user_lang, language=lang_name))
    return ConversationHandler.END


# ── Emoji settings (part of /settings) ─────────────────

async def _show_emoji_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emoji management list."""
    user_lang = await lang(update)
    moods_full = await emoji_config.get_moods_full(user_lang)
    text_lines = [await get_text("emoji_current", user_lang)]
    keyboard = []

    for item in moods_full:
        text_lines.append(f"  {item['emoji']} {item['label']}")
        keyboard.append([
            InlineKeyboardButton(f"{item['emoji']} {item['label']}", callback_data=f"emojiset:edit:{item['emoji']}"),
            InlineKeyboardButton(await get_text("emoji_remove_btn", user_lang), callback_data=f"emojiset:remove:{item['emoji']}"),
        ])

    keyboard.append([InlineKeyboardButton(await get_text("emoji_add_btn", user_lang), callback_data="emojiset:add")])
    keyboard.append([InlineKeyboardButton(await get_text("emoji_reset_btn", user_lang), callback_data="emojiset:reset")])
    keyboard.append([InlineKeyboardButton(await get_text("cancel", user_lang), callback_data=CANCEL)])

    text = "\n".join(text_lines) + "\n\n" + await get_text("emoji_tap_prompt", user_lang)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    return EMOJI_SETTINGS_MAIN


async def emoji_settings_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle emoji settings menu actions."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == CANCEL:
        return await _show_settings_menu(update, context)

    action = query.data.split(":", 1)[1]

    if action == "add":
        await query.edit_message_text(await get_text("emoji_add_prompt", user_lang))
        return EMOJI_ADD

    if action == "reset":
        default_moods = await emoji_config.get_default_moods_full(user_lang)
        default_list = "\n".join(f"  {m['emoji']} {m['label']}" for m in default_moods)
        keyboard = [
            [
                InlineKeyboardButton(await get_text("yes_reset", user_lang), callback_data="emojiset:confirmreset"),
                InlineKeyboardButton(await get_text("cancel", user_lang), callback_data="emojiset:cancelreset"),
            ]
        ]
        await query.edit_message_text(
            await get_text("emoji_reset_confirm", user_lang, defaults=default_list),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EMOJI_REMOVE

    if action.startswith("edit:"):
        emoji = action.split(":", 1)[1]
        moods_full = await emoji_config.get_moods_full(user_lang)
        item = next((m for m in moods_full if m["emoji"] == emoji), None)
        if not item:
            await query.edit_message_text(await get_text("emoji_not_found", user_lang))
            return await _show_settings_menu(update, context)

        context.user_data["editing_emoji"] = emoji
        await query.edit_message_text(
            await get_text("emoji_edit_prompt", user_lang, emoji=item['emoji'], label=item['label'])
        )
        return EMOJI_EDIT

    if action.startswith("remove:"):
        emoji = action.split(":", 1)[1]
        moods_full = await emoji_config.get_moods_full(user_lang)
        item = next((m for m in moods_full if m["emoji"] == emoji), None)
        if not item:
            await query.edit_message_text(await get_text("emoji_not_found", user_lang))
            return await _show_settings_menu(update, context)

        keyboard = [
            [
                InlineKeyboardButton(await get_text("yes_remove", user_lang), callback_data=f"emojiset:confirmremove:{emoji}"),
                InlineKeyboardButton(await get_text("cancel", user_lang), callback_data="emojiset:cancelremove"),
            ]
        ]
        await query.edit_message_text(
            await get_text("emoji_remove_confirm", user_lang, emoji=item['emoji'], label=item['label']),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EMOJI_REMOVE

    return EMOJI_SETTINGS_MAIN


async def emoji_add_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new emoji input - add to mood list."""
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    user_lang = await lang(update)

    if len(parts) < 2:
        await update.message.reply_text(await get_text("emoji_send_emoji_label", user_lang))
        return EMOJI_ADD

    emoji, label = parts[0], parts[1]

    moods_raw = await emoji_config.get_raw_moods()
    if any(m["emoji"] == emoji for m in moods_raw):
        await update.message.reply_text(await get_text("emoji_already_exists", user_lang, emoji=emoji))
        return EMOJI_ADD

    moods_raw.append({"emoji": emoji, "label": label})
    await emoji_config.set_moods(moods_raw)
    log.info("emoji_added emoji={} label={} user_id={}", emoji, label, update.effective_user.id)
    await update.message.reply_text(await get_text("emoji_added", user_lang, emoji=emoji, label=label))

    return await _show_settings_menu(update, context)


async def emoji_edit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle emoji edit input - update existing emoji."""
    old_emoji = context.user_data.pop("editing_emoji", None)
    user_lang = await lang(update)
    if not old_emoji:
        await update.message.reply_text(await get_text("emoji_something_wrong", user_lang))
        return await _show_settings_menu(update, context)

    text = update.message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await update.message.reply_text(await get_text("emoji_send_emoji_label", user_lang))
        return EMOJI_EDIT

    new_emoji, new_label = parts[0], parts[1]

    moods_raw = await emoji_config.get_raw_moods()
    if new_emoji != old_emoji and any(m["emoji"] == new_emoji for m in moods_raw):
        await update.message.reply_text(await get_text("emoji_already_exists", user_lang, emoji=new_emoji))
        return EMOJI_EDIT

    for item in moods_raw:
        if item["emoji"] == old_emoji:
            item["emoji"] = new_emoji
            item["label"] = new_label
            break

    await emoji_config.set_moods(moods_raw)
    log.info("emoji_updated old_emoji={} new_emoji={} new_label={} user_id={}", old_emoji, new_emoji, new_label, update.effective_user.id)
    await update.message.reply_text(await get_text("emoji_updated", user_lang, old_emoji=old_emoji, new_emoji=new_emoji, new_label=new_label))

    return await _show_settings_menu(update, context)


async def emoji_remove_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle emoji remove/reset confirmation."""
    query = update.callback_query
    await query.answer()

    user_lang = await lang(update)

    if query.data == "emojiset:cancelremove":
        return await _show_settings_menu(update, context)

    if query.data == "emojiset:cancelreset":
        return await _show_emoji_list(update, context)

    if query.data == "emojiset:confirmreset":
        await emoji_config.set_moods(emoji_config.DEFAULT_MOODS)
        log.info("emojis_reset_to_default user_id={}", update.effective_user.id)
        return await _show_emoji_list(update, context)

    emoji = query.data.split(":", 2)[2]
    moods_raw = await emoji_config.get_raw_moods()
    moods_raw = [m for m in moods_raw if m["emoji"] != emoji]
    await emoji_config.set_moods(moods_raw)
    log.info("emoji_removed emoji={} user_id={}", emoji, update.effective_user.id)
    await query.edit_message_text(await get_text("emoji_removed", user_lang, emoji=emoji))

    return await _show_settings_menu(update, context)
