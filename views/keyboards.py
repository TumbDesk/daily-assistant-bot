"""Inline keyboards for category follow-up selection (Telegram)."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.i18n_util import t
from services.types import CategoryDTO

# TODO: WhatsApp-like button layout when a second messenger backend exists


def build_category_suggestion_keyboard(
    event_id: str,
    categories: list[CategoryDTO],
    *,
    locale: str = "de",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for category in categories:
        label = category.name
        if len(label) > 28:
            label = label[:25] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📁 {label}",
                    callback_data=f"cat_set:{event_id}:{category.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("btn_category_skip", locale),
                callback_data=f"cat_skip:{event_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
