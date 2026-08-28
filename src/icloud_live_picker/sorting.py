from __future__ import annotations

from .constants import (
    SORT_LIVE_FIRST,
    SORT_NAME_ASC,
    SORT_NAME_DESC,
    SORT_OLDEST,
)
from .models import MediaItem


def sort_media_items(items: list[MediaItem], mode: str) -> list[MediaItem]:
    """Return a sorted copy while keeping unknown dates at the end."""
    filename_key = lambda item: (item.filename.casefold(), item.asset_id)
    newest_key = lambda item: (
        bool(item.created_text),
        item.created_text,
        item.filename.casefold(),
        item.asset_id,
    )
    oldest_key = lambda item: (
        not bool(item.created_text),
        item.created_text,
        item.filename.casefold(),
        item.asset_id,
    )

    if mode == SORT_OLDEST:
        return sorted(items, key=oldest_key)
    if mode == SORT_NAME_ASC:
        return sorted(items, key=filename_key)
    if mode == SORT_NAME_DESC:
        return sorted(items, key=filename_key, reverse=True)

    newest = sorted(items, key=newest_key, reverse=True)
    if mode == SORT_LIVE_FIRST:
        return sorted(newest, key=lambda item: not item.is_live)
    return newest

