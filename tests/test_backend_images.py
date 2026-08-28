from __future__ import annotations

import io
import unittest
from types import SimpleNamespace

from PIL import Image

from icloud_live_picker.backend import ICloudBackend
from icloud_live_picker.models import MediaItem


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs: object) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse(self.content)


class BackendImageTests(unittest.TestCase):
    def setUp(self) -> None:
        source = Image.new("RGB", (1200, 900), "#278B82")
        encoded = io.BytesIO()
        source.save(encoded, format="JPEG", quality=95)
        self.session = FakeSession(encoded.getvalue())
        self.backend = ICloudBackend()
        self.backend.api = SimpleNamespace(session=self.session)
        self.backend.AssetVersionSize = SimpleNamespace(
            THUMB="thumb",
            MEDIUM="medium",
            ADJUSTED="adjusted",
            ORIGINAL="original",
        )
        asset = SimpleNamespace(
            versions={
                "thumb": SimpleNamespace(url="thumb-url"),
                "medium": SimpleNamespace(url="medium-url"),
                "adjusted": SimpleNamespace(url="adjusted-url"),
                "original": SimpleNamespace(url="original-url"),
            }
        )
        self.item = MediaItem(asset, "asset", "IMG_0001.HEIC", "", True)

    def test_thumbnail_prefers_medium_and_keeps_high_dpi_pixels(self) -> None:
        image = self.backend.fetch_thumbnail(self.item)
        self.assertEqual("medium-url", self.session.urls[0])
        self.assertEqual((448, 336), image.size)

    def test_preview_keeps_screen_sized_resolution(self) -> None:
        image = self.backend.fetch_preview(self.item)
        self.assertEqual("adjusted-url", self.session.urls[0])
        self.assertEqual((1200, 900), image.size)

    def test_thumbnail_quality_changes_resource_and_pixel_size(self) -> None:
        fast = self.backend.fetch_thumbnail(self.item, "fast")
        self.assertEqual("thumb-url", self.session.urls[0])
        self.assertEqual((224, 168), fast.size)
        self.session.urls.clear()
        high = self.backend.fetch_thumbnail(self.item, "high")
        self.assertEqual("adjusted-url", self.session.urls[0])
        self.assertEqual((896, 672), high.size)

    def test_preview_quality_can_use_standard_or_original(self) -> None:
        standard = self.backend.fetch_preview(self.item, "standard")
        self.assertEqual("medium-url", self.session.urls[0])
        self.assertEqual((1200, 900), standard.size)
        self.session.urls.clear()
        original = self.backend.fetch_preview(self.item, "original")
        self.assertEqual("original-url", self.session.urls[0])
        self.assertEqual((1200, 900), original.size)


if __name__ == "__main__":
    unittest.main()
