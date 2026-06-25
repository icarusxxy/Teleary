import logging
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
    delete_select_callback,
    delete_confirm_callback,
    cmd_import,
    import_text_receive,
    import_mood_callback,
    cmd_settings,
    settings_select_callback,
    settings_value_receive,
    cmd_stats,
    MOOD_PICK,
    EDIT_SELECT,
    EDIT_MOOD,
    EDIT_TEXT,
    IMPORT_DATE,
    IMPORT_MOOD,
    SETTINGS_SELECT,
    SETTINGS_VALUE,
)
from scheduler import init_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    await db.get_db()
    chat_id = (await application.bot.get_me()).id
    init_scheduler(application.bot, chat_id)


async def post_shutdown(application: Application):
    await db.close_db()


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    entry_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.AUDIO) & ~filters.COMMAND,
                receive_entry,
            )
        ],
        states={
            MOOD_PICK: [CallbackQueryHandler(mood_callback, pattern=r"^mood:")],
        },
        fallbacks=[],
    )

    edit_conv = ConversationHandler(
        entry_points=[CommandHandler("edit", cmd_edit)],
        states={
            EDIT_SELECT: [CallbackQueryHandler(edit_select_callback, pattern=r"^edit:")],
            EDIT_MOOD: [CallbackQueryHandler(edit_mood_callback, pattern=r"^emood:")],
            EDIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_receive),
                CommandHandler("skip", edit_text_skip),
            ],
        },
        fallbacks=[],
    )

    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", cmd_delete)],
        states={
            EDIT_SELECT: [CallbackQueryHandler(delete_select_callback, pattern=r"^del:")],
            EDIT_TEXT: [CallbackQueryHandler(delete_confirm_callback, pattern=r"^del(yes|cancel)")],
        },
        fallbacks=[],
    )

    import_conv = ConversationHandler(
        entry_points=[CommandHandler("import", cmd_import)],
        states={
            IMPORT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, import_text_receive)],
            IMPORT_MOOD: [CallbackQueryHandler(import_mood_callback, pattern=r"^imood:")],
        },
        fallbacks=[],
    )

    settings_conv = ConversationHandler(
        entry_points=[CommandHandler("settings", cmd_settings)],
        states={
            SETTINGS_SELECT: [CallbackQueryHandler(settings_select_callback, pattern=r"^set:")],
            SETTINGS_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_value_receive)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(entry_conv)
    app.add_handler(edit_conv)
    app.add_handler(delete_conv)
    app.add_handler(import_conv)
    app.add_handler(settings_conv)

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
