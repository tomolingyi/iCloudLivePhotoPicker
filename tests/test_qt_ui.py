from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from icloud_live_picker.constants import LIVE_SIZE_LABELS, PHOTO_SIZE_LABELS, THUMBNAIL_QUALITY_LABELS
from icloud_live_picker.models import MediaItem, MediaPage
from icloud_live_picker.settings import SettingsStore
from icloud_live_picker.ui.qt_app import PickerWindow
from icloud_live_picker.ui.qt_dialogs import NoticeDialog, SessionClearDialog, VerificationCodeDialog
from icloud_live_picker.ui.qt_preview import ImagePreviewDialog
from icloud_live_picker.ui.qt_result import DownloadResultDialog
from icloud_live_picker.ui.qt_widgets import APP_STYLESHEET, CleanComboBox
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFrame, QPlainTextEdit, QPushButton


class QtUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setStyle("Fusion")
        cls.application.setStyleSheet(APP_STYLESHEET)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings_path = Path(self.temp_dir.name) / "settings.json"
        self.window = PickerWindow(settings_store=SettingsStore(settings_path))
        self.window.show()
        self.application.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.application.processEvents()
        self.temp_dir.cleanup()

    def test_every_selector_uses_clean_combo_box(self) -> None:
        combos = self.window.findChildren(CleanComboBox)
        self.assertEqual(7, len(combos))
        self.assertTrue(all(combo.view().frameShape() == QFrame.Shape.NoFrame for combo in combos))

    def test_download_quality_selectors_use_chinese_labels_and_save_internal_keys(self) -> None:
        self.assertEqual(
            list(PHOTO_SIZE_LABELS.values()),
            [self.window.photo_size_combo.itemText(index) for index in range(self.window.photo_size_combo.count())],
        )
        self.assertEqual(
            list(LIVE_SIZE_LABELS.values()),
            [self.window.live_size_combo.itemText(index) for index in range(self.window.live_size_combo.count())],
        )
        self.window.photo_size_combo.setCurrentText(PHOTO_SIZE_LABELS["adjusted"])
        self.window.live_size_combo.setCurrentText(LIVE_SIZE_LABELS["small"])
        self.window._sync_preferences_to_settings()
        self.assertEqual("adjusted", self.window.settings.photo_size)
        self.assertEqual("small", self.window.settings.live_size)

    def test_ui_has_no_idle_refresh_timer(self) -> None:
        self.assertFalse(self.window.thumbnail_flush_timer.isActive())
        self.assertFalse(self.window.gallery._auto_scroll_timer.isActive())

    def test_first_visible_row_always_schedules_thumbnail_requests(self) -> None:
        requested: list[str] = []
        self.window.gallery.on_need_thumbnail = lambda item: requested.append(item.asset_id)
        items = [
            MediaItem(object(), f"visible-{index}", f"IMG_{index}.HEIC", "", False)
            for index in range(20)
        ]
        self.window.gallery.set_items(
            items,
            pair_mode=True,
            thumbnail_cache={},
            thumbnail_errors=set(),
        )
        self.application.processEvents()
        self.assertTrue({item.asset_id for item in items[:5]}.issubset(requested))

    def test_new_account_ui_defaults_to_phone_mainland_mode(self) -> None:
        self.assertTrue(self.window.phone_login_toggle.isChecked())
        self.assertEqual(1, self.window.account_stack.currentIndex())
        self.assertEqual("+86", self.window.country_code_edit.text())
        self.assertEqual("cn", self.window.domain_combo.currentText())
        self.window.phone_login_toggle.setChecked(False)
        self.assertEqual(0, self.window.account_stack.currentIndex())
        self.assertEqual("Apple 账号邮箱", self.window.account_field_label.text())

    def test_loading_photos_uses_indeterminate_task_progress(self) -> None:
        self.window.backend.api = object()
        self.window.load_btn.setEnabled(True)
        with patch("icloud_live_picker.ui.qt_app.threading.Thread") as thread:
            self.window.load_assets()
        thread.assert_called_once()
        self.assertEqual((0, 0), (self.window.progress.minimum(), self.window.progress.maximum()))
        self.assertIn("正在读取", self.window.progress_text_label.text())
        self.window._after_items([])
        self.assertEqual((0, 1000), (self.window.progress.minimum(), self.window.progress.maximum()))
        self.assertEqual(1000, self.window.progress.value())

    def test_load_more_appends_and_preserves_existing_selection(self) -> None:
        self.window.backend.api = object()
        initial = [MediaItem(object(), "first", "IMG_1.HEIC", "", False)]
        self.window._after_items_page(
            MediaPage(initial, exhausted=False, total_assets=3),
            album="全部照片",
            append=False,
            requested_all=False,
        )
        initial[0].selected_photo = True
        added = [
            MediaItem(object(), "second", "IMG_2.HEIC", "", False),
            MediaItem(object(), "third", "IMG_3.HEIC", "", False),
        ]
        self.window._after_items_page(
            MediaPage(added, exhausted=True, total_assets=3),
            album="全部照片",
            append=True,
            requested_all=False,
        )

        self.assertEqual(["first", "second", "third"], [item.asset_id for item in self.window.items])
        self.assertTrue(self.window.items[0].selected_photo)
        self.assertFalse(self.window.load_more_btn.isEnabled())
        self.assertFalse(self.window.load_all_btn.isEnabled())

    def test_load_all_warning_is_visible_next_to_pagination_actions(self) -> None:
        self.assertEqual(
            "加载全部会加大列表、缩略图任务和内存压力，请谨慎使用。",
            self.window.load_all_hint.text(),
        )
        self.assertEqual("加载更多", self.window.load_more_btn.text())
        self.assertEqual("全部加载", self.window.load_all_btn.text())

    def test_first_page_shows_latest_five_before_load_more(self) -> None:
        from tests.test_pagination import CloudKitFixture

        cloud = CloudKitFixture(305)
        self.window.backend = cloud.backend()
        self.window.gallery.on_need_thumbnail = lambda item: None
        first = self.window.backend.load_items_page("全部照片", limit=300)
        self.window._after_items_page(first, album="全部照片", append=False, requested_all=False)
        self.assertEqual(cloud.ids[:5], [item.asset_id for item in self.window.gallery.items[:5]])
        self.window.items[0].select_pair(True)
        rest = self.window.backend.load_items_page(
            "全部照片", limit=300, known_asset_ids=set(self.window.item_by_id),
        )
        self.window._after_items_page(rest, album="全部照片", append=True, requested_all=False)
        self.assertEqual(cloud.ids, [item.asset_id for item in self.window.gallery.items])
        self.assertTrue(self.window.item_by_id[cloud.ids[0]].selected_photo)
        self.assertFalse(self.window.load_more_btn.isEnabled())

    def test_all_project_prompts_use_styled_dialog_surfaces(self) -> None:
        dialogs = [
            NoticeDialog(self.window, title="提示", message="测试"),
            SessionClearDialog(self.window, "C:/session"),
            VerificationCodeDialog(self.window),
        ]
        for dialog in dialogs:
            self.assertIsNotNone(dialog.findChild(QFrame, "surface"))
            dialog.close()

    def test_sidebar_icons_have_one_consistent_size(self) -> None:
        sizes = {button.iconSize() for button in self.window.nav_buttons.values()}
        self.assertEqual(1, len(sizes))
        self.assertEqual((20, 20), (next(iter(sizes)).width(), next(iter(sizes)).height()))

    def test_clicking_filename_requests_preview_without_selecting(self) -> None:
        item = MediaItem(object(), "preview-id", "IMG_PREVIEW.HEIC", "2026-08-28", True)
        requested: list[MediaItem] = []
        self.window.gallery.on_preview_requested = requested.append
        self.window.gallery.set_items(
            [item],
            pair_mode=True,
            thumbnail_cache={},
            thumbnail_errors={item.asset_id},
        )
        self.window._show_page("library")
        self.application.processEvents()
        rect = self.window.gallery._filename_rect(self.window.gallery._card_rect(0), item)
        point = QPoint(round(rect.center().x()), round(rect.center().y()))
        QTest.mouseClick(
            self.window.gallery.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            point,
        )
        self.assertEqual([item], requested)
        self.assertFalse(item.selected_photo)
        self.assertFalse(item.selected_live)

    def test_large_selection_updates_models_without_card_widgets(self) -> None:
        items = [
            MediaItem(
                asset=object(),
                asset_id=f"asset-{index}",
                filename=f"IMG_{index:04d}.HEIC",
                created_text="2026-08-28 12:00",
                is_live=index % 2 == 0,
            )
            for index in range(1200)
        ]
        self.window._after_items(items)
        selected_ids = {f"asset-{index}" for index in range(1000)}
        self.window._box_selected(selected_ids, False)
        self.assertEqual(1000, sum(item.selected_photo for item in items))
        self.assertEqual(500, sum(item.selected_live for item in items))
        self.assertLess(len(self.window.gallery._visible_index_range()), 100)

    def test_thumbnail_quality_change_invalidates_gallery_cache(self) -> None:
        item = MediaItem(object(), "quality-id", "IMG_QUALITY.HEIC", "2026-08-28", False)
        self.window.items = [item]
        self.window.filtered_items = [item]
        self.window.item_by_id = {item.asset_id: item}
        self.window.gallery.set_items(
            [item], pair_mode=True, thumbnail_cache={}, thumbnail_errors={item.asset_id}
        )
        self.window.gallery.install_thumbnail(item.asset_id, Image.new("RGB", (448, 336)))
        self.assertTrue(self.window.gallery.has_thumbnail(item.asset_id))
        self.window.thumbnail_quality_combo.setCurrentText(THUMBNAIL_QUALITY_LABELS["high"])
        self.application.processEvents()
        self.assertEqual("high", self.window.settings.thumbnail_quality)
        self.assertFalse(self.window.gallery.has_thumbnail(item.asset_id))

    def test_preview_arrow_keys_follow_filtered_gallery_order(self) -> None:
        items = [
            MediaItem(object(), f"preview-{index}", f"IMG_{index}.JPG", "2026-08-28", False)
            for index in range(3)
        ]
        self.window.items = items
        self.window.filtered_items = items
        self.window.item_by_id = {item.asset_id: item for item in items}
        self.window.backend.fetch_preview = lambda _item, _quality: Image.new("RGB", (640, 480))
        self.window._preview_item(items[1])
        self.application.processEvents()
        dialog = self.window.preview_dialog
        self.assertIsNotNone(dialog)
        assert dialog is not None
        QTest.keyClick(dialog, Qt.Key.Key_Right)
        self.application.processEvents()
        self.assertEqual(items[2].asset_id, self.window.preview_current_id)
        self.assertFalse(dialog.next_button.isEnabled())
        QTest.keyClick(dialog, Qt.Key.Key_Left)
        self.application.processEvents()
        self.assertEqual(items[1].asset_id, self.window.preview_current_id)

    def test_preview_arrow_icons_are_geometrically_centered(self) -> None:
        dialog = ImagePreviewDialog("IMG_TEST.JPG", self.window)
        for button in (dialog.previous_button, dialog.next_button):
            image = button.icon().pixmap(24, 24).toImage()
            points = [
                (x, y)
                for y in range(image.height())
                for x in range(image.width())
                if image.pixelColor(x, y).alpha() > 0
            ]
            self.assertTrue(points)
            xs, ys = zip(*points)
            self.assertAlmostEqual((min(xs) + max(xs)) / 2, 11.5, delta=1.0)
            self.assertAlmostEqual((min(ys) + max(ys)) / 2, 11.5, delta=1.0)
        dialog.close()

    def test_download_result_uses_project_styled_dialog(self) -> None:
        dialog = DownloadResultDialog(
            self.window,
            summary="完成：2 个下载。",
            output=Path(self.temp_dir.name),
            details="一个测试提示",
            open_directory=lambda: None,
        )
        self.assertIsNotNone(dialog.findChild(QFrame, "surface"))
        self.assertEqual(1, len(dialog.findChildren(QPlainTextEdit)))
        open_button = dialog.findChild(QPushButton, "openDirectoryButton")
        self.assertIsNotNone(open_button)
        self.assertEqual("soft", open_button.property("role"))
        self.assertEqual(Qt.CursorShape.PointingHandCursor, open_button.cursor().shape())
        self.assertIn('QPushButton[role="soft"]:hover', APP_STYLESHEET)
        self.assertIn('QPushButton[role="soft"]:pressed', APP_STYLESHEET)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
