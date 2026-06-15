"""Helpers for Telegram API calls."""
from telegram import CallbackQuery
from telegram.error import BadRequest


async def safe_edit_message_text(
    query: CallbackQuery,
    text: str,
    *,
    reply_markup=None,
    parse_mode=None,
) -> None:
    """edit_message_text; ignores "Message is not modified"."""
    try:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
