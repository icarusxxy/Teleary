"""
Conversation state constants for the diary bot.

These constants represent steps in conversation flows. python-telegram-bot uses
these integers to route incoming messages to the correct handler within a
ConversationHandler.

Each conversation flow has its own set of states. The numeric values are
arbitrary but must be unique within a ConversationHandler.
"""

# Entry creation flow
MOOD_PICK = 0
ENTRY_TEXT = 1

# Edit flow (search → select → mood → text)
EDIT_SELECT = 2
EDIT_MOOD = 3
EDIT_TEXT = 4

# Import flow
IMPORT_DATE = 5
IMPORT_MOOD = 6

# Settings flow
SETTINGS_SELECT = 7
SETTINGS_VALUE = 8

# Delete flow (search → select → confirm)
DELETE_SEARCH = 9
DELETE_KEYWORD = 10
DELETE_DATE = 11

# Edit search flow (separate from edit flow states)
EDIT_SEARCH = 12
EDIT_KEYWORD = 13
EDIT_DATE = 14

# Emoji settings sub-flow
EMOJI_SETTINGS_MAIN = 15
EMOJI_ADD = 16
EMOJI_REMOVE = 17
EMOJI_EDIT = 18

# Language selection
LANGUAGE_SELECT = 19

# Special callback data constant
CANCEL = "cancel"
