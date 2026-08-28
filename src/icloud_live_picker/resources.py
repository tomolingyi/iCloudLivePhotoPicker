from __future__ import annotations

import ctypes
import os
from pathlib import Path


ASSET_DIR = Path(__file__).resolve().parent / "assets"


def asset_path(name: str) -> Path:
    return ASSET_DIR / name


def configure_windows_app_id() -> None:
    """Give the packaged app a stable taskbar identity and icon grouping."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            "iCloudLivePhotoPicker.App"
        )
    except (AttributeError, OSError):
        pass
