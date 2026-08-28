from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OrientationRepairResult:
    changed: bool
    warning: str = ""


@dataclass(frozen=True)
class OrientationTransform:
    rotation_ccw: float
    horizontal_flip: bool = False
    vertical_flip: bool = False


ORIENTATION_BAKED_MARKER = b"iCloudPickerOrientationBaked"


def asset_exif_orientation(asset: Any) -> int | None:
    """Read the TIFF/EXIF-compatible orientation returned by iCloud CloudKit.

    CloudKit normally stores ``originalOrientation`` on the CPLMaster record
    and ``orientation`` on the paired CPLAsset record.  Older responses and
    test fixtures may expose either key on either record, so accept all four
    combinations while preferring the original master orientation used by the
    original Live Photo video.
    """
    sources = (
        (getattr(asset, "_master_record", None), "originalOrientation"),
        (getattr(asset, "_asset_record", None), "orientation"),
        (getattr(asset, "_master_record", None), "orientation"),
        (getattr(asset, "_asset_record", None), "originalOrientation"),
    )
    for record, field_name in sources:
        try:
            orientation = int(record["fields"][field_name]["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= orientation <= 8:
            return orientation
    return None


def exif_orientation_to_ccw_degrees(orientation: int) -> float | None:
    """Convert common non-mirrored EXIF orientations to FFmpeg display rotation."""
    return {
        1: 0.0,
        3: 180.0,
        6: -90.0,
        8: 90.0,
    }.get(orientation)


def exif_orientation_transform(orientation: int) -> OrientationTransform | None:
    """Map all eight EXIF values to rotation and post-rotation display flips."""
    return {
        1: OrientationTransform(0.0),
        2: OrientationTransform(0.0, horizontal_flip=True),
        3: OrientationTransform(180.0),
        4: OrientationTransform(0.0, vertical_flip=True),
        5: OrientationTransform(90.0, horizontal_flip=True),
        6: OrientationTransform(-90.0),
        7: OrientationTransform(-90.0, horizontal_flip=True),
        8: OrientationTransform(90.0),
    }.get(orientation)


def exif_orientation_filter(orientation: int) -> str | None:
    """Return a pixel transform that bakes EXIF orientation into decoded frames."""
    return {
        2: "hflip",
        3: "hflip,vflip",
        4: "vflip",
        5: "transpose=cclock,hflip",
        6: "transpose=clock",
        7: "transpose=clock,hflip",
        8: "transpose=cclock",
    }.get(orientation)


def has_baked_orientation_marker(path: Path) -> bool:
    """Detect files already transformed by this app without starting FFprobe."""
    overlap = len(ORIENTATION_BAKED_MARKER) - 1
    previous = b""
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                combined = previous + chunk
                if ORIENTATION_BAKED_MARKER in combined:
                    return True
                previous = combined[-overlap:] if overlap else b""
    except OSError:
        return False
    return False


def find_ffmpeg() -> str | None:
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    if configured and Path(configured).is_file():
        return configured
    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered
    common_windows = Path("C:/ffmpeg/bin/ffmpeg.exe")
    if common_windows.is_file():
        return str(common_windows)
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    return bundled if bundled and Path(bundled).is_file() else None


def repair_mov_orientation(
    path: Path,
    orientation: int | None,
    *,
    ffmpeg_executable: str | None = None,
) -> OrientationRepairResult:
    """Bake orientation into video pixels for consistent Windows playback.

    iCloud Live Photo MOV files normally already contain a valid QuickTime
    display matrix. Windows Explorer and some Windows players ignore mirrored
    matrices, however, so mirrored/rotated encoded frames can still appear in
    the wrong direction. Decode without autorotation, apply the EXIF transform,
    remove display-matrix side data, and re-encode only the video stream. Audio,
    Live Photo metadata streams, and global QuickTime metadata are copied. The
    source file is replaced only after a successful encode.
    """
    if orientation is None:
        return OrientationRepairResult(False, "iCloud 未返回照片方向，已保留原始 MOV")
    if orientation == 1 or has_baked_orientation_marker(path):
        return OrientationRepairResult(False)
    video_filter = exif_orientation_filter(orientation)
    if video_filter is None:
        return OrientationRepairResult(False, f"无法识别方向值 {orientation}，已保留原始 MOV")

    ffmpeg = ffmpeg_executable or find_ffmpeg()
    if not ffmpeg:
        return OrientationRepairResult(False, "未找到 FFmpeg，已保留原始 MOV 方向")

    temp = path.with_name(f"{path.stem}.orientation.tmp{path.suffix}")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-noautorotate",
        "-i",
        str(path),
        "-map",
        "0",
        "-map_metadata",
        "0",
        "-c",
        "copy",
        "-c:v:0",
        "libx265",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-tag:v:0",
        "hvc1",
        "-filter:v:0",
        f"{video_filter},sidedata=delete:type=DISPLAYMATRIX",
        "-metadata:s:v:0",
        "rotate=0",
        "-metadata",
        f"iCloudPickerOrientationBaked={orientation}",
        "-movflags",
        "+use_metadata_tags+faststart",
        str(temp),
    ]
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        if completed.returncode != 0 or not temp.is_file() or temp.stat().st_size == 0:
            detail = (completed.stderr or completed.stdout or "FFmpeg 返回未知错误").strip()
            return OrientationRepairResult(False, f"MOV 方向修复失败，已保留原文件：{detail}")
        os.replace(temp, path)
        return OrientationRepairResult(True)
    except (OSError, subprocess.SubprocessError) as exc:
        return OrientationRepairResult(False, f"MOV 方向修复失败，已保留原文件：{exc}")
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
