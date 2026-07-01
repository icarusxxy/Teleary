import os
from pathlib import Path
from loguru import logger
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.error import NetworkError, TelegramError

from core.config import BOT_TOKEN, DB_PATH
import core.database as db

log = logger.bind(module="bot")

# PID file for Docker health checks
PID_FILE = Path(DB_PATH).parent / ".pid"


# ---------- Error handler --------------------------------------------------
# Catches transient Telegram API errors (e.g. 502 Bad Gateway) that occur during polling or API calls.
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log exceptions raised by handlers or the polling loop."""
    if isinstance(context.error, NetworkError):
        log.warning("Transient network error (will retry): {}", context.error)
    elif isinstance(context.error, TelegramError):
        log.error("Telegram API error: {}", context.error)
    else:
        log.exception("Unhandled exception in handler", exc_info=context.error)

# Handler imports are grouped by feature. Each handler function is imported
# individually because ConversationHandler states reference specific callbacks —
# importing a module wouldn't work here without qualifying every reference.
from handlers import (
    cmd_start,
    cmd_help,
    cmd_language,
    receive_entry,
    mood_callback,
    cmd_edit,
    edit_search_callback,
    edit_keyword_receive,
    edit_date_receive,
    edit_select_callback,
    edit_mood_callback,
    edit_text_receive,
    edit_text_skip,
    cmd_delete,
    delete_search_callback,
    delete_keyword_receive,
    delete_date_receive,
    delete_select_callback,
    delete_confirm_callback,
    cmd_import,
    import_text_receive,
    import_media_receive,
    import_mood_callback,
    cmd_settings,
    settings_select_callback,
    settings_value_receive,
    emoji_settings_main_callback,
    emoji_add_receive,
    emoji_edit_receive,
    emoji_remove_confirm_callback,
    language_select_callback,
    cmd_stats,
    cmd_list,
    list_more_callback,
    view_entry_callback,
    cmd_search,
    cmd_random,
    cmd_search_by_date,
    search_result_callback,
    cancel,
    MOOD_PICK,
    EDIT_SELECT,
    EDIT_MOOD,
    EDIT_TEXT,
    IMPORT_DATE,
    IMPORT_MOOD,
    SETTINGS_SELECT,
    SETTINGS_VALUE,
    DELETE_SEARCH,
    DELETE_KEYWORD,
    DELETE_DATE,
    EDIT_SEARCH,
    EDIT_KEYWORD,
    EDIT_DATE,
    EMOJI_SETTINGS_MAIN,
    EMOJI_ADD,
    EMOJI_REMOVE,
    EMOJI_EDIT,
    LANGUAGE_SELECT,
)
from core.scheduler import init_scheduler


# Lifecycle hooks: post_init opens the DB and starts the scheduler after the
# Application is fully built; post_shutdown tears them down on SIGINT/SIGTERM.
async def post_init(application: Application):
    log.info("Initializing bot: opening database and starting scheduler")
    await db.get_db()
    
    # Write PID file for Docker health checks
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    log.info("PID file written pid={}", os.getpid())
    
    # chat_id is None initially — set to the user's chat_id on first /start or message.
    init_scheduler(application.bot, None)
    log.info("Bot initialized")


async def post_shutdown(application: Application):
    log.info("Shutting down: closing database and scheduler")
    
    # Clean up PID file
    if PID_FILE.exists():
        PID_FILE.unlink()
        log.debug("PID file removed")
    
    await db.close_db()
    log.info("Shutdown complete")


def main():
    log.info("Starting Teleary diary bot", version="1.0.0")
    
    app = Application.builder().token(BOT_TOKEN).build()

    # Register the error handler so transient errors are logged cleanly
    # instead of producing a full traceback.
    app.add_error_handler(error_handler)

    # Shared cancel button handler — reused across all conversation flows.
    # Pattern anchored with ^ and $ to avoid matching substrings like "cancel_something".
    cancel_cb = CallbackQueryHandler(cancel, pattern=r"^cancel$")

    # ConversationHandler lifecycle:
    # 1. User sends text/photo/media → receive_entry → MOOD_PICK
    # 2. User taps mood emoji → mood_callback → END (entry saved)
    #
    # Media groups (albums) arrive as multiple messages with the same media_group_id.
    # Buffer them with a 1.5s delay to collect all items before prompting for mood.
    entry_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.AUDIO) & ~filters.COMMAND,
                receive_entry,
            )
        ],
        states={
            MOOD_PICK: [
                CallbackQueryHandler(mood_callback, pattern=r"^mood:"),
                cancel_cb,
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_conv = ConversationHandler(
        entry_points=[CommandHandler("edit", cmd_edit)],
        states={
            EDIT_SEARCH: [
                CallbackQueryHandler(edit_search_callback, pattern=r"^editsearch:"),
                cancel_cb,
            ],
            EDIT_KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_keyword_receive),
            ],
            EDIT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_receive),
            ],
            EDIT_SELECT: [
                CallbackQueryHandler(edit_select_callback, pattern=r"^edit:"),
                cancel_cb,
            ],
            EDIT_MOOD: [
                CallbackQueryHandler(edit_mood_callback, pattern=r"^emood:"),
                cancel_cb,
            ],
            EDIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_receive),
                CommandHandler("skip", edit_text_skip),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", cmd_delete)],
        states={
            DELETE_SEARCH: [
                CallbackQueryHandler(delete_search_callback, pattern=r"^delsearch:"),
                cancel_cb,
            ],
            DELETE_KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_keyword_receive),
            ],
            DELETE_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_date_receive),
            ],
            EDIT_SELECT: [
                CallbackQueryHandler(delete_select_callback, pattern=r"^del:"),
                cancel_cb,
            ],
            EDIT_TEXT: [CallbackQueryHandler(delete_confirm_callback, pattern=r"^del(yes|cancel)")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    import_conv = ConversationHandler(
        entry_points=[CommandHandler("import", cmd_import)],
        states={
            IMPORT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_text_receive),
                MessageHandler(
                    (filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.AUDIO) & ~filters.COMMAND,
                    import_media_receive,
                ),
                # Media groups stay in IMPORT_DATE until all items are buffered,
                # so the mood callback must also be accepted in this state.
                CallbackQueryHandler(import_mood_callback, pattern=r"^imood:"),
                cancel_cb,
            ],
            IMPORT_MOOD: [
                CallbackQueryHandler(import_mood_callback, pattern=r"^imood:"),
                cancel_cb,
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    settings_conv = ConversationHandler(
        entry_points=[
            CommandHandler("settings", cmd_settings),
            CommandHandler("language", cmd_language),
        ],
        states={
            SETTINGS_SELECT: [
                CallbackQueryHandler(settings_select_callback, pattern=r"^set:"),
                cancel_cb,
            ],
            SETTINGS_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_value_receive)],
            EMOJI_SETTINGS_MAIN: [
                CallbackQueryHandler(emoji_settings_main_callback, pattern=r"^emojiset:"),
                cancel_cb,
            ],
            EMOJI_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, emoji_add_receive),
            ],
            EMOJI_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, emoji_edit_receive),
            ],
            EMOJI_REMOVE: [
                CallbackQueryHandler(emoji_remove_confirm_callback, pattern=r"^emojiset:"),
                cancel_cb,
            ],
            LANGUAGE_SELECT: [
                CallbackQueryHandler(language_select_callback, pattern=r"^lang:"),
                cancel_cb,
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Registration order matters: python-telegram-bot checks handlers top-to-bottom.
    # Commands must come first so /edit, /delete, /import aren't swallowed by entry_conv
    # (which catches all text messages). ConversationHandlers go last as catch-alls.
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("random", cmd_random))
    app.add_handler(CommandHandler("search_by_date", cmd_search_by_date))
    app.add_handler(CallbackQueryHandler(list_more_callback, pattern=r"^list(prev|next)$"))
    app.add_handler(CallbackQueryHandler(view_entry_callback, pattern=r"^view:"))
    app.add_handler(CallbackQueryHandler(search_result_callback, pattern=r"^srch:"))
    app.add_handler(import_conv)
    app.add_handler(edit_conv)
    app.add_handler(delete_conv)
    app.add_handler(settings_conv)
    app.add_handler(entry_conv)  # Must be last — catches all unmatched text/media

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    log.info("Bot starting with polling", pid=os.getpid())
    
    # Run the bot with proper signal handling
    # python-telegram-bot handles SIGINT/SIGTERM internally
    app.run_polling(
        drop_pending_updates=False,  # Ignore updates from downtime
        allowed_updates=["message", "callback_query"],  # Explicit update types
    )


if __name__ == "__main__":
    main()
