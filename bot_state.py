"""
Shared bot state module.

This module holds shared state that is used by both handlers and scheduler.
By centralizing this state here to avoid circular imports between modules.
"""

# Global bot instance and chat_id
_bot = None
_chat_id = None


def set_bot(bot):
    """Set the global bot instance."""
    global _bot
    _bot = bot


def get_bot():
    """Get the global bot instance."""
    return _bot


def set_chat_id(chat_id: int):
    """Set the global chat_id."""
    global _chat_id
    _chat_id = chat_id


def get_chat_id() -> int | None:
    """Get the global chat_id."""
    return _chat_id
