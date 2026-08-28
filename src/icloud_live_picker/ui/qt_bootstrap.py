from __future__ import annotations

import ctypes
import os
from pathlib import Path


_SYSTEM_ICU_HANDLES: list[object] = []


def prepare_qt_runtime() -> None:
    """Keep Anaconda's ICU from shadowing the Windows ICU used by Qt 6.10+."""
    if os.name != "nt" or _SYSTEM_ICU_HANDLES:
        return
    system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
    system32 = system_root / "System32"
    for name in ("icu.dll", "icuuc.dll", "icuin.dll"):
        path = system32 / name
        if path.is_file():
            _SYSTEM_ICU_HANDLES.append(ctypes.WinDLL(str(path)))

