from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MediaItem:
    asset: Any
    asset_id: str
    filename: str
    created_text: str
    is_live: bool
    selected_photo: bool = False
    selected_live: bool = False

    @property
    def selected(self) -> bool:
        if self.is_live:
            return self.selected_photo and self.selected_live
        return self.selected_photo

    def select_pair(self, selected: bool) -> None:
        self.selected_photo = selected
        self.selected_live = selected and self.is_live

