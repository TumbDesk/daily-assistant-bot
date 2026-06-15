"""Internal vs. localized source labels for event visibility."""
from services.i18n_util import t

SOURCE_PRIVATE_INTERNAL = "Privat"
SOURCE_GROUP_FALLBACK = "Gruppe"


def is_private_source(label: str) -> bool:
    return label == SOURCE_PRIVATE_INTERNAL


def display_source_label(label: str, locale: str = "de") -> str:
    if label == SOURCE_PRIVATE_INTERNAL:
        return t("source_private", locale)
    if label == SOURCE_GROUP_FALLBACK:
        return t("source_group", locale)
    return label
