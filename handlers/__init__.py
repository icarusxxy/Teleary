"""
Handlers package for the diary bot.

This package re-exports all handler functions and state constants from the
legacy handlers module to maintain backward compatibility with bot.py.

Future phases will progressively move handler functions into feature-specific
modules within this package (entry.py, edit.py, delete.py, etc.).
"""

# Import state constants from the centralized states module
from handlers.states import (
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
    CANCEL,
)

# Import entry creation handlers from entry module
from handlers.entry import (
    cmd_start,
    cmd_help,
    cmd_language,
    receive_entry,
    mood_callback,
)

# Import edit handlers from edit module
from handlers.edit import (
    cmd_edit,
    edit_search_callback,
    edit_keyword_receive,
    edit_date_receive,
    edit_select_callback,
    edit_mood_callback,
    edit_text_receive,
    edit_text_skip,
)

# Import delete handlers from delete module
from handlers.delete import (
    cmd_delete,
    delete_search_callback,
    delete_keyword_receive,
    delete_date_receive,
    delete_select_callback,
    delete_confirm_callback,
)

# Import import handlers from import_flow module
from handlers.import_flow import (
    cmd_import,
    import_text_receive,
    import_media_receive,
    import_mood_callback,
)

# Import settings handlers from settings module
from handlers.settings import (
    cmd_settings,
    settings_select_callback,
    settings_value_receive,
    emoji_settings_main_callback,
    emoji_add_receive,
    emoji_edit_receive,
    emoji_remove_confirm_callback,
    language_select_callback,
)

# Import stats handler from stats module
from handlers.stats import cmd_stats

# Import list/browse handlers from list module
from handlers.list import (
    cmd_list,
    list_more_callback,
    view_entry_callback,
)

# Import search handlers from search module
from handlers.search import (
    cmd_search,
    search_result_callback,
    cmd_search_by_date,
)

# Import random handler from random module
from handlers.random import cmd_random

# Import memory handler from memory module
from handlers.memory import send_memories

# Import cancel handler from common module
from handlers.common import cancel

# Import handler functions from the legacy module (if any remain)
# from _handlers_old import (
#     # Handler functions
# )

# Re-export common helpers for backward compatibility
from handlers.common import (
    lang as _lang,
    mood_keyboard as _mood_keyboard,
    reply_to_entry as _reply_to_entry,
    handle_media_group as _handle_media_group,
    build_entry_buttons as _build_entry_buttons,
)

__all__ = [
    # Handler functions
    "cmd_start",
    "cmd_help",
    "cmd_language",
    "receive_entry",
    "mood_callback",
    "cmd_edit",
    "edit_search_callback",
    "edit_keyword_receive",
    "edit_date_receive",
    "edit_select_callback",
    "edit_mood_callback",
    "edit_text_receive",
    "edit_text_skip",
    "cmd_delete",
    "delete_search_callback",
    "delete_keyword_receive",
    "delete_date_receive",
    "delete_select_callback",
    "delete_confirm_callback",
    "cmd_import",
    "import_text_receive",
    "import_media_receive",
    "import_mood_callback",
    "cmd_settings",
    "settings_select_callback",
    "settings_value_receive",
    "emoji_settings_main_callback",
    "emoji_add_receive",
    "emoji_edit_receive",
    "emoji_remove_confirm_callback",
    "language_select_callback",
    "cmd_stats",
    "cmd_list",
    "list_more_callback",
    "view_entry_callback",
    "cmd_search",
    "cmd_random",
    "cmd_search_by_date",
    "search_result_callback",
    "cancel",
    "send_memories",
    # State constants
    "MOOD_PICK",
    "EDIT_SELECT",
    "EDIT_MOOD",
    "EDIT_TEXT",
    "IMPORT_DATE",
    "IMPORT_MOOD",
    "SETTINGS_SELECT",
    "SETTINGS_VALUE",
    "DELETE_SEARCH",
    "DELETE_KEYWORD",
    "DELETE_DATE",
    "EDIT_SEARCH",
    "EDIT_KEYWORD",
    "EDIT_DATE",
    "EMOJI_SETTINGS_MAIN",
    "EMOJI_ADD",
    "EMOJI_REMOVE",
    "EMOJI_EDIT",
    "LANGUAGE_SELECT",
]
