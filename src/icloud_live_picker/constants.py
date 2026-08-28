from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "iCloud Live Photo Picker"
APP_VERSION = "0.5.3"


def default_cookie_dir() -> Path:
    """Resolve the session directory for the user running this process."""
    return Path.home() / ".icloudpd-picker"


def default_output_dir() -> Path:
    """Resolve the download directory for the user running this process."""
    return Path.home() / "Pictures" / "iCloudPicker"


def default_settings_path() -> Path:
    """Resolve the settings path from the target machine at application runtime."""
    return (
        Path(os.environ.get("APPDATA", str(Path.home())))
        / "iCloudLivePhotoPicker"
        / "settings.json"
    )

IMAGE_SUFFIXES = {
    ".heic",
    ".heif",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".tif",
    ".tiff",
    ".dng",
    ".cr2",
    ".cr3",
    ".arw",
    ".nef",
    ".nrw",
    ".rw2",
}

SORT_NEWEST = "拍摄时间 · 最新优先"
SORT_OLDEST = "拍摄时间 · 最早优先"
SORT_NAME_ASC = "文件名 · A → Z"
SORT_NAME_DESC = "文件名 · Z → A"
SORT_LIVE_FIRST = "Live Photo · 优先显示"
SORT_OPTIONS = (
    SORT_NEWEST,
    SORT_OLDEST,
    SORT_NAME_ASC,
    SORT_NAME_DESC,
    SORT_LIVE_FIRST,
)

THUMBNAIL_QUALITY_LABELS = {
    "fast": "流畅 · 224 × 168",
    "balanced": "清晰 · 448 × 336（推荐）",
    "high": "超清 · 896 × 672",
}

PREVIEW_QUALITY_LABELS = {
    "standard": "标准 · 1280 × 960",
    "high": "高清 · 2048 × 1536（推荐）",
    "original": "原始分辨率",
}
