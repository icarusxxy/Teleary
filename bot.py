from loguru import logger
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import BOT_TOKEN
import database as db
from handlers import (
    cmd_start,
    receive_entry,
    mood_callback,
    cmd_edit,
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
    import_mood_callback,
    cmd_settings,
    settings_select_callback,
    settings_value_receive,
    cmd_stats,
    cmd_list,
    list_more_callback,
    view_entry_callback,
    cmd_search,
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
)
from scheduler import init_scheduler


async def post_init(application: Application):
    await db.get_db()
    chat_id = (await application.bot.get_me()).id
    init_scheduler(application.bot, chat_id)


async def post_shutdown(application: Application):
    await db.close_db()


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    cancel_cb = CallbackQueryHandler(cancel, pattern=r"^cancel$")

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
            IMPORT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, import_text_receive)],
            IMPORT_MOOD: [
                CallbackQueryHandler(import_mood_callback, pattern=r"^imood:"),
                cancel_cb,
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    settings_conv = ConversationHandler(
        entry_points=[CommandHandler("settings", cmd_settings)],
        states={
            SETTINGS_SELECT: [
                CallbackQueryHandler(settings_select_callback, pattern=r"^set:"),
                cancel_cb,
            ],
            SETTINGS_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_value_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(list_more_callback, pattern=r"^list(prev|next)$"))
    app.add_handler(CallbackQueryHandler(view_entry_callback, pattern=r"^view:"))
    app.add_handler(CallbackQueryHandler(search_result_callback, pattern=r"^srch:"))
    app.add_handler(import_conv)
    app.add_handler(edit_conv)
    app.add_handler(delete_conv)
    app.add_handler(settings_conv)
    app.add_handler(entry_conv)

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
