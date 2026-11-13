from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from .constants import IMAGE_SUFFIXES
from .models import MediaItem, MediaPage


class ICloudBackend:
    """Adapter around icloudpd 1.32.3's pyicloud_ipd implementation."""

    def __init__(self) -> None:
        self.api: Any | None = None
        self.AssetVersionSize: Any | None = None
        self.LivePhotoVersionSize: Any | None = None

    def _load_api(self) -> None:
        try:
            from pyicloud_ipd import PyiCloudService
            from pyicloud_ipd.version_size import AssetVersionSize, LivePhotoVersionSize
        except Exception as exc:
            raise RuntimeError(
                "无法导入 pyicloud_ipd。请用项目自带的 run_windows.bat 安装依赖；"
                "它会安装 icloudpd 1.32.3 的纯 Python wheel。"
            ) from exc
        self.PyiCloudService = PyiCloudService
        self.AssetVersionSize = AssetVersionSize
        self.LivePhotoVersionSize = LivePhotoVersionSize

    def connect(self, domain: str, account: str, password: str, cookie_dir: Path) -> str:
        self._load_api()
        cookie_dir.mkdir(parents=True, exist_ok=True)
        provider: Callable[[], str | None] = lambda: password or None
        self.api = self.PyiCloudService(
            domain,
            account,
            provider,
            cookie_directory=str(cookie_dir),
            with_family=True,
        )
        try:
            if self.api.requires_2fa:
                try:
                    self.api.trigger_push_notification()
                except Exception:
                    pass
                return "2fa"
            if self.api.requires_2sa:
                return "2sa"
        except KeyError as exc:
            raise RuntimeError(
                "当前缓存的 iCloud 会话状态无效。请清理当前账号会话后重新登录。"
            ) from exc
        return "ok"

    def verify_2fa(self, code: str) -> bool:
        if self.api is None:
            raise RuntimeError("尚未建立 iCloud 会话")
        return bool(self.api.validate_2fa_code(code.strip()))

    def album_names(self) -> list[str]:
        if self.api is None:
            raise RuntimeError("尚未登录")
        names = list(self.api.photos.albums.keys())
        preferred = ["Live", "Favorites", "Screenshots", "Videos"]
        ordered = [name for name in preferred if name in names]
        ordered += sorted(name for name in names if name not in preferred)
        return ordered

    @staticmethod
    def _prepare_album(album: Any) -> int:
        """Reset native rank traversal: rank 0 is the newest asset.

        icloudpd implements --recent by taking the first N elements from the
        unmodified PhotoAlbum iterator (ASCENDING ranks, increasing offset).
        Rank direction is not chronological direction. Starting at count - 1
        and decrementing instead selects the oldest assets first.
        """
        total = len(album)
        album.offset = 0
        album.page_size = 100
        return total

    def _media_item(self, asset: Any) -> MediaItem | None:
        filename = str(getattr(asset, "filename", "") or f"{asset.id}.jpg")
        suffix = Path(filename).suffix.lower()
        item_type = str(getattr(asset, "item_type", "")).lower()
        if suffix not in IMAGE_SUFFIXES and "image" not in item_type:
            return None

        versions = asset.versions
        is_live = any(
            key in versions
            for key in (
                self.LivePhotoVersionSize.ORIGINAL,
                self.LivePhotoVersionSize.MEDIUM,
                self.LivePhotoVersionSize.THUMB,
            )
        )
        try:
            created = asset.created.strftime("%Y-%m-%d %H:%M")
        except Exception:
            created = ""
        return MediaItem(
            asset=asset,
            asset_id=str(asset.id),
            filename=filename,
            created_text=created,
            is_live=is_live,
        )

    def _album(self, album_name: str) -> Any:
        if self.api is None:
            raise RuntimeError("尚未登录")
        photos = self.api.photos
        if album_name == "全部照片":
            return photos.all
        albums = photos.albums
        if album_name not in albums:
            raise RuntimeError(f"找不到相簿：{album_name}")
        return albums[album_name]

    def load_items_page(
        self,
        album_name: str,
        *,
        start: int = 0,
        limit: int | None = 300,
        known_asset_ids: set[str] | None = None,
    ) -> MediaPage:
        """Load image assets newest-first, optionally continuing after ``start`` images.

        CloudKit is still queried in its native 100-record pages. ``start`` counts
        image assets rather than raw album records because an album can also
        contain standalone videos. When ``known_asset_ids`` is supplied, assets
        already displayed by the UI are ignored instead of relying on a numeric
        offset. That keeps continuation stable when iCloud inserts or exposes new
        records between requests. A ``None`` limit deliberately scans the rest of
        the album for the UI's explicit "load all" action.
        """
        if start < 0:
            raise ValueError("start must be non-negative")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive or None")

        album = self._album(album_name)

        total_assets = self._prepare_album(album)
        items: list[MediaItem] = []
        known_ids = known_asset_ids or set()
        seen_ids: set[str] = set()
        image_index = 0
        exhausted = True
        # Treat the count as informational only. Consume native pages until the
        # iterator ends or one more unseen image proves that a next page exists.
        for asset in album:
            asset_id = str(asset.id)
            if asset_id in seen_ids:
                continue
            seen_ids.add(asset_id)
            item = self._media_item(asset)
            if item is None:
                continue

            if image_index < start:
                image_index += 1
                continue
            image_index += 1
            if item.asset_id in known_ids:
                continue
            if limit is not None and len(items) >= limit:
                exhausted = False
                break
            items.append(item)

        total_assets = max(total_assets, len(seen_ids))
        return MediaPage(
            items=items,
            exhausted=exhausted,
            total_assets=total_assets,
        )

    def load_items(self, album_name: str, limit: int) -> list[MediaItem]:
        """Backward-compatible single-page loader used by integrations/tests."""
        return self.load_items_page(album_name, limit=limit).items

    def _pick_version(self, item: MediaItem, kind: str, size: str) -> Any:
        versions = item.asset.versions
        if kind == "photo":
            choices = {
                "original": [
                    self.AssetVersionSize.ORIGINAL,
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.MEDIUM,
                ],
                "adjusted": [
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.ORIGINAL,
                    self.AssetVersionSize.MEDIUM,
                ],
                "medium": [
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.ORIGINAL,
                ],
            }
        else:
            choices = {
                "original": [
                    self.LivePhotoVersionSize.ORIGINAL,
                    self.LivePhotoVersionSize.MEDIUM,
                    self.LivePhotoVersionSize.THUMB,
                ],
                "medium": [
                    self.LivePhotoVersionSize.MEDIUM,
                    self.LivePhotoVersionSize.ORIGINAL,
                    self.LivePhotoVersionSize.THUMB,
                ],
                "small": [
                    self.LivePhotoVersionSize.THUMB,
                    self.LivePhotoVersionSize.MEDIUM,
                    self.LivePhotoVersionSize.ORIGINAL,
                ],
            }
        for key in choices[size]:
            if key in versions:
                return versions[key]
        raise RuntimeError(f"{item.filename} 没有可用的 {kind} 资源")

    def fetch_thumbnail(self, item: MediaItem, quality: str = "balanced") -> Image.Image:
        if self.api is None:
            raise RuntimeError("尚未登录")
        versions = item.asset.versions
        quality_options = {
            "fast": (
                (224, 168),
                [
                    self.AssetVersionSize.THUMB,
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.ADJUSTED,
                ],
            ),
            "balanced": (
                (448, 336),
                [
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.THUMB,
                ],
            ),
            "high": (
                (896, 672),
                [
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.ORIGINAL,
                    self.AssetVersionSize.THUMB,
                ],
            ),
        }
        maximum, candidates = quality_options.get(quality, quality_options["balanced"])
        available = [versions[key] for key in candidates if key in versions]
        if not available:
            raise RuntimeError("无 JPEG 缩略图资源")

        errors: list[str] = []
        for version in available:
            for attempt in range(3):
                try:
                    response = self.api.session.get(version.url, stream=False, timeout=30)
                    response.raise_for_status()
                    image = Image.open(io.BytesIO(response.content))
                    image.load()
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    # The card is 194×142 logical pixels. The selected source
                    # size controls network/memory use at high Windows DPI.
                    image.thumbnail(maximum, Image.Resampling.LANCZOS)
                    return image
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    if attempt < 2:
                        time.sleep(0.35 * (attempt + 1))
        raise RuntimeError(errors[-1] if errors else "缩略图下载失败")

    def fetch_preview(self, item: MediaItem, quality: str = "high") -> Image.Image:
        """Fetch a screen-sized still for the filename-click preview dialog."""
        if self.api is None:
            raise RuntimeError("尚未登录")
        versions = item.asset.versions
        quality_options: dict[str, tuple[tuple[int, int] | None, list[Any]]] = {
            "standard": (
                (1280, 960),
                [
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.ORIGINAL,
                    self.AssetVersionSize.THUMB,
                ],
            ),
            "high": (
                (2048, 1536),
                [
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.ORIGINAL,
                    self.AssetVersionSize.THUMB,
                ],
            ),
            "original": (
                None,
                [
                    self.AssetVersionSize.ORIGINAL,
                    self.AssetVersionSize.ADJUSTED,
                    self.AssetVersionSize.MEDIUM,
                    self.AssetVersionSize.THUMB,
                ],
            ),
        }
        maximum, candidates = quality_options.get(quality, quality_options["high"])
        available = [versions[key] for key in candidates if key in versions]
        if not available:
            raise RuntimeError("没有可用于预览的照片资源")

        errors: list[str] = []
        for version in available:
            for attempt in range(2):
                try:
                    response = self.api.session.get(version.url, stream=False, timeout=60)
                    response.raise_for_status()
                    image = Image.open(io.BytesIO(response.content))
                    image.load()
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    if maximum is not None:
                        image.thumbnail(maximum, Image.Resampling.LANCZOS)
                    return image
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    if attempt == 0:
                        time.sleep(0.35)
        raise RuntimeError(errors[-1] if errors else "照片预览加载失败")

    def download_version(
        self,
        item: MediaItem,
        kind: str,
        size: str,
        target: Path,
    ) -> int:
        if self.api is None:
            raise RuntimeError("尚未登录")
        version = self._pick_version(item, kind, size)
        response = item.asset.download(self.api.session, version.url)
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".part")
        written = 0
        try:
            with temp.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
                        written += len(chunk)
            os.replace(temp, target)
            return written
        except Exception:
            try:
                temp.unlink()
            except OSError:
                pass
            raise
