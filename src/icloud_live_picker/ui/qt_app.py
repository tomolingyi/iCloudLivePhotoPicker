from __future__ import annotations

import os
import re
import sys
import threading
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from PIL import Image
from .qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtCore import QObject, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..backend import ICloudBackend
from ..constants import (
    APP_BUILD,
    APP_NAME,
    APP_VERSION,
    LIVE_SIZE_LABELS,
    PHOTO_SIZE_LABELS,
    PREVIEW_QUALITY_LABELS,
    SORT_NEWEST,
    SORT_OPTIONS,
    THUMBNAIL_QUALITY_LABELS,
    default_cookie_dir,
)
from ..filenames import human_bytes, safe_filename, safe_session_stem
from ..models import MediaItem, MediaPage
from ..orientation import asset_exif_orientation, repair_mov_orientation
from ..resources import asset_path, configure_windows_app_id
from ..settings import SettingsStore
from ..sorting import sort_media_items
from .qt_gallery import GalleryView
from .qt_dialogs import NoticeDialog, SessionClearDialog, VerificationCodeDialog
from .qt_preview import ImagePreviewDialog
from .qt_result import DownloadResultDialog
from .qt_widgets import (
    APP_STYLESHEET,
    COLORS,
    CleanComboBox,
    ToggleSwitch,
    make_label,
    make_nav_icon,
    set_role,
)


class UiBridge(QObject):
    """Deliver worker results through Qt's native queued-signal mechanism."""

    invoke = pyqtSignal(object)


