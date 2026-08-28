from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from icloud_live_picker.ui.qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtWidgets import QApplication

from icloud_live_picker.models import MediaItem
from icloud_live_picker.settings import SettingsStore
from icloud_live_picker.ui.qt_app import PickerWindow
from icloud_live_picker.ui.qt_dialogs import NoticeDialog, SessionClearDialog, VerificationCodeDialog
from icloud_live_picker.ui.qt_result import DownloadResultDialog
from icloud_live_picker.ui.qt_widgets import APP_STYLESHEET


ROOT = Path(__file__).resolve().parents[1]


def demo_thumbnail(index: int) -> Image.Image:
    palettes = [
        ("#3C8D86", "#D9EEE9"),
        ("#5578A5", "#DCE5F2"),
        ("#C27D5D", "#F2E3D9"),
        ("#7C6AA8", "#E7E1F1"),
    ]
    dark, light = palettes[index % len(palettes)]
    image = Image.new("RGB", (448, 336), light)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 214, 448, 336), fill=dark)
    draw.ellipse((48 + index * 8, 42, 202 + index * 8, 196), fill="#FFFFFF")
    draw.polygon(((130, 245), (235, 108), (350, 245)), fill="#FFFFFF")
    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture privacy-safe project screenshots.")
    parser.add_argument(
        "view",
        nargs="?",
        default="library",
        choices=("library", "account", "session", "verification", "notice", "result"),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLESHEET)
    with tempfile.TemporaryDirectory() as temp_dir:
        window = PickerWindow(settings_store=SettingsStore(Path(temp_dir) / "settings.json"))
        window.resize(1750, 1150)
        window.cookie_edit.setText("C:/Users/Example/.icloudpd-picker")
        window.backend.api = object()
        window.connection_badge.setText("iCloud 已连接")
        window.album_combo.setEnabled(True)
        window.load_btn.setEnabled(True)
        items = [
            MediaItem(
                object(),
                f"demo-{index}",
                f"IMG_{8400 - index * 7}.HEIC",
                f"2026-08-28 {10 - index // 2:02d}:{40 - (index % 2) * 20:02d}",
                index != 0,
            )
            for index in range(8)
        ]
        if args.view == "library":
            window._after_items(items)
            for index, item in enumerate(items):
                window.gallery.install_thumbnail(item.asset_id, demo_thumbnail(index))
            window._show_page("library")
        else:
            window._show_page("account")
        window.show()
        application.processEvents()

        target = window
        dialog = None
        if args.view == "session":
            dialog = SessionClearDialog(window, "C:/Users/Example/.icloudpd-picker")
        elif args.view == "verification":
            dialog = VerificationCodeDialog(window)
        elif args.view == "notice":
            dialog = NoticeDialog(window, title="操作提示", message="这是统一风格的信息提示。")
        elif args.view == "result":
            dialog = DownloadResultDialog(
                window,
                summary="完成：8 个下载，0 个跳过，0 个失败。",
                output=Path("C:/Pictures/iCloudPicker"),
                open_directory=lambda: None,
            )
        if dialog is not None:
            dialog.show()
            application.processEvents()
            target = dialog

        output = args.output or ROOT / "docs" / "images" / "application.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        if not target.grab().save(str(output)):
            raise RuntimeError(f"Unable to save {output}")
        if dialog is not None:
            dialog.close()
        window.close()


if __name__ == "__main__":
    main()
