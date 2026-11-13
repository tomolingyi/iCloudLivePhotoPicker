from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pyicloud_ipd.services.photos import PhotoAlbum, PhotoLibrary
from pyicloud_ipd.version_size import LivePhotoVersionSize

from icloud_live_picker.backend import ICloudBackend


class CloudKitFixture:
    """Transport fixture: rank zero is newest, as used by icloudpd --recent.

    Keep PhotoAlbum's query builder, 100-asset paging, record pairing and
    PhotoAsset decoding real; only replace the HTTP responses.
    """

    def __init__(self, count: int, reported_count: int | None = None) -> None:
        self.ids = [f"photo-{i:04d}" for i in range(count)]
        self.reported_count = count if reported_count is None else reported_count
        self.videos: set[str] = set()
        self.requests: list[tuple[int, str]] = []

    def post(self, url, *, data, headers):
        query = json.loads(data)
        if "batch" in query:
            response = {"batch": [{"records": [{"fields": {
                "itemCount": {"value": self.reported_count},
            }}]}]}
        else:
            filters = {item["fieldName"]: item["fieldValue"]["value"]
                       for item in query["query"]["filterBy"]}
            start, direction = filters["startRank"], filters["direction"]
            self.requests.append((start, direction))
            page_size = query["resultsLimit"] // 2
            indices = (range(start, min(start + page_size, len(self.ids)))
                       if direction == "ASCENDING"
                       else range(start, max(-1, start - page_size), -1))
            records = []
            for rank in indices:
                if not 0 <= rank < len(self.ids):
                    continue
                asset_id = self.ids[rank]
                video = asset_id in self.videos
                records.extend([
                    {"recordType": "CPLAsset", "recordName": "asset-" + asset_id,
                     "fields": {"masterRef": {"value": {"recordName": asset_id}},
                                "assetDate": {"value": 1794240000000 - rank * 60000}}},
                    {"recordType": "CPLMaster", "recordName": asset_id,
                     "fields": {"filenameEnc": {"type": "STRING", "value":
                                                asset_id + (".MOV" if video else ".HEIC")},
                                "itemType": {"value": "com.apple.quicktime-movie"
                                             if video else "public.heic"}}},
                ])
            response = {"records": records}
        return SimpleNamespace(json=lambda: response)

    def backend(self, album_name: str = "全部照片") -> ICloudBackend:
        props = (PhotoLibrary.WHOLE_COLLECTION if album_name == "全部照片"
                 else PhotoLibrary.SMART_FOLDERS[album_name])
        album = PhotoAlbum({}, self, "https://fixture.invalid", album_name, **props)
        backend = ICloudBackend()
        backend.api = SimpleNamespace(photos=SimpleNamespace(all=album, albums={album_name: album}))
        backend.LivePhotoVersionSize = LivePhotoVersionSize
        return backend


class PaginationTests(unittest.TestCase):
    def test_305_photos_first_300_include_latest_five_then_append_oldest_five(self) -> None:
        for album_name in ("全部照片", "Live"):
            with self.subTest(album=album_name):
                cloud = CloudKitFixture(305)
                backend = cloud.backend(album_name)
                first = backend.load_items_page(album_name, limit=300)
                ids = [item.asset_id for item in first.items]
                self.assertEqual(cloud.ids[:300], ids)
                self.assertFalse(first.exhausted)
                self.assertEqual([(0, "ASCENDING"), (100, "ASCENDING"),
                                  (200, "ASCENDING"), (300, "ASCENDING")], cloud.requests)
                second = backend.load_items_page(album_name, limit=300, known_asset_ids=set(ids))
                self.assertEqual(cloud.ids[300:], [item.asset_id for item in second.items])
                self.assertTrue(second.exhausted)
                self.assertEqual(305, len(set(ids + [item.asset_id for item in second.items])))

    def test_page_boundaries_and_load_all_have_no_gaps(self) -> None:
        for count in (0, 1, 99, 100, 101, 299, 300, 301, 305, 605):
            with self.subTest(count=count):
                cloud = CloudKitFixture(count)
                backend = cloud.backend()
                first = backend.load_items_page("全部照片", limit=300)
                ids = [item.asset_id for item in first.items]
                self.assertEqual(cloud.ids[:300], ids)
                self.assertEqual(count <= 300, first.exhausted)
                rest = backend.load_items_page("全部照片", limit=None, known_asset_ids=set(ids))
                self.assertEqual(cloud.ids, ids + [item.asset_id for item in rest.items])
                self.assertTrue(rest.exhausted)

    def test_stale_count_does_not_truncate_the_list_or_hide_newest(self) -> None:
        for reported in (0, 300, 310):
            with self.subTest(reported=reported):
                cloud = CloudKitFixture(305, reported_count=reported)
                page = cloud.backend().load_items_page("全部照片", limit=None)
                self.assertEqual(cloud.ids, [item.asset_id for item in page.items])
                self.assertTrue(page.exhausted)

    def test_new_head_records_and_duplicates_do_not_consume_page_quota(self) -> None:
        cloud = CloudKitFixture(10)
        backend = cloud.backend()
        first = backend.load_items_page("全部照片", limit=3)
        known = {item.asset_id for item in first.items}
        cloud.ids[:0] = ["new-a", "new-a", "new-b"]
        second = backend.load_items_page("全部照片", limit=3, known_asset_ids=known)
        self.assertEqual(["new-a", "new-b", "photo-0003"], [item.asset_id for item in second.items])
        self.assertFalse(second.exhausted)

    def test_videos_do_not_consume_photo_quota_or_numeric_start(self) -> None:
        cloud = CloudKitFixture(8)
        cloud.videos = {cloud.ids[0], cloud.ids[3]}
        backend = cloud.backend()
        first = backend.load_items_page("全部照片", limit=3)
        rest = backend.load_items_page("全部照片", start=3, limit=None)
        self.assertEqual([cloud.ids[i] for i in (1, 2, 4)], [item.asset_id for item in first.items])
        self.assertEqual(cloud.ids[5:], [item.asset_id for item in rest.items])
        self.assertTrue(rest.exhausted)

    def test_request_failure_is_not_reported_as_end_of_album(self) -> None:
        cloud = CloudKitFixture(305)
        backend = cloud.backend()
        original_post = cloud.post

        def fail_second_page(url, *, data, headers):
            if len(cloud.requests) >= 1:
                raise OSError("simulated network failure")
            return original_post(url, data=data, headers=headers)

        cloud.post = fail_second_page
        with self.assertRaisesRegex(OSError, "simulated network failure"):
            backend.load_items_page("全部照片", limit=300)