class PickerWindow(QMainWindow):
    def __init__(self, *, settings_store: SettingsStore | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} {APP_BUILD}")
        self.setMinimumSize(1080, 720)
        self.resize(1320, 900)

        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self.backend = ICloudBackend()
        self.items: list[MediaItem] = []
        self.filtered_items: list[MediaItem] = []
        self.item_by_id: dict[str, MediaItem] = {}
        self.thumbnail_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="thumb")
        self.preview_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preview")
        self.thumbnail_images: dict[str, Image.Image] = {}
        self.thumbnail_pending: set[str] = set()
        self.thumbnail_errors: dict[str, str] = {}
        self._deferred_thumbnails: dict[str, tuple[int, Image.Image]] = {}
        self._load_generation = 0
        self._loaded_album: str | None = None
        self._all_items_loaded = False
        self._busy = False
        self._auto_restoring = False
        self._active_page = "account"
        self.preview_dialog: ImagePreviewDialog | None = None
        self.preview_current_id: str | None = None
        self._preview_generation = 0
        self._preview_future: Any | None = None
        self.preview_cache: OrderedDict[tuple[str, str], tuple[bytes, int, int]] = OrderedDict()
        self._preview_cache_bytes = 0

        self.bridge = UiBridge(self)
        self.bridge.invoke.connect(self._dispatch_ui)
        self.thumbnail_flush_timer = QTimer(self)
        self.thumbnail_flush_timer.setSingleShot(True)
        self.thumbnail_flush_timer.timeout.connect(self._flush_deferred_thumbnails)

        self._build_ui()
        self._center_window()
        self._render_gallery()
        self._update_selection_text()

        if (
            self.settings.remember_account
            and self.settings.auto_restore_session
            and self.settings.last_login_ok
            and self.settings.account
        ):
            QTimer.singleShot(350, self._try_auto_restore_session)

    # ---------- Common UI helpers ----------

    def _center_window(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = min(self.width(), max(640, area.width() - 40))
        height = min(self.height(), max(520, area.height() - 40))
        self.resize(width, height)
        self.move(area.x() + (area.width() - width) // 2, area.y() + (area.height() - height) // 2)

    @staticmethod
    def _dispatch_ui(callback: Callable[[], None]) -> None:
        callback()

    def _post_ui(self, callback: Callable[[], None]) -> None:
        self.bridge.invoke.emit(callback)

    @staticmethod
    def _surface(parent: QWidget | None = None) -> QFrame:
        frame = QFrame(parent)
        frame.setObjectName("surface")
        return frame

    @staticmethod
    def _field_label(text: str) -> QLabel:
        return make_label(text, object_name="muted")

    @staticmethod
    def _button(text: str, *, role: str = "", minimum_width: int = 0) -> QPushButton:
        button = QPushButton(text)
        if role:
            set_role(button, role)
        if minimum_width:
            button.setMinimumWidth(minimum_width)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    @staticmethod
    def _combo(values: list[str], current: str = "") -> CleanComboBox:
        combo = CleanComboBox()
        combo.addItems(values)
        if current in values:
            combo.setCurrentText(current)
        return combo

    @staticmethod
    def _page_header(eyebrow: str, title: str, subtitle: str) -> tuple[QWidget, QLabel]:
        header = QWidget()
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(make_label(eyebrow, object_name="eyebrow"))
        title_label = make_label(title, object_name="pageTitle")
        layout.addWidget(title_label)
        layout.addWidget(make_label(subtitle, object_name="muted", word_wrap=True))
        return header, title_label

    @staticmethod
    def _set_layout_margins(layout: Any, margins: tuple[int, int, int, int], spacing: int) -> None:
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_topbar())

        self.page_stack = QStackedWidget()
        self.pages = {
            "account": self._build_account_page(),
            "library": self._build_library_page(),
            "settings": self._build_settings_page(),
        }
        for page in self.pages.values():
            self.page_stack.addWidget(page)
        main_layout.addWidget(self.page_stack, 1)
        root_layout.addWidget(main, 1)
        self._show_page("account")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        self._set_layout_margins(layout, (16, 22, 16, 20), 7)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(6, 0, 0, 20)
        brand_layout.setSpacing(11)
        logo = QLabel("☁")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(40, 40)
        logo.setStyleSheet(
            f"background:{COLORS['primary']};color:white;border-radius:13px;font:700 20px 'Segoe UI Symbol';"
        )
        brand_layout.addWidget(logo)
        name = QLabel("Live Picker")
        name.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.Bold))
        brand_layout.addWidget(name)
        brand_layout.addStretch()
        layout.addWidget(brand)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in (
            ("library", "媒体库"),
            ("account", "iCloud 账户"),
            ("settings", "选择与下载设置"),
        ):
            button = QPushButton(text)
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(make_nav_icon(key))
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda _checked=False, page=key: self._show_page(page))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch(1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{COLORS['border']};border:0;")
        layout.addWidget(divider)
        layout.addWidget(make_label("本地安全会话", object_name="sectionTitle"))
        layout.addWidget(make_label("可自动恢复 · 密码永不落盘", object_name="muted"))
        layout.addSpacing(5)
        layout.addWidget(make_label(f"v{APP_VERSION} {APP_BUILD}", object_name="muted"))
        return sidebar

    def _build_topbar(self) -> QWidget:
        topbar = QWidget()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(74)
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(36, 15, 30, 15)
        layout.setSpacing(12)

        self.topbar_title = make_label("iCloud 账户", object_name="sectionTitle")
        layout.addWidget(self.topbar_title)
        layout.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索照片、日期或文件名")
        self.search_edit.setFixedWidth(300)
        self.search_edit.textChanged.connect(self._search_changed)
        layout.addWidget(self.search_edit)
        self.connection_badge = make_label("尚未连接", object_name="badge")
        self.connection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_badge.setMinimumWidth(96)
        layout.addWidget(self.connection_badge)
        account_button = self._button("账户", role="primary", minimum_width=104)
        account_button.clicked.connect(lambda: self._show_page("account"))
        layout.addWidget(account_button)
        return topbar

    # ---------- Pages ----------

    def _build_account_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._set_layout_margins(layout, (40, 28, 40, 28), 24)
        header, _ = self._page_header(
            "安全连接",
            "连接你的 iCloud",
            "登录状态通过本地 iCloud 会话恢复；账号可记住，密码和验证码绝不保存。",
        )
        layout.addWidget(header)

        card = self._surface()
        grid = QGridLayout(card)
        self._set_layout_margins(grid, (24, 20, 24, 22), 8)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 1)
        grid.addWidget(make_label("iCloud 登录", object_name="sectionTitle"), 0, 0)
        hint = make_label("大陆账号使用 cn；程序也会根据 Apple 提示自动切换", object_name="muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(hint, 0, 1, 1, 3)

        self.phone_login_toggle = ToggleSwitch("手机号登录（关闭为邮箱）")
        self.phone_login_toggle.setChecked(self.settings.login_method == "phone")
        self.phone_login_toggle.toggled.connect(self._login_method_changed)
        grid.addWidget(self.phone_login_toggle, 1, 0, 1, 4)

        self.account_field_label = self._field_label("手机号")
        grid.addWidget(self.account_field_label, 2, 0)
        grid.addWidget(self._field_label("密码"), 2, 1)
        grid.addWidget(self._field_label("区域"), 2, 2)

        saved_account = self.settings.account if self.settings.remember_account else ""
        self.email_edit = QLineEdit(saved_account if self.settings.login_method == "email" else "")
        self.email_edit.setPlaceholderText("name@example.com")
        self.country_code_edit = QLineEdit(self.settings.country_code)
        self.country_code_edit.setFixedWidth(78)
        self.country_code_edit.setPlaceholderText("+86")
        phone_number = saved_account
        if self.settings.login_method == "phone" and saved_account.startswith(self.settings.country_code):
            phone_number = saved_account[len(self.settings.country_code) :]
        elif self.settings.login_method != "phone":
            phone_number = ""
        self.phone_edit = QLineEdit(phone_number)
        self.phone_edit.setPlaceholderText("手机号")
        phone_widget = QWidget()
        phone_layout = QHBoxLayout(phone_widget)
        phone_layout.setContentsMargins(0, 0, 0, 0)
        phone_layout.setSpacing(8)
        phone_layout.addWidget(self.country_code_edit)
        phone_layout.addWidget(self.phone_edit, 1)
        self.account_stack = QStackedWidget()
        self.account_stack.addWidget(self.email_edit)
        self.account_stack.addWidget(phone_widget)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.domain_combo = self._combo(["com", "cn"], self.settings.domain)
        grid.addWidget(self.account_stack, 3, 0)
        grid.addWidget(self.password_edit, 3, 1)
        grid.addWidget(self.domain_combo, 3, 2)
        self.connect_btn = self._button("连接 iCloud  →", role="primary", minimum_width=150)
        self.connect_btn.clicked.connect(lambda: self.connect_icloud(False))
        grid.addWidget(self.connect_btn, 3, 3)

        switch_row = QWidget()
        switches = QHBoxLayout(switch_row)
        switches.setContentsMargins(0, 4, 0, 0)
        switches.setSpacing(18)
        self.remember_account_toggle = ToggleSwitch("记住账号（不保存密码）")
        self.remember_account_toggle.setChecked(self.settings.remember_account)
        self.remember_account_toggle.toggled.connect(self._remember_account_toggled)
        switches.addWidget(self.remember_account_toggle)
        self.show_password_toggle = ToggleSwitch("显示密码")
        self.show_password_toggle.toggled.connect(self._toggle_password_visibility)
        switches.addWidget(self.show_password_toggle)
        switches.addStretch(1)
        clear_button = self._button("清理会话")
        clear_button.clicked.connect(self.clear_session)
        switches.addWidget(clear_button)
        forget_button = self._button("忘记账号")
        forget_button.clicked.connect(self.forget_saved_account)
        switches.addWidget(forget_button)
        grid.addWidget(switch_row, 4, 0, 1, 4)

        grid.addWidget(self._field_label("会话目录"), 5, 0, 1, 4)
        self.cookie_edit = QLineEdit(self.settings.cookie_dir)
        grid.addWidget(self.cookie_edit, 6, 0, 1, 3)
        cookie_button = self._button("浏览目录", role="soft", minimum_width=120)
        cookie_button.clicked.connect(self.choose_cookie_dir)
        grid.addWidget(cookie_button, 6, 3)
        self.login_status_label = make_label(
            "准备就绪。已有安全会话可自动恢复；密码不会保存到磁盘。",
            object_name="badge",
            word_wrap=True,
        )
        self.login_status_label.setMinimumHeight(42)
        grid.addWidget(self.login_status_label, 7, 0, 1, 4)
        self._login_method_changed(self.phone_login_toggle.isChecked(), persist=False)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._set_layout_margins(layout, (40, 24, 40, 24), 12)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(make_label("你的媒体库", object_name="eyebrow"))
        self.library_title_label = make_label("全部照片", object_name="pageTitle")
        text_layout.addWidget(self.library_title_label)
        text_layout.addWidget(
            make_label("单击卡片直接选择；按住鼠标拖出选择框可以一次选择多张照片。", object_name="muted")
        )
        header_layout.addWidget(text, 1)
        settings_button = self._button("下载设置")
        settings_button.clicked.connect(lambda: self._show_page("settings"))
        header_layout.addWidget(settings_button, 0, Qt.AlignmentFlag.AlignBottom)
        open_button = self._button("打开下载目录")
        open_button.clicked.connect(self.open_output_directory)
        header_layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignBottom)
        self.download_btn = self._button("下载已选  →", role="primary", minimum_width=136)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self.start_download)
        header_layout.addWidget(self.download_btn, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(header)

        toolbar = self._surface()
        toolbar_grid = QGridLayout(toolbar)
        self._set_layout_margins(toolbar_grid, (16, 12, 16, 13), 7)
        toolbar_grid.setColumnStretch(0, 3)
        toolbar_grid.setColumnStretch(2, 2)
        toolbar_grid.addWidget(self._field_label("相簿"), 0, 0)
        toolbar_grid.addWidget(self._field_label("每次数量"), 0, 1)
        toolbar_grid.addWidget(self._field_label("排序方式"), 0, 2)
        self.album_combo = self._combo(["全部照片"], "全部照片")
        self.album_combo.setEnabled(False)
        toolbar_grid.addWidget(self.album_combo, 1, 0)
        self.limit_edit = QLineEdit("300")
        self.limit_edit.setFixedWidth(94)
        toolbar_grid.addWidget(self.limit_edit, 1, 1)
        self.sort_combo = self._combo(list(SORT_OPTIONS), self.settings.sort_mode)
        self.sort_combo.currentTextChanged.connect(self._sort_changed)
        toolbar_grid.addWidget(self.sort_combo, 1, 2)
        self.load_btn = self._button("加载 iCloud 照片", role="primary", minimum_width=158)
        self.load_btn.setEnabled(False)
        self.load_btn.clicked.connect(self.load_assets)
        toolbar_grid.addWidget(self.load_btn, 1, 3)

        continuation_widget = QWidget()
        continuation = QHBoxLayout(continuation_widget)
        continuation.setContentsMargins(0, 2, 0, 0)
        continuation.setSpacing(8)
        self.load_more_btn = self._button("加载更多", role="soft", minimum_width=112)
        self.load_more_btn.setEnabled(False)
        self.load_more_btn.clicked.connect(self.load_more_assets)
        continuation.addWidget(self.load_more_btn)
        self.load_all_btn = self._button("全部加载", minimum_width=112)
        self.load_all_btn.setEnabled(False)
        self.load_all_btn.clicked.connect(self.load_all_assets)
        continuation.addWidget(self.load_all_btn)
        self.load_all_hint = make_label(
            "加载全部会加大列表、缩略图任务和内存压力，请谨慎使用。",
            object_name="muted",
            word_wrap=True,
        )
        self.load_all_hint.setFont(QFont("Microsoft YaHei UI", 9))
        continuation.addWidget(self.load_all_hint, 1)
        toolbar_grid.addWidget(continuation_widget, 2, 0, 1, 4)

        actions_widget = QWidget()
        actions = QHBoxLayout(actions_widget)
        actions.setContentsMargins(0, 3, 0, 0)
        actions.setSpacing(7)
        self.live_only_toggle = ToggleSwitch("只看 Live Photo")
        self.live_only_toggle.toggled.connect(self._live_filter_changed)
        actions.addWidget(self.live_only_toggle)
        select_visible = self._button("全选可见", role="soft")
        select_visible.clicked.connect(lambda: self.set_visible_selection(True))
        actions.addWidget(select_visible)
        clear_visible = self._button("取消可见选择")
        clear_visible.clicked.connect(lambda: self.set_visible_selection(False))
        actions.addWidget(clear_visible)
        live_select = self._button("只选 Live")
        live_select.clicked.connect(self.select_live_only)
        actions.addWidget(live_select)
        retry = self._button("重试缩略图")
        retry.clicked.connect(self.retry_failed_thumbnails)
        actions.addWidget(retry)
        actions.addStretch(1)
        self.selection_badge = make_label("尚未加载", object_name="badge")
        actions.addWidget(self.selection_badge)
        toolbar_grid.addWidget(actions_widget, 3, 0, 1, 4)
        self.album_combo.currentTextChanged.connect(self._album_selection_changed)
        layout.addWidget(toolbar)

        progress_surface = self._surface()
        progress_layout = QGridLayout(progress_surface)
        self._set_layout_margins(progress_layout, (16, 10, 16, 11), 5)
        progress_layout.addWidget(make_label("任务进度", object_name="sectionTitle"), 0, 0)
        self.progress_text_label = make_label("等待选择照片", object_name="muted")
        self.progress_text_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progress_layout.addWidget(self.progress_text_label, 0, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.progress, 1, 0, 1, 2)
        layout.addWidget(progress_surface)

        gallery_surface = self._surface()
        gallery_layout = QVBoxLayout(gallery_surface)
        self._set_layout_margins(gallery_layout, (10, 10, 10, 10), 7)
        gallery_header = QWidget()
        gallery_header_layout = QHBoxLayout(gallery_header)
        gallery_header_layout.setContentsMargins(4, 0, 4, 0)
        gallery_header_layout.addWidget(make_label("照片库", object_name="sectionTitle"))
        gallery_header_layout.addStretch(1)
        gallery_header_layout.addWidget(make_label("拖框选择 · Ctrl + 拖框可追加 · 单击卡片切换", object_name="muted"))
        gallery_layout.addWidget(gallery_header)
        self.gallery = GalleryView(
            gallery_surface,
            on_card_clicked=self._card_clicked,
            on_box_selected=self._box_selected,
            on_selection_changed=self._manual_selection_changed,
            on_need_thumbnail=self._request_thumbnail,
            on_preview_requested=self._preview_item,
        )
        gallery_layout.addWidget(self.gallery, 1)
        layout.addWidget(gallery_surface, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        self._set_layout_margins(layout, (40, 28, 40, 28), 12)
        header, _ = self._page_header(
            "偏好设置",
            "选择与下载",
            "控制照片选择方式、图片清晰度、登录恢复以及 Live Photo 视频方向修复。",
        )
        layout.addWidget(header)

        experience = self._surface()
        experience_layout = QVBoxLayout(experience)
        self._set_layout_margins(experience_layout, (22, 19, 22, 20), 10)
        experience_layout.addWidget(make_label("使用体验", object_name="sectionTitle"))
        experience_layout.addWidget(
            make_label(
                "默认联动时，单击或框选 Live Photo 会直接选择照片和配套 MOV。关闭后卡片显示两个独立选项。",
                object_name="muted",
                word_wrap=True,
            )
        )
        toggles_widget = QWidget()
        toggles = QHBoxLayout(toggles_widget)
        toggles.setContentsMargins(0, 2, 0, 0)
        toggles.setSpacing(28)
        self.auto_pair_toggle = ToggleSwitch("照片 + MOV 默认成组选中")
        self.auto_pair_toggle.setChecked(self.settings.auto_pair_selection)
        self.auto_pair_toggle.toggled.connect(self._selection_mode_changed)
        toggles.addWidget(self.auto_pair_toggle)
        self.auto_restore_toggle = ToggleSwitch("启动时自动恢复登录状态")
        self.auto_restore_toggle.setChecked(self.settings.auto_restore_session)
        self.auto_restore_toggle.toggled.connect(self._preferences_changed)
        toggles.addWidget(self.auto_restore_toggle)
        self.fix_orientation_toggle = ToggleSwitch("Windows 兼容 MOV 方向")
        self.fix_orientation_toggle.setChecked(self.settings.fix_mov_orientation)
        self.fix_orientation_toggle.toggled.connect(self._preferences_changed)
        toggles.addWidget(self.fix_orientation_toggle)
        toggles.addStretch(1)
        experience_layout.addWidget(toggles_widget)
        experience_layout.addWidget(
            make_label(
                "方向兼容会在必要时把旋转或镜像固化到视频画面，避免 Windows 忽略 QuickTime 镜像矩阵；"
                "仅视频流采用高质量 HEVC 编码，音频和 Live Photo 元数据保持复制。",
                object_name="muted",
                word_wrap=True,
            )
        )

        quality_widget = QWidget()
        quality_grid = QGridLayout(quality_widget)
        quality_grid.setContentsMargins(0, 8, 0, 0)
        quality_grid.setHorizontalSpacing(12)
        quality_grid.setVerticalSpacing(7)
        quality_grid.setColumnStretch(0, 1)
        quality_grid.setColumnStretch(1, 1)
        quality_grid.addWidget(self._field_label("缩略图清晰度"), 0, 0)
        quality_grid.addWidget(self._field_label("预览图清晰度"), 0, 1)
        self.thumbnail_quality_combo = self._combo(
            list(THUMBNAIL_QUALITY_LABELS.values()),
            THUMBNAIL_QUALITY_LABELS[self.settings.thumbnail_quality],
        )
        self.thumbnail_quality_combo.currentTextChanged.connect(self._thumbnail_quality_changed)
        quality_grid.addWidget(self.thumbnail_quality_combo, 1, 0)
        self.preview_quality_combo = self._combo(
            list(PREVIEW_QUALITY_LABELS.values()),
            PREVIEW_QUALITY_LABELS[self.settings.preview_quality],
        )
        self.preview_quality_combo.currentTextChanged.connect(self._preview_quality_changed)
        quality_grid.addWidget(self.preview_quality_combo, 1, 1)
        quality_grid.addWidget(
            make_label(
                "更高清的档位会增加网络流量和内存占用；切换缩略图档位后，当前图库会自动重新加载。",
                object_name="muted",
                word_wrap=True,
            ),
            2,
            0,
            1,
            2,
        )
        experience_layout.addWidget(quality_widget)
        layout.addWidget(experience)

        download = self._surface()
        grid = QGridLayout(download)
        self._set_layout_margins(grid, (22, 19, 22, 20), 8)
        grid.setColumnStretch(0, 3)
        grid.addWidget(make_label("下载设置", object_name="sectionTitle"), 0, 0)
        self.settings_selection_badge = make_label("尚未加载", object_name="badge")
        grid.addWidget(self.settings_selection_badge, 0, 4)
        grid.addWidget(self._field_label("保存位置"), 1, 0)
        grid.addWidget(self._field_label("照片质量"), 1, 2)
        grid.addWidget(self._field_label("实况视频质量"), 1, 3)
        self.output_edit = QLineEdit(self.settings.output_dir)
        self.output_edit.editingFinished.connect(self._preferences_changed)
        grid.addWidget(self.output_edit, 2, 0)
        browse = self._button("浏览", role="soft", minimum_width=86)
        browse.clicked.connect(self.choose_output_dir)
        grid.addWidget(browse, 2, 1)
        self.photo_size_combo = self._combo(
            list(PHOTO_SIZE_LABELS.values()),
            PHOTO_SIZE_LABELS[self.settings.photo_size],
        )
        self.photo_size_combo.currentTextChanged.connect(self._preferences_changed)
        grid.addWidget(self.photo_size_combo, 2, 2)
        self.live_size_combo = self._combo(
            list(LIVE_SIZE_LABELS.values()),
            LIVE_SIZE_LABELS[self.settings.live_size],
        )
        self.live_size_combo.currentTextChanged.connect(self._preferences_changed)
        grid.addWidget(self.live_size_combo, 2, 3)
        option_widget = QWidget()
        option_layout = QHBoxLayout(option_widget)
        option_layout.setContentsMargins(0, 4, 0, 0)
        option_layout.setSpacing(24)
        self.overwrite_toggle = ToggleSwitch("覆盖已有文件")
        self.overwrite_toggle.setChecked(self.settings.overwrite)
        self.overwrite_toggle.toggled.connect(self._preferences_changed)
        option_layout.addWidget(self.overwrite_toggle)
        self.live_suffix_toggle = ToggleSwitch("实况视频文件名加 _LIVE")
        self.live_suffix_toggle.setChecked(self.settings.live_suffix)
        self.live_suffix_toggle.toggled.connect(self._preferences_changed)
        option_layout.addWidget(self.live_suffix_toggle)
        option_layout.addStretch(1)
        grid.addWidget(option_widget, 3, 0, 1, 5)
        layout.addWidget(download)
        layout.addStretch(1)
        scroll.setWidget(body)
        page_layout.addWidget(scroll)
        return page

    # ---------- Navigation, settings and local folders ----------

    def _show_page(self, name: str) -> None:
        page = self.pages.get(name)
        if page is None:
            return
        self.page_stack.setCurrentWidget(page)
        self.nav_buttons[name].setChecked(True)
        title = {
            "account": "iCloud 账户",
            "library": "实况照片" if self.live_only_toggle.isChecked() else "全部照片",
            "settings": "选择与下载设置",
        }[name]
        self.topbar_title.setText(title)
        self.search_edit.setVisible(name == "library")
        self._active_page = name

    def _show_library(self, live_only: bool | None = None) -> None:
        if live_only is not None:
            self.live_only_toggle.setChecked(live_only)
        self._sync_library_heading()
        self.apply_filter()
        self._show_page("library")

    def _sync_library_heading(self) -> None:
        title = "实况照片" if self.live_only_toggle.isChecked() else "全部照片"
        self.library_title_label.setText(title)
        if self._active_page == "library":
            self.topbar_title.setText(title)

    def _sync_preferences_to_settings(self) -> None:
        sort_mode = self.sort_combo.currentText()
        self.settings.sort_mode = sort_mode if sort_mode in SORT_OPTIONS else SORT_NEWEST
        self.settings.auto_pair_selection = self.auto_pair_toggle.isChecked()
        self.settings.auto_restore_session = self.auto_restore_toggle.isChecked()
        self.settings.fix_mov_orientation = self.fix_orientation_toggle.isChecked()
        self.settings.thumbnail_quality = self._key_for_quality_label(
            THUMBNAIL_QUALITY_LABELS,
            self.thumbnail_quality_combo.currentText(),
            "balanced",
        )
        self.settings.preview_quality = self._key_for_quality_label(
            PREVIEW_QUALITY_LABELS,
            self.preview_quality_combo.currentText(),
            "high",
        )
        self.settings.output_dir = self.output_edit.text().strip()
        self.settings.photo_size = self._key_for_quality_label(
            PHOTO_SIZE_LABELS,
            self.photo_size_combo.currentText(),
            "original",
        )
        self.settings.live_size = self._key_for_quality_label(
            LIVE_SIZE_LABELS,
            self.live_size_combo.currentText(),
            "original",
        )
        self.settings.overwrite = self.overwrite_toggle.isChecked()
        self.settings.live_suffix = self.live_suffix_toggle.isChecked()

    def _save_settings(self, *, silent: bool = False) -> bool:
        try:
            self.settings_store.save(self.settings)
            return True
        except OSError as exc:
            print(f"Could not save settings: {exc}", file=sys.stderr)
            if not silent:
                NoticeDialog.show_message(self, title="无法保存设置", message=str(exc), kind="error")
            return False

    def _preferences_changed(self, *_args: Any) -> None:
        self._sync_preferences_to_settings()
        self._save_settings(silent=True)

    @staticmethod
    def _key_for_quality_label(options: dict[str, str], label: str, default: str) -> str:
        return next((key for key, value in options.items() if value == label), default)

    def _thumbnail_quality_changed(self, *_args: Any) -> None:
        previous = self.settings.thumbnail_quality
        self._sync_preferences_to_settings()
        self._save_settings(silent=True)
        if self.settings.thumbnail_quality == previous:
            return
        self._load_generation += 1
        self.thumbnail_images.clear()
        self.thumbnail_pending.clear()
        self.thumbnail_errors.clear()
        self._deferred_thumbnails.clear()
        self.gallery.clear_thumbnails()
        self.gallery.viewport().update()

    def _preview_quality_changed(self, *_args: Any) -> None:
        previous = self.settings.preview_quality
        self._sync_preferences_to_settings()
        self._save_settings(silent=True)
        if self.settings.preview_quality == previous:
            return
        self.preview_cache.clear()
        self._preview_cache_bytes = 0
        dialog = self.preview_dialog
        item = self.item_by_id.get(self.preview_current_id or "")
        if dialog is not None and dialog.isVisible() and item is not None:
            self._load_preview_item(item, dialog)

    def _selection_mode_changed(self, *_args: Any) -> None:
        if self.auto_pair_toggle.isChecked():
            for item in self.items:
                if item.selected_photo or item.selected_live:
                    item.select_pair(True)
        self._preferences_changed()
        self.gallery.set_pair_mode(self.auto_pair_toggle.isChecked())
        self.apply_filter()
        self._update_selection_text()

    def _sort_changed(self, *_args: Any) -> None:
        self._preferences_changed()
        self.apply_filter()

    def _live_filter_changed(self, *_args: Any) -> None:
        self._sync_library_heading()
        self.apply_filter()

    def _search_changed(self, *_args: Any) -> None:
        self.apply_filter()

    def _toggle_password_visibility(self, visible: bool) -> None:
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def _login_method_changed(self, phone_login: bool, *, persist: bool = True) -> None:
        self.account_stack.setCurrentIndex(1 if phone_login else 0)
        self.account_field_label.setText("手机号" if phone_login else "Apple 账号邮箱")
        if persist:
            self.settings.login_method = "phone" if phone_login else "email"
            self.settings.country_code = self._normalized_country_code()
            self._save_settings(silent=True)

    def _normalized_country_code(self) -> str:
        digits = "".join(character for character in self.country_code_edit.text() if character.isdigit())
        return f"+{digits}" if digits else "+86"

    def _current_account(self) -> str:
        if not self.phone_login_toggle.isChecked():
            return self.email_edit.text().strip()
        code = self._normalized_country_code()
        number = "".join(character for character in self.phone_edit.text() if character.isdigit())
        return f"{code}{number}" if number else ""

    def choose_cookie_dir(self) -> None:
        initial = self.cookie_edit.text().strip() or str(Path.home())
        value = QFileDialog.getExistingDirectory(self, "选择 iCloud 会话目录", initial)
        if value:
            self.cookie_edit.setText(value)

    def choose_output_dir(self) -> None:
        initial = self.output_edit.text().strip() or str(Path.home())
        value = QFileDialog.getExistingDirectory(self, "选择下载目录", initial)
        if value:
            self.output_edit.setText(value)
            self._preferences_changed()

    def open_output_directory(self) -> None:
        value = self.output_edit.text().strip()
        if not value:
            NoticeDialog.show_message(self, title="尚未选择保存位置", message="请先在下载设置中选择保存位置。", kind="warning")
            return
        try:
            directory = Path(value).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                raise OSError("当前系统不支持 Windows 文件夹打开方式")
            os.startfile(directory)  # type: ignore[attr-defined]
        except OSError as exc:
            NoticeDialog.show_message(self, title="无法打开下载目录", message=str(exc), kind="error")

    def _remember_account_toggled(self, enabled: bool) -> None:
        if enabled:
            self.login_status_label.setText("连接成功后会记住账号并自动恢复安全会话；不会保存密码。")
            return
        self.settings.remember_account = False
        self.settings.account = ""
        self.settings.last_login_ok = False
        self._save_settings(silent=True)
        self.login_status_label.setText("已关闭账号与登录状态保存。")

    def forget_saved_account(self) -> None:
        self.remember_account_toggle.setChecked(False)
        self.settings.remember_account = False
        self.settings.account = ""
        self.settings.login_method = "phone"
        self.settings.country_code = "+86"
        self.settings.domain = "cn"
        cookie_dir = default_cookie_dir()
        self.settings.cookie_dir = str(cookie_dir)
        self.settings.last_login_ok = False
        if not self._save_settings():
            return
        self.email_edit.clear()
        self.phone_edit.clear()
        self.country_code_edit.setText("+86")
        self.password_edit.clear()
        self.phone_login_toggle.setChecked(True)
        self.domain_combo.setCurrentText("cn")
        self.cookie_edit.setText(str(cookie_dir))
        self.login_status_label.setText("已忘记保存的账号。iCloud 会话文件未删除。")

    def clear_session(self) -> None:
        account = self._current_account()
        if not account:
            NoticeDialog.show_message(self, title="缺少 Apple 账号", message="请先填写 Apple 账号。", kind="warning")
            return
        cookie_dir = Path(self.cookie_edit.text()).expanduser()
        if SessionClearDialog(self, str(cookie_dir)).exec() != QDialog.DialogCode.Accepted:
            return
        stem = safe_session_stem(account)
        removed = 0
        for path in (cookie_dir / stem, cookie_dir / f"{stem}.session"):
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                pass
            except OSError as exc:
                NoticeDialog.show_message(self, title="会话删除失败", message=f"{path}\n{exc}", kind="error")
                return
        self.backend.api = None
        self._loaded_album = None
        self._all_items_loaded = False
        self.settings.last_login_ok = False
        self._save_settings(silent=True)
        self.connection_badge.setText("尚未连接")
        self.login_status_label.setText(f"已删除 {removed} 个当前账号会话文件。")
        self.load_btn.setEnabled(False)
        self._update_load_buttons()

    # ---------- Login and loading ----------

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.connect_btn.setEnabled(not busy)
        self.load_btn.setEnabled(self.backend.api is not None and not busy)
        self._update_load_buttons()
        self._update_download_button()
        if message:
            self.login_status_label.setText(message)

    def _album_selection_changed(self, _album: str) -> None:
        self._update_load_buttons()

    def _update_load_buttons(self) -> None:
        if not hasattr(self, "load_more_btn"):
            return
        connected = self.backend.api is not None
        album = self.album_combo.currentText() or "全部照片"
        same_album = bool(self.items) and self._loaded_album == album
        self.load_more_btn.setEnabled(
            connected and not self._busy and same_album and not self._all_items_loaded
        )
        self.load_all_btn.setEnabled(
            connected and not self._busy and not (same_album and self._all_items_loaded)
        )

    def _try_auto_restore_session(self) -> None:
        if not (
            self.settings.remember_account
            and self.settings.auto_restore_session
            and self.settings.last_login_ok
            and self.settings.account
        ):
            return
        account = self.settings.account
        cookie_dir = Path(self.settings.cookie_dir).expanduser()

        def inspect_session() -> None:
            stem = safe_session_stem(account)
            exists = (cookie_dir / stem).exists() or (cookie_dir / f"{stem}.session").exists()
            self._post_ui(self._begin_auto_restore_session if exists else self._auto_restore_session_missing)

        threading.Thread(target=inspect_session, daemon=True, name="icloud-session-check").start()

    def _begin_auto_restore_session(self) -> None:
        self.login_status_label.setText("正在自动恢复上次 iCloud 登录状态…")
        self.connect_icloud(True)

    def _auto_restore_session_missing(self) -> None:
        self.login_status_label.setText("已保存账号，但本地 iCloud 会话不存在；请输入密码重新连接。")

    def connect_icloud(self, auto_restore: bool = False) -> None:
        if self._busy:
            return
        account = self._current_account()
        if not account:
            if not auto_restore:
                NoticeDialog.show_message(self, title="缺少 Apple 账号", message="请输入 Apple 账号后再连接。", kind="warning")
            return
        password = "" if auto_restore else self.password_edit.text()
        domain = self.domain_combo.currentText().strip() or "cn"
        cookie_dir = Path(self.cookie_edit.text()).expanduser()
        self._auto_restoring = auto_restore
        self._set_busy(True, "正在恢复 iCloud 登录状态…" if auto_restore else "正在连接 iCloud…")

        def work() -> None:
            try:
                state = self.backend.connect(domain, account, password, cookie_dir)
                self._post_ui(lambda result=state: self._after_connect(result))
                return
            except Exception as exc:
                message = str(exc)
                retry_domain: str | None = None
                if "iCloud.com.cn" in message and domain != "cn":
                    retry_domain = "cn"
                elif "iCloud.com" in message and "iCloud.com.cn" not in message and domain != "com":
                    retry_domain = "com"
                if retry_domain is not None:
                    try:
                        self._post_ui(lambda selected=retry_domain: self.domain_combo.setCurrentText(selected))
                        state = self.backend.connect(retry_domain, account, password, cookie_dir)
                        self._post_ui(lambda result=state: self._after_connect(result))
                        return
                    except Exception as retry_exc:
                        exc = retry_exc
                details = traceback.format_exc()
                if auto_restore:
                    self._post_ui(lambda error=exc, detail=details: self._auto_restore_failed(error, detail))
                else:
                    self._post_ui(lambda error=exc, detail=details: self._show_worker_error("登录失败", error, detail))

        threading.Thread(target=work, daemon=True, name="icloud-login").start()

    def _auto_restore_failed(self, exc: Exception, details: str) -> None:
        print(details, file=sys.stderr)
        self.backend.api = None
        self._set_busy(False, f"自动恢复失败：{exc}。请输入密码重新连接。")
        self.connection_badge.setText("需要重新登录")
        self._show_page("account")

    def _after_connect(self, state: str) -> None:
        if state == "2fa":
            self._set_busy(False, "需要双重认证。验证码通常会推送到受信任 Apple 设备。")
            verification = VerificationCodeDialog(self)
            if verification.exec() != QDialog.DialogCode.Accepted:
                self.login_status_label.setText("已取消验证码输入。")
                return
            code = verification.code()
            self._set_busy(True, "正在验证双重认证码…")

            def verify() -> None:
                try:
                    if not self.backend.verify_2fa(code):
                        raise RuntimeError("验证码无效或会话未受信任")
                    self._post_ui(self._finish_login)
                except Exception as exc:
                    details = traceback.format_exc()
                    self._post_ui(
                        lambda error=exc, detail=details: self._show_worker_error("双重认证失败", error, detail)
                    )

            threading.Thread(target=verify, daemon=True, name="icloud-2fa").start()
            return
        if state == "2sa":
            self._set_busy(False, "该账号使用旧式两步验证，请先通过 icloudpd 完成认证。")
            NoticeDialog.show_message(
                self,
                title="检测到旧式两步验证",
                message="请先使用 icloudpd --auth-only 完成 2SA 认证，再返回应用恢复会话。",
                kind="warning",
            )
            return
        self._finish_login()

    def _finish_login(self) -> None:
        self._set_busy(True, "登录成功，正在读取相簿列表…")

        def work() -> None:
            try:
                names = self.backend.album_names()
                self._post_ui(lambda values=names: self._after_album_names(values))
            except Exception as exc:
                details = traceback.format_exc()
                self._post_ui(lambda error=exc, detail=details: self._show_worker_error("读取相簿失败", error, detail))

        threading.Thread(target=work, daemon=True, name="icloud-albums").start()

    def _after_album_names(self, names: list[str]) -> None:
        self._loaded_album = None
        self._all_items_loaded = False
        self.album_combo.blockSignals(True)
        self.album_combo.clear()
        self.album_combo.addItems(["全部照片"] + names)
        self.album_combo.setCurrentText("Live" if "Live" in names else "全部照片")
        self.album_combo.blockSignals(False)
        self.album_combo.setEnabled(True)
        self._update_load_buttons()
        self.password_edit.clear()
        if self.remember_account_toggle.isChecked():
            self.settings.remember_account = True
            self.settings.account = self._current_account()
            self.settings.login_method = "phone" if self.phone_login_toggle.isChecked() else "email"
            self.settings.country_code = self._normalized_country_code()
            self.settings.domain = self.domain_combo.currentText().strip() or "cn"
            self.settings.cookie_dir = str(Path(self.cookie_edit.text()).expanduser())
            self.settings.last_login_ok = True
            saved = self._save_settings(silent=True)
        else:
            self.settings.remember_account = False
            self.settings.account = ""
            self.settings.last_login_ok = False
            saved = self._save_settings(silent=True)
        message = "已恢复登录状态。可以开始加载照片。" if self._auto_restoring else "已连接。可以开始加载照片。"
        if self.remember_account_toggle.isChecked() and saved:
            message = "已连接并保存登录状态（未保存密码）。可以开始加载照片。"
        self._set_busy(False, message)
        self.connection_badge.setText("iCloud 已连接")
        self.load_btn.setEnabled(True)
        self._auto_restoring = False
        self._show_library(False)

    def _show_worker_error(self, title: str, exc: Exception, details: str) -> None:
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(0)
            self.progress_text_label.setText(f"{title}：{exc}")
        self._set_busy(False, f"{title}：{exc}")
        print(details, file=sys.stderr)
        NoticeDialog.show_message(self, title=title, message=str(exc), kind="error")

    def _requested_load_count(self) -> int:
        try:
            limit = int(self.limit_edit.text())
        except ValueError:
            limit = 300
        limit = max(20, min(limit, 5000))
        self.limit_edit.setText(str(limit))
        return limit

    def load_assets(self) -> None:
        self._start_asset_load(append=False, load_all=False)

    def load_more_assets(self) -> None:
        album = self.album_combo.currentText() or "全部照片"
        append = bool(self.items) and self._loaded_album == album
        self._start_asset_load(append=append, load_all=False)

    def load_all_assets(self) -> None:
        album = self.album_combo.currentText() or "全部照片"
        append = bool(self.items) and self._loaded_album == album
        self._start_asset_load(append=append, load_all=True)

    def _start_asset_load(self, *, append: bool, load_all: bool) -> None:
        if self._busy:
            return
        limit = None if load_all else self._requested_load_count()
        album = self.album_combo.currentText() or "全部照片"
        known_asset_ids = set(self.item_by_id) if append else None
        if load_all:
            action = "剩余全部" if append else "全部"
            busy_message = f"正在从“{album}”读取{action}照片…"
        elif append:
            busy_message = f"正在从“{album}”继续读取 {limit} 张照片…"
        else:
            busy_message = f"正在从“{album}”读取最近 {limit} 张照片…"
        self._set_busy(True, busy_message)
        self.progress.setRange(0, 0)
        self.progress_text_label.setText(f"正在读取“{album}”中的照片列表…")

        def work() -> None:
            try:
                page = self.backend.load_items_page(
                    album,
                    start=0,
                    limit=limit,
                    known_asset_ids=known_asset_ids,
                )
                self._post_ui(
                    lambda loaded=page: self._after_items_page(
                        loaded,
                        album=album,
                        append=append,
                        requested_all=load_all,
                    )
                )
            except Exception as exc:
                details = traceback.format_exc()
                self._post_ui(lambda error=exc, detail=details: self._show_worker_error("加载照片失败", error, detail))

        thread_name = "icloud-list-all" if load_all else "icloud-list-more" if append else "icloud-list"
        threading.Thread(target=work, daemon=True, name=thread_name).start()

    def _after_items(self, items: list[MediaItem]) -> None:
        """Compatibility hook used by screenshot helpers and existing tests."""
        album = self.album_combo.currentText() or "全部照片"
        self._after_items_page(
            MediaPage(items=items, exhausted=False, total_assets=len(items)),
            album=album,
            append=False,
            requested_all=False,
        )

    def _after_items_page(
        self,
        page: MediaPage,
        *,
        album: str,
        append: bool,
        requested_all: bool,
    ) -> None:
        if append:
            existing_ids = set(self.item_by_id)
            added_items: list[MediaItem] = []
            for item in page.items:
                if item.asset_id in existing_ids:
                    continue
                existing_ids.add(item.asset_id)
                added_items.append(item)
            self.items.extend(added_items)
            self.item_by_id.update((item.asset_id, item) for item in added_items)
        else:
            self._load_generation += 1
            self.items = list(page.items)
            added_items = list(page.items)
            self.item_by_id = {item.asset_id: item for item in self.items}
            self.thumbnail_images.clear()
            self.thumbnail_pending.clear()
            self.thumbnail_errors.clear()
            self._deferred_thumbnails.clear()
            self.gallery.clear_thumbnails()
        self._loaded_album = album
        self._all_items_loaded = page.exhausted
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        if append:
            summary = f"新增 {len(added_items)} 张，共已读取 {len(self.items)} 张照片"
        else:
            summary = f"已读取 {len(self.items)} 张照片"
        if page.exhausted:
            summary += "，已到相簿末尾"
        elif requested_all:
            summary += "，但相簿仍有未读取内容"
        self.progress_text_label.setText(f"{summary}，正在按可见区域加载缩略图。")
        self._set_busy(False, f"{summary}。缩略图会继续在后台补齐。")
        self.apply_filter()
        self._update_selection_text()

    # ---------- Gallery and selection ----------

    def apply_filter(self) -> None:
        query = self.search_edit.text().strip().lower()
        live_only = self.live_only_toggle.isChecked()
        filtered = [
            item
            for item in self.items
            if (not live_only or item.is_live)
            and (not query or query in item.filename.lower() or query in item.created_text.lower())
        ]
        self.filtered_items = sort_media_items(filtered, self.sort_combo.currentText())
        self._render_gallery()
        self._update_selection_text()

    def _render_gallery(self) -> None:
        if self.filtered_items:
            self.gallery.set_items(
                self.filtered_items,
                pair_mode=self.auto_pair_toggle.isChecked(),
                thumbnail_cache=self.thumbnail_images,
                thumbnail_errors=set(self.thumbnail_errors),
            )
            return
        if self.backend.api is None:
            self.gallery.show_empty(
                "连接 iCloud，开始浏览照片",
                "登录后可查看缩略图，并按需框选照片和配套实况视频。",
                "前往连接 iCloud  →",
                lambda: self._show_page("account"),
            )
        elif self.items:
            self.gallery.show_empty(
                "没有符合筛选条件的照片",
                "可以清除搜索内容或关闭 Live Photo 筛选。",
                "清除筛选",
                self._clear_filters,
            )
        else:
            self.gallery.show_empty(
                "媒体库还没有加载",
                "选择相簿和数量，然后从 iCloud 读取照片。",
                "加载 iCloud 照片  →",
                self.load_assets,
            )

    def _clear_filters(self) -> None:
        self.search_edit.clear()
        self.live_only_toggle.setChecked(False)
        self.apply_filter()
        self._show_page("library")

    def _request_thumbnail(self, item: MediaItem) -> None:
        if item.asset_id in self.thumbnail_pending or self.gallery.has_thumbnail(item.asset_id):
            return
        self.thumbnail_pending.add(item.asset_id)
        generation = self._load_generation
        quality = self.settings.thumbnail_quality
        future = self.thumbnail_executor.submit(self.backend.fetch_thumbnail, item, quality)
        future.add_done_callback(
            lambda result, asset_id=item.asset_id, gen=generation: self._thumbnail_ready(asset_id, gen, result)
        )

    def _thumbnail_ready(self, asset_id: str, generation: int, future: Any) -> None:
        try:
            image = future.result()
        except Exception as exc:
            self._post_ui(lambda aid=asset_id, gen=generation, error=exc: self._thumbnail_failed(aid, gen, error))
            return
        self._post_ui(lambda aid=asset_id, gen=generation, preview=image: self._install_thumbnail(aid, gen, preview))

    def _thumbnail_failed(self, asset_id: str, generation: int, exc: Exception) -> None:
        if generation != self._load_generation:
            return
        self.thumbnail_pending.discard(asset_id)
        self.thumbnail_errors[asset_id] = str(exc)
        self.gallery.mark_thumbnail_failed(asset_id)
        print(f"Thumbnail failed for {asset_id}: {exc}", file=sys.stderr)

    def _install_thumbnail(self, asset_id: str, generation: int, image: Image.Image) -> None:
        if generation != self._load_generation:
            return
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self._deferred_thumbnails[asset_id] = (generation, image)
            if not self.thumbnail_flush_timer.isActive():
                self.thumbnail_flush_timer.start(70)
            return
        self.thumbnail_pending.discard(asset_id)
        self.thumbnail_errors.pop(asset_id, None)
        self.gallery.install_thumbnail(asset_id, image)

    def _preview_item(self, item: MediaItem) -> None:
        dialog = self.preview_dialog
        created = dialog is None or not dialog.isVisible()
        if created:
            dialog = ImagePreviewDialog(item.filename, self)
            self.preview_dialog = dialog
            dialog.previous_requested.connect(lambda: self._navigate_preview(-1))
            dialog.next_requested.connect(lambda: self._navigate_preview(1))
            dialog.finished.connect(lambda _result, target=dialog: self._preview_closed(target))
            dialog.show()
            dialog.move(
                self.x() + max(0, (self.width() - dialog.width()) // 2),
                self.y() + max(0, (self.height() - dialog.height()) // 2),
            )
        elif self.preview_current_id == item.asset_id:
            dialog.raise_()
            dialog.activateWindow()
            return
        self._load_preview_item(item, dialog)
        dialog.raise_()
        dialog.activateWindow()

    def _preview_sequence(self) -> list[MediaItem]:
        if any(item.asset_id == self.preview_current_id for item in self.filtered_items):
            return self.filtered_items
        return self.items

    def _load_preview_item(self, item: MediaItem, dialog: ImagePreviewDialog) -> None:
        sequence = self.filtered_items if any(
            candidate.asset_id == item.asset_id for candidate in self.filtered_items
        ) else self.items
        try:
            index = next(
                index for index, candidate in enumerate(sequence) if candidate.asset_id == item.asset_id
            )
        except StopIteration:
            sequence = [item]
            index = 0
        self.preview_current_id = item.asset_id
        self._preview_generation += 1
        generation = self._preview_generation
        dialog.begin_loading(
            item.filename,
            position_text=f"{index + 1} / {len(sequence)}",
            can_previous=index > 0,
            can_next=index + 1 < len(sequence),
        )
        quality = self.settings.preview_quality
        cache_key = (quality, item.asset_id)
        cached = self.preview_cache.get(cache_key)
        if cached is not None:
            self.preview_cache.move_to_end(cache_key)
            self._show_preview_payload(item.asset_id, dialog, generation, cache_key, cached)
            return
        if self._preview_future is not None:
            self._preview_future.cancel()
        future = self.preview_executor.submit(self.backend.fetch_preview, item, quality)
        self._preview_future = future
        future.add_done_callback(
            lambda result, asset_id=item.asset_id, target=dialog, gen=generation, key=cache_key: (
                self._preview_future_done(asset_id, target, gen, key, result)
            )
        )

    def _navigate_preview(self, delta: int) -> None:
        dialog = self.preview_dialog
        if dialog is None or not dialog.isVisible() or self.preview_current_id is None:
            return
        sequence = self._preview_sequence()
        try:
            index = next(
                index
                for index, item in enumerate(sequence)
                if item.asset_id == self.preview_current_id
            )
        except StopIteration:
            return
        target_index = index + delta
        if 0 <= target_index < len(sequence):
            self._load_preview_item(sequence[target_index], dialog)

    def _preview_closed(self, dialog: ImagePreviewDialog) -> None:
        if self.preview_dialog is dialog:
            self.preview_dialog = None
            self.preview_current_id = None
            self._preview_generation += 1
            if self._preview_future is not None:
                self._preview_future.cancel()
            self._preview_future = None

    def _preview_future_done(
        self,
        asset_id: str,
        dialog: ImagePreviewDialog,
        generation: int,
        cache_key: tuple[str, str],
        future: Any,
    ) -> None:
        try:
            image = future.result().convert("RGBA")
            payload = image.tobytes("raw", "RGBA"), image.width, image.height
        except Exception as exc:
            self._post_ui(
                lambda error=exc, aid=asset_id, target=dialog, gen=generation: self._show_preview_error(
                    aid, target, gen, error
                )
            )
            return
        self._post_ui(
            lambda data=payload, aid=asset_id, target=dialog, gen=generation, key=cache_key: self._show_preview_payload(
                aid, target, gen, key, data
            )
        )

    def _show_preview_payload(
        self,
        asset_id: str,
        dialog: ImagePreviewDialog,
        generation: int,
        cache_key: tuple[str, str],
        payload: tuple[bytes, int, int],
    ) -> None:
        self._remember_preview(cache_key, payload)
        if (
            self.preview_dialog is not dialog
            or self.preview_current_id != asset_id
            or self._preview_generation != generation
            or not dialog.isVisible()
        ):
            return
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            QTimer.singleShot(
                80,
                lambda: self._show_preview_payload(asset_id, dialog, generation, cache_key, payload),
            )
            return
        dialog.show_image(*payload)

    def _remember_preview(
        self,
        cache_key: tuple[str, str],
        payload: tuple[bytes, int, int],
    ) -> None:
        byte_count = len(payload[0])
        if byte_count > 96 * 1024 * 1024:
            return
        previous = self.preview_cache.pop(cache_key, None)
        if previous is not None:
            self._preview_cache_bytes -= len(previous[0])
        self.preview_cache[cache_key] = payload
        self._preview_cache_bytes += byte_count
        while self._preview_cache_bytes > 96 * 1024 * 1024 and self.preview_cache:
            _old_key, old_payload = self.preview_cache.popitem(last=False)
            self._preview_cache_bytes -= len(old_payload[0])

    def _show_preview_error(
        self,
        asset_id: str,
        dialog: ImagePreviewDialog,
        generation: int,
        error: Exception,
    ) -> None:
        if (
            self.preview_dialog is dialog
            and self.preview_current_id == asset_id
            and self._preview_generation == generation
            and dialog.isVisible()
        ):
            dialog.show_error(str(error))

    def _flush_deferred_thumbnails(self) -> None:
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.thumbnail_flush_timer.start(70)
            return
        pending = self._deferred_thumbnails
        self._deferred_thumbnails = {}
        for asset_id, (generation, image) in pending.items():
            self._install_thumbnail(asset_id, generation, image)

    def retry_failed_thumbnails(self) -> None:
        failed = set(self.thumbnail_errors)
        if not failed:
            NoticeDialog.show_message(self, title="无需重试", message="当前没有失败的缩略图。")
            return
        self.thumbnail_errors.clear()
        self.thumbnail_pending.difference_update(failed)
        for asset_id in failed:
            item = self.item_by_id.get(asset_id)
            if item:
                self._request_thumbnail(item)
        self.login_status_label.setText(f"正在重试 {len(failed)} 个失败缩略图…")

    def _card_clicked(self, asset_id: str, _additive: bool) -> None:
        item = self.item_by_id.get(asset_id)
        if item is None:
            return
        item.select_pair(not item.selected)
        self.gallery.refresh_selection({asset_id})
        self._update_selection_text()

    def _box_selected(self, asset_ids: set[str], additive: bool) -> None:
        previous = {item.asset_id: (item.selected_photo, item.selected_live) for item in self.items}
        if not additive:
            for item in self.items:
                item.select_pair(False)
        for asset_id in asset_ids:
            item = self.item_by_id.get(asset_id)
            if item:
                item.select_pair(True)
        changed = {
            item.asset_id
            for item in self.items
            if previous[item.asset_id] != (item.selected_photo, item.selected_live)
        }
        self.gallery.refresh_selection(changed)
        self._update_selection_text()

    def _manual_selection_changed(self, _item: MediaItem) -> None:
        self._update_selection_text()

    def set_visible_selection(self, selected: bool) -> None:
        for item in self.filtered_items:
            item.select_pair(selected)
        self.gallery.refresh_selection({item.asset_id for item in self.filtered_items})
        self._update_selection_text()

    def select_live_only(self) -> None:
        for item in self.items:
            item.select_pair(item.is_live)
        self.gallery.refresh_selection({item.asset_id for item in self.items})
        self._update_selection_text()

    def _update_selection_text(self) -> None:
        photos = sum(item.selected_photo for item in self.items)
        live = sum(item.selected_live for item in self.items)
        text = f"已选：{photos} 张照片 + {live} 个实况视频" if self.items else "尚未加载"
        self.selection_badge.setText(text)
        self.settings_selection_badge.setText(text)
        self._update_download_button()

    def _update_download_button(self) -> None:
        any_selected = any(item.selected_photo or item.selected_live for item in self.items)
        self.download_btn.setEnabled(any_selected and not self._busy)

    # ---------- Download ----------

    def _selected_plan(self) -> list[tuple[MediaItem, str, Path]]:
        output = Path(self.output_edit.text()).expanduser()
        plan: list[tuple[MediaItem, str, Path]] = []
        claimed: set[str] = set()

        def unique_photo_name(item: MediaItem) -> Path:
            base = Path(safe_filename(item.filename))
            photo_key = str((output / base).resolve()).casefold()
            live_suffix = "_LIVE.MOV" if self.live_suffix_toggle.isChecked() else ".MOV"
            live_key = str((output / f"{base.stem}{live_suffix}").resolve()).casefold()
            if photo_key not in claimed and live_key not in claimed:
                return base
            short_id = re.sub(r"[^0-9A-Za-z]", "", item.asset_id)[-7:] or "icloud"
            return base.with_name(f"{base.stem}_{short_id}{base.suffix}")

        for item in self.items:
            if not (item.selected_photo or item.selected_live):
                continue
            photo_name = unique_photo_name(item)
            if item.selected_photo:
                photo_target = output / photo_name
                claimed.add(str(photo_target.resolve()).casefold())
                plan.append((item, "photo", photo_target))
            if item.is_live and item.selected_live:
                suffix = "_LIVE.MOV" if self.live_suffix_toggle.isChecked() else ".MOV"
                live_target = output / f"{photo_name.stem}{suffix}"
                claimed.add(str(live_target.resolve()).casefold())
                plan.append((item, "live", live_target))
        return plan

    def start_download(self) -> None:
        if self._busy:
            return
        plan = self._selected_plan()
        if not plan:
            NoticeDialog.show_message(self, title="尚未选择照片", message="请先在媒体库中选择要下载的照片。", kind="warning")
            return
        output = Path(self.output_edit.text()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            NoticeDialog.show_message(self, title="无法创建下载目录", message=str(exc), kind="error")
            return
        self._preferences_changed()
        overwrite = self.overwrite_toggle.isChecked()
        photo_size = self.settings.photo_size
        live_size = self.settings.live_size
        fix_orientation = self.fix_orientation_toggle.isChecked()
        self._busy = True
        self.connect_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self._update_load_buttons()
        self.download_btn.setEnabled(False)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress_text_label.setText(f"准备下载 {len(plan)} 个文件…")

        def work() -> None:
            ok = 0
            skipped = 0
            repaired_existing = 0
            failed: list[str] = []
            warnings: list[str] = []
            bytes_written = 0
            for index, (item, kind, target) in enumerate(plan, start=1):
                try:
                    if target.exists() and not overwrite:
                        if kind == "live" and fix_orientation:
                            result = repair_mov_orientation(
                                target,
                                asset_exif_orientation(item.asset),
                            )
                            if result.changed:
                                repaired_existing += 1
                                status = f"已修复已有 MOV：{target.name}"
                            else:
                                skipped += 1
                                status = f"跳过已有文件：{target.name}"
                            if result.warning:
                                warnings.append(f"{target.name}: {result.warning}")
                        else:
                            skipped += 1
                            status = f"跳过已有文件：{target.name}"
                    else:
                        size = photo_size if kind == "photo" else live_size
                        written = self.backend.download_version(item, kind, size, target)
                        orientation_fixed = False
                        if kind == "live" and fix_orientation:
                            result = repair_mov_orientation(target, asset_exif_orientation(item.asset))
                            orientation_fixed = result.changed
                            if result.warning:
                                warnings.append(f"{target.name}: {result.warning}")
                        final_size = target.stat().st_size if target.exists() else written
                        bytes_written += final_size
                        ok += 1
                        suffix = "，方向已校正" if orientation_fixed else ""
                        status = f"已下载：{target.name} ({human_bytes(final_size)}{suffix})"
                except Exception as exc:
                    failed.append(f"{target.name}: {exc}")
                    status = f"失败：{target.name} — {exc}"
                self._post_ui(
                    lambda i=index, text=status, total=len(plan): self._download_progress(i, total, text)
                )
            self._post_ui(
                lambda: self._download_done(
                    ok,
                    skipped,
                    repaired_existing,
                    failed,
                    warnings,
                    bytes_written,
                    output,
                )
            )

        threading.Thread(target=work, daemon=True, name="icloud-download").start()

    def _download_progress(self, index: int, total: int, status: str) -> None:
        self.progress.setValue(round(index / max(1, total) * 1000))
        self.progress_text_label.setText(status)

    def _download_done(
        self,
        ok: int,
        skipped: int,
        repaired_existing: int,
        failed: list[str],
        warnings: list[str],
        bytes_written: int,
        output: Path,
    ) -> None:
        self._busy = False
        self.connect_btn.setEnabled(True)
        self.load_btn.setEnabled(self.backend.api is not None)
        self._update_load_buttons()
        self._update_download_button()
        summary = (
            f"完成：{ok} 个下载，{repaired_existing} 个已有 MOV 已修复，"
            f"{skipped} 个跳过，{len(failed)} 个失败，共 {human_bytes(bytes_written)}。"
        )
        self.progress_text_label.setText(summary)
        details: list[str] = []
        if failed:
            details.append("失败：\n" + "\n".join(failed[:12]))
        if warnings:
            print("MOV orientation notes:\n" + "\n".join(warnings), file=sys.stderr)
            details.append(
                f"方向提示：{len(warnings)} 个 MOV 无法自动校正，原文件已安全保留。"
                + ("\n" + "\n".join(warnings[:3]) if warnings else "")
            )
        DownloadResultDialog(
            self,
            summary=summary,
            output=output,
            details="\n\n".join(details),
            open_directory=self.open_output_directory,
        ).exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._sync_preferences_to_settings()
        self._save_settings(silent=True)
        self.thumbnail_executor.shutdown(wait=False, cancel_futures=True)
        self.preview_executor.shutdown(wait=False, cancel_futures=True)
        event.accept()


def main() -> int:
    configure_windows_app_id()
    application = QApplication.instance()
    owns_application = application is None
    if application is None:
        application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.setOrganizationName("iCloud Live Photo Picker contributors")
    icon = QIcon(str(asset_path("app-icon.ico")))
    if not icon.isNull():
        application.setWindowIcon(icon)
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLESHEET)
    window = PickerWindow()
    window.show()
    smoke_test_ms = os.environ.get("ICLOUD_PICKER_SMOKE_TEST_MS", "").strip()
    if smoke_test_ms:
        try:
            QTimer.singleShot(max(250, int(smoke_test_ms)), window.close)
        except ValueError:
            pass
    if owns_application:
        return application.exec()
    return 0
