from __future__ import annotations

import io
import itertools
import os
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from .constants import IMAGE_SUFFIXES
from .models import MediaItem


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
    def _prepare_descending(album: Any) -> int:
        """Configure CloudKit rank pagination for newest-first iteration."""
        total = len(album)
        if not getattr(album, "_picker_descending_patched", False):
            original_query = album._list_query_gen

            def desc_query(
                offset: int,
                list_type: str,
                query_filter: Any = None,
            ) -> dict[str, Any]:
                query = original_query(offset, list_type, query_filter)
                filters = query.get("query", {}).get("filterBy", [])
                for entry in filters:
                    if entry.get("fieldName") == "direction":
                        entry.setdefault("fieldValue", {})["value"] = "DESCENDING"
                        break
                return query

            def decrement_offset(value: int) -> None:
                album.offset -= value

            album._list_query_gen = desc_query
            album.increment_offset = decrement_offset
            album._picker_descending_patched = True

        album.offset = max(0, total - 1)
        return total

    def load_items(self, album_name: str, limit: int) -> list[MediaItem]:
        if self.api is None:
            raise RuntimeError("尚未登录")
        photos = self.api.photos
        if album_name == "全部照片":
            album = photos.all
        else:
            albums = photos.albums
            if album_name not in albums:
                raise RuntimeError(f"找不到相簿：{album_name}")
            album = albums[album_name]

        total_assets = self._prepare_descending(album)
        album.page_size = 100
        items: list[MediaItem] = []
        scan_cap = min(total_assets, max(limit * 4, limit + 100))
        for asset in itertools.islice(iter(album), scan_cap):
            filename = str(getattr(asset, "filename", "") or f"{asset.id}.jpg")
            suffix = Path(filename).suffix.lower()
            item_type = str(getattr(asset, "item_type", "")).lower()
            if suffix not in IMAGE_SUFFIXES and "image" not in item_type:
                continue

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
            items.append(
                MediaItem(
                    asset=asset,
                    asset_id=str(asset.id),
                    filename=filename,
                    created_text=created,
                    is_live=is_live,
                )
            )
            if len(items) >= limit:
                break
        return items

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
