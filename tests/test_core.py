from __future__ import annotations

import unittest
from types import SimpleNamespace

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

    def test_pagination_resets_to_first_rank_without_reversing_upstream(self) -> None:
        album_type = type("Album", (object,), {"__len__": lambda self: 205})
        album = album_type()
        album.offset = 150
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

        original_query = album._list_query_gen
        ICloudBackend._prepare_album(album)

        self.assertEqual(album.offset, 0)
        self.assertIs(original_query, album._list_query_gen)
        query = album._list_query_gen(0, "CPLAssetAndMasterByAssetDateWithoutHiddenOrDeleted")
        self.assertEqual(query["query"]["filterBy"][0]["fieldValue"]["value"], "ASCENDING")

    def test_media_pages_continue_by_image_count_and_can_load_the_rest(self) -> None:
        assets = [
            SimpleNamespace(id="0", filename="IMG_0.HEIC", item_type="image", versions={}),
            SimpleNamespace(id="video", filename="CLIP.MOV", item_type="video", versions={}),
            SimpleNamespace(id="1", filename="IMG_1.JPG", item_type="image", versions={}),
            SimpleNamespace(id="2", filename="IMG_2.HEIC", item_type="image", versions={}),
            SimpleNamespace(id="3", filename="IMG_3.PNG", item_type="image", versions={}),
            SimpleNamespace(id="4", filename="IMG_4.HEIC", item_type="image", versions={}),
        ]

        class FakeAlbum:
            def __init__(self) -> None:
                self.offset = 0
                self._list_query_gen = lambda offset, list_type, query_filter=None: {
                    "query": {
                        "filterBy": [
                            {
                                "fieldName": "direction",
                                "fieldValue": {"value": "ASCENDING"},
                            }
                        ]
                    }
                }

            def __len__(self) -> int:
                return len(assets)

            def __iter__(self):
                return iter(assets[self.offset :])

        backend = ICloudBackend()
        backend.api = SimpleNamespace(photos=SimpleNamespace(all=FakeAlbum()))
        backend.LivePhotoVersionSize = SimpleNamespace(
            ORIGINAL="live-original",
            MEDIUM="live-medium",
            THUMB="live-thumb",
        )

        first = backend.load_items_page("全部照片", start=0, limit=2)
        second = backend.load_items_page("全部照片", start=2, limit=2)
        remainder = backend.load_items_page("全部照片", start=4, limit=None)

        self.assertEqual(["0", "1"], [item.asset_id for item in first.items])
        self.assertEqual(["2", "3"], [item.asset_id for item in second.items])
        self.assertEqual(["4"], [item.asset_id for item in remainder.items])
        self.assertFalse(first.exhausted)
        self.assertFalse(second.exhausted)
        self.assertTrue(remainder.exhausted)

    def test_media_page_continuation_recovers_new_head_assets_by_id(self) -> None:
        assets = [
            SimpleNamespace(id=str(index), filename=f"IMG_{index}.HEIC", item_type="image", versions={})
            for index in range(4)
        ]

        class ChangingAlbum:
            def __init__(self) -> None:
                self.offset = 0
                self.reported_total = 4
                self._list_query_gen = lambda offset, list_type, query_filter=None: {
                    "query": {
                        "filterBy": [
                            {
                                "fieldName": "direction",
                                "fieldValue": {"value": "ASCENDING"},
                            }
                        ]
                    }
                }

            def __len__(self) -> int:
                return self.reported_total

            def __iter__(self):
                return iter(assets[self.offset :])

        backend = ICloudBackend()
        backend.api = SimpleNamespace(photos=SimpleNamespace(all=ChangingAlbum()))
        backend.LivePhotoVersionSize = SimpleNamespace(
            ORIGINAL="live-original",
            MEDIUM="live-medium",
            THUMB="live-thumb",
        )

        first = backend.load_items_page("全部照片", limit=2)
        known_ids = {item.asset_id for item in first.items}
        assets[:0] = [
            SimpleNamespace(id="new-a", filename="NEW_A.HEIC", item_type="image", versions={}),
            SimpleNamespace(id="new-b", filename="NEW_B.HEIC", item_type="image", versions={}),
        ]
        fresh = backend.load_items_page("全部照片", limit=2)
        continued = backend.load_items_page(
            "全部照片",
            limit=2,
            known_asset_ids=known_ids,
        )

        self.assertEqual(["new-a", "new-b"], [item.asset_id for item in fresh.items])
        self.assertEqual(["new-a", "new-b"], [item.asset_id for item in continued.items])


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

