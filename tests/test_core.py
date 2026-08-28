from __future__ import annotations

import unittest

from icloud_live_picker.backend import ICloudBackend
from icloud_live_picker.constants import (
    SORT_LIVE_FIRST,
    SORT_NAME_ASC,
    SORT_NAME_DESC,
    SORT_NEWEST,
    SORT_OLDEST,
)
from icloud_live_picker.filenames import human_bytes, safe_filename, safe_session_stem
from icloud_live_picker.models import MediaItem
from icloud_live_picker.sorting import sort_media_items


class HelperTests(unittest.TestCase):
    def test_filename_session_and_size_helpers(self) -> None:
        self.assertEqual(safe_session_stem("+86138-1234-5678"), "8613812345678")
        self.assertEqual(safe_filename('IMG:<12>?.HEIC'), "IMG__12__.HEIC")
        self.assertEqual(human_bytes(1536), "1.5 KB")

    def test_descending_pagination_starts_at_last_rank(self) -> None:
        album_type = type("Album", (object,), {"__len__": lambda self: 205})
        album = album_type()
        album.offset = 0
        album._list_query_gen = lambda offset, list_type, query_filter=None: {
            "query": {
                "filterBy": [
                    {
                        "fieldName": "direction",
                        "fieldValue": {"value": "ASCENDING"},
                    }
                ]
            }
        }

        ICloudBackend._prepare_descending(album)

        self.assertEqual(album.offset, 204)
        query = album._list_query_gen(204, "CPLAssetAndMasterByAddedDate")
        self.assertEqual(query["query"]["filterBy"][0]["fieldValue"]["value"], "DESCENDING")
        album.increment_offset(1)
        self.assertEqual(album.offset, 203)


class SelectionAndSortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.items = [
            MediaItem(None, "1", "B.HEIC", "2024-02-01 10:00", False),
            MediaItem(None, "2", "A.HEIC", "2023-02-01 10:00", True),
            MediaItem(None, "3", "C.HEIC", "", False),
            MediaItem(None, "4", "D.HEIC", "2025-02-01 10:00", True),
        ]

    def names(self, mode: str) -> list[str]:
        return [item.filename for item in sort_media_items(self.items, mode)]

    def test_all_sort_modes(self) -> None:
        self.assertEqual(self.names(SORT_NEWEST), ["D.HEIC", "B.HEIC", "A.HEIC", "C.HEIC"])
        self.assertEqual(self.names(SORT_OLDEST), ["A.HEIC", "B.HEIC", "D.HEIC", "C.HEIC"])
        self.assertEqual(self.names(SORT_NAME_ASC), ["A.HEIC", "B.HEIC", "C.HEIC", "D.HEIC"])
        self.assertEqual(self.names(SORT_NAME_DESC), ["D.HEIC", "C.HEIC", "B.HEIC", "A.HEIC"])
        self.assertEqual(self.names(SORT_LIVE_FIRST), ["D.HEIC", "A.HEIC", "B.HEIC", "C.HEIC"])

    def test_pair_selection_selects_photo_and_mov(self) -> None:
        live = self.items[1]
        live.select_pair(True)
        self.assertTrue(live.selected_photo)
        self.assertTrue(live.selected_live)
        self.assertTrue(live.selected)

        photo = self.items[0]
        photo.select_pair(True)
        self.assertTrue(photo.selected_photo)
        self.assertFalse(photo.selected_live)
        self.assertTrue(photo.selected)

