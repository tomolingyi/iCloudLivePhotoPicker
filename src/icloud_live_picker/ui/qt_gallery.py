from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from PIL import Image
from .qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractScrollArea, QFrame, QPushButton, QWidget

from ..models import MediaItem
from .qt_widgets import COLORS, set_role


class GalleryView(QAbstractScrollArea):
    CARD_WIDTH = 214
    CARD_HEIGHT = 258
    ROW_HEIGHT = 272
    GAP = 14
    THUMB_HEIGHT = 142
    MAX_CACHED_PIXMAPS = 500

    def __init__(
        self,
        parent: QWidget,
        *,
        on_card_clicked: Callable[[str, bool], None],
        on_box_selected: Callable[[set[str], bool], None],
        on_selection_changed: Callable[[MediaItem], None],
        on_need_thumbnail: Callable[[MediaItem], None],
        on_preview_requested: Callable[[MediaItem], None],
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setMouseTracking(True)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

        self.on_card_clicked = on_card_clicked
        self.on_box_selected = on_box_selected
        self.on_selection_changed = on_selection_changed
        self.on_need_thumbnail = on_need_thumbnail
        self.on_preview_requested = on_preview_requested
        self.items: list[MediaItem] = []
        self.item_by_id: dict[str, MediaItem] = {}
        self.pair_mode = True
        self.pixmaps: OrderedDict[str, QPixmap] = OrderedDict()
        self.thumbnail_errors: set[str] = set()
        self._requested_this_paint: set[str] = set()
        self._columns = 2
        self._cell_width = 230.0
        self._content_height = 0

        self._empty_title = ""
        self._empty_detail = ""
        self._empty_action: Callable[[], None] | None = None
        self._empty_action_button = QPushButton(self.viewport())
        self._empty_action_button.setObjectName("emptyActionButton")
        set_role(self._empty_action_button, "primary")
        self._empty_action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._empty_action_button.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        self._empty_action_button.setFixedSize(220, 46)
        self._empty_action_button.clicked.connect(self._activate_empty_action)
        self._empty_action_button.hide()

        self._press_viewport: QPointF | None = None
        self._press_content: QPointF | None = None
        self._current_content: QPointF | None = None
        self._pressed_asset_id: str | None = None
        self._manual_target: str | None = None
        self._pressed_preview_id: str | None = None
        self._hovered_filename_id: str | None = None
        self._dragged = False
        self._preview_ids: set[str] = set()
        self._auto_scroll_direction = 0
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(28)
        self._auto_scroll_timer.timeout.connect(self._auto_scroll_step)
        self._thumbnail_kick_timer = QTimer(self)
        self._thumbnail_kick_timer.setSingleShot(True)
        self._thumbnail_kick_timer.setInterval(160)
        self._thumbnail_kick_timer.timeout.connect(self.request_visible_thumbnails)

    def set_items(
        self,
        items: list[MediaItem],
        *,
        pair_mode: bool,
        thumbnail_cache: dict[str, Image.Image],
        thumbnail_errors: set[str],
    ) -> None:
        self.items = list(items)
        self.item_by_id = {item.asset_id: item for item in items}
        self.pair_mode = pair_mode
        self.thumbnail_errors = set(thumbnail_errors)
        self._requested_this_paint.clear()
        self._empty_title = ""
        self._empty_action = None
        self._empty_action_button.hide()
        for asset_id, image in thumbnail_cache.items():
            if asset_id not in self.pixmaps:
                self.install_thumbnail(asset_id, image)
        self.verticalScrollBar().setValue(0)
        self._update_scroll_range()
        self.viewport().update()
        # A page/layout switch can invalidate the first paint before its queued
        # thumbnail callbacks run. Request the visible cards once immediately
        # and once after geometry settles so the first row cannot remain blank.
        self.request_visible_thumbnails()
        self._thumbnail_kick_timer.start()

    def show_empty(
        self,
        title: str,
        detail: str,
        action_text: str,
        action: Callable[[], None],
    ) -> None:
        self.items = []
        self.item_by_id = {}
        self._empty_title = title
        self._empty_detail = detail
        self._empty_action = action
        self.verticalScrollBar().setRange(0, 0)
        self._empty_action_button.setText(action_text)
        self._position_empty_action()
        self._empty_action_button.setVisible(bool(action_text))
        self.viewport().update()

    def _activate_empty_action(self) -> None:
        if not self.items and self._empty_action is not None:
            self._empty_action()

    def _position_empty_action(self) -> None:
        self._empty_action_button.move(
            round((self.viewport().width() - self._empty_action_button.width()) / 2),
            round(self.viewport().height() * 0.43 + 98),
        )

    def set_pair_mode(self, pair_mode: bool) -> None:
        self.pair_mode = pair_mode
        self.viewport().update()

    def install_thumbnail(self, asset_id: str, image: Image.Image | QPixmap) -> None:
        if isinstance(image, QPixmap):
            pixmap = image
        else:
            rgba = image.convert("RGBA")
            raw = rgba.tobytes("raw", "RGBA")
            qimage = QImage(raw, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
            pixmap = QPixmap.fromImage(qimage)
        self.pixmaps[asset_id] = pixmap
        self.pixmaps.move_to_end(asset_id)
        while len(self.pixmaps) > self.MAX_CACHED_PIXMAPS:
            evicted, _pixmap = self.pixmaps.popitem(last=False)
            self._requested_this_paint.discard(evicted)
        self.thumbnail_errors.discard(asset_id)
        self._requested_this_paint.discard(asset_id)
        self.viewport().update()

    def has_thumbnail(self, asset_id: str) -> bool:
        return asset_id in self.pixmaps

    def clear_thumbnails(self) -> None:
        self.pixmaps.clear()
        self._requested_this_paint.clear()
        self.thumbnail_errors.clear()
        self.viewport().update()

    def mark_thumbnail_failed(self, asset_id: str) -> None:
        self.thumbnail_errors.add(asset_id)
        self._requested_this_paint.discard(asset_id)
        self.viewport().update()

    def refresh_selection(self, _asset_ids: set[str] | None = None) -> None:
        self.viewport().update()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._update_scroll_range()
        self._position_empty_action()

    def _update_scroll_range(self) -> None:
        width = max(1, self.viewport().width())
        usable = max(self.CARD_WIDTH * 2, width - 20)
        self._columns = max(2, int((usable + self.GAP) // (self.CARD_WIDTH + self.GAP)))
        self._cell_width = usable / self._columns
        rows = math.ceil(len(self.items) / self._columns) if self.items else 0
        self._content_height = max(0, rows * self.ROW_HEIGHT + 14)
        maximum = max(0, self._content_height - self.viewport().height())
        bar = self.verticalScrollBar()
        bar.setPageStep(max(1, self.viewport().height()))
        bar.setSingleStep(48)
        bar.setRange(0, maximum)

    def _card_rect(self, index: int) -> QRectF:
        row, column = divmod(index, self._columns)
        x = 10 + column * self._cell_width + (self._cell_width - self.CARD_WIDTH) / 2
        y = 7 + row * self.ROW_HEIGHT
        return QRectF(x, y, self.CARD_WIDTH, self.CARD_HEIGHT)

    def _visible_index_range(self) -> range:
        if not self.items:
            return range(0)
        scroll = self.verticalScrollBar().value()
        first_row = max(0, scroll // self.ROW_HEIGHT - 2)
        last_row = min(
            math.ceil(len(self.items) / self._columns) - 1,
            (scroll + self.viewport().height()) // self.ROW_HEIGHT + 2,
        )
        return range(first_row * self._columns, min(len(self.items), (last_row + 1) * self._columns))

    def request_visible_thumbnails(self) -> None:
        """Ensure every currently visible card has a thumbnail task."""
        for index in self._visible_index_range():
            item = self.items[index]
            if item.asset_id in self.pixmaps or item.asset_id in self.thumbnail_errors:
                continue
            self._requested_this_paint.add(item.asset_id)
            self.on_need_thumbnail(item)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The surrounding gallery surface already owns the rounded panel.
        # Painting another tinted rectangle here created a square inner frame.
        painter.fillRect(self.viewport().rect(), QColor(COLORS["surface"]))
        if not self.items:
            self._paint_empty(painter)
            return

        scroll = self.verticalScrollBar().value()
        need: list[MediaItem] = []
        for index in self._visible_index_range():
            item = self.items[index]
            rect = self._card_rect(index).translated(0, -scroll)
            self._paint_card(painter, item, rect)
            if item.asset_id not in self.pixmaps and item.asset_id not in self.thumbnail_errors:
                if item.asset_id not in self._requested_this_paint:
                    self._requested_this_paint.add(item.asset_id)
                    need.append(item)

        if self._press_content is not None and self._current_content is not None and self._dragged:
            selection = QRectF(self._press_content, self._current_content).normalized().translated(0, -scroll)
            painter.setPen(QPen(QColor(COLORS["primary"]), 2))
            painter.setBrush(QColor(39, 139, 130, 38))
            painter.drawRect(selection)
        painter.end()
        for item in need:
            QTimer.singleShot(0, lambda target=item: self.on_need_thumbnail(target))

    def _paint_empty(self, painter: QPainter) -> None:
        center_x = self.viewport().width() / 2
        center_y = self.viewport().height() * 0.43
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["primary_soft"]))
        painter.drawRoundedRect(QRectF(center_x - 36, center_y - 76, 72, 72), 24, 24)
        painter.setPen(QColor(COLORS["primary"]))
        painter.setFont(QFont("Segoe UI Symbol", 24, QFont.Weight.Bold))
        painter.drawText(QRectF(center_x - 36, center_y - 76, 72, 72), Qt.AlignmentFlag.AlignCenter, "☁")
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(QFont("Microsoft YaHei UI", 20, QFont.Weight.Bold))
        painter.drawText(QRectF(20, center_y + 10, self.viewport().width() - 40, 36), Qt.AlignmentFlag.AlignCenter, self._empty_title)
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Microsoft YaHei UI", 11))
        painter.drawText(QRectF(20, center_y + 50, self.viewport().width() - 40, 30), Qt.AlignmentFlag.AlignCenter, self._empty_detail)

    def _paint_card(self, painter: QPainter, item: MediaItem, rect: QRectF) -> None:
        selected = item.selected
        preview = item.asset_id in self._preview_ids
        painter.setPen(QPen(QColor(COLORS["primary"] if selected or preview else COLORS["border"]), 2 if selected or preview else 1))
        painter.setBrush(QColor(COLORS["primary_soft"] if preview else COLORS["surface"]))
        painter.drawRoundedRect(rect, 11, 11)

        thumb = QRectF(rect.left() + 10, rect.top() + 10, rect.width() - 20, self.THUMB_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#E8F0EE"))
        painter.drawRoundedRect(thumb, 7, 7)
        pixmap = self.pixmaps.get(item.asset_id)
        if pixmap is not None and not pixmap.isNull():
            self.pixmaps.move_to_end(item.asset_id)
            scaled = pixmap.scaled(
                int(thumb.width()),
                int(thumb.height()),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            source = QRectF(
                max(0, (scaled.width() - thumb.width()) / 2),
                max(0, (scaled.height() - thumb.height()) / 2),
                thumb.width(),
                thumb.height(),
            )
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(thumb, 7, 7)
            painter.setClipPath(clip)
            painter.drawPixmap(thumb, scaled, source)
            painter.restore()
        else:
            painter.setPen(QColor(COLORS["muted"]))
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            message = "预览加载失败" if item.asset_id in self.thumbnail_errors else "正在加载预览…"
            painter.drawText(thumb, Qt.AlignmentFlag.AlignCenter, message)

        name_hovered = item.asset_id == self._hovered_filename_id
        painter.setPen(QColor(COLORS["primary_hover"] if name_hovered else COLORS["text"]))
        name_font = QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold)
        name_font.setUnderline(name_hovered)
        painter.setFont(name_font)
        name_rect = self._filename_rect(rect, item)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(item.filename, Qt.TextElideMode.ElideRight, int(name_rect.width())))
        if item.is_live:
            badge = QRectF(rect.right() - 49, rect.top() + 164, 37, 19)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["primary_soft"]))
            painter.drawRoundedRect(badge, 6, 6)
            painter.setPen(QColor(COLORS["primary_hover"]))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Weight.Bold))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "LIVE")
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRectF(rect.left() + 11, rect.top() + 191, rect.width() - 22, 20), Qt.AlignmentFlag.AlignVCenter, item.created_text)

        footer = QRectF(rect.left() + 11, rect.bottom() - 39, rect.width() - 22, 28)
        if self.pair_mode:
            painter.setPen(QColor(COLORS["primary_hover"]))
            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold))
            painter.drawText(footer, Qt.AlignmentFlag.AlignVCenter, "照片 + MOV" if item.is_live else "照片")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["primary"] if selected else COLORS["surface_alt"]))
            painter.drawEllipse(QRectF(footer.right() - 22, footer.top() + 3, 22, 22))
            if selected:
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(QRectF(footer.right() - 22, footer.top() + 3, 22, 22), Qt.AlignmentFlag.AlignCenter, "✓")
        else:
            half = footer.width() / (2 if item.is_live else 1)
            self._paint_manual_choice(painter, QRectF(footer.left(), footer.top(), half, footer.height()), "照片", item.selected_photo)
            if item.is_live:
                self._paint_manual_choice(painter, QRectF(footer.left() + half, footer.top(), half, footer.height()), "MOV", item.selected_live)

    def _paint_manual_choice(self, painter: QPainter, rect: QRectF, text: str, selected: bool) -> None:
        box = QRectF(rect.left(), rect.top() + 5, 18, 18)
        painter.setPen(QPen(QColor(COLORS["primary"] if selected else COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["primary"] if selected else COLORS["surface"]))
        painter.drawRoundedRect(box, 5, 5)
        if selected:
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "✓")
        painter.setPen(QColor(COLORS["primary_hover"]))
        painter.drawText(QRectF(rect.left() + 24, rect.top(), rect.width() - 24, rect.height()), Qt.AlignmentFlag.AlignVCenter, text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if not self.items:
            return
        self.setFocus()
        self._press_viewport = event.position()
        self._press_content = QPointF(event.position().x(), event.position().y() + self.verticalScrollBar().value())
        self._current_content = QPointF(self._press_content)
        card = self._card_at(self._press_content)
        self._pressed_asset_id = card[1].asset_id if card else None
        self._manual_target = self._manual_target_at(card[0], self._press_content, card[1]) if card else None
        self._pressed_preview_id = (
            card[1].asset_id
            if card and self._filename_rect(card[0], card[1]).contains(self._press_content)
            else None
        )
        self._dragged = False
        self._preview_ids.clear()
        self.viewport().update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_content is None or self._press_viewport is None:
            content = QPointF(event.position().x(), event.position().y() + self.verticalScrollBar().value())
            card = self._card_at(content)
            hovered = (
                card[1].asset_id
                if card and self._filename_rect(card[0], card[1]).contains(content)
                else None
            )
            if hovered != self._hovered_filename_id:
                self._hovered_filename_id = hovered
                self.viewport().setCursor(
                    Qt.CursorShape.PointingHandCursor if hovered else Qt.CursorShape.ArrowCursor
                )
                self.viewport().setToolTip("点击预览照片" if hovered else "")
                self.viewport().update()
            return
        if (event.position() - self._press_viewport).manhattanLength() > 5:
            self._dragged = True
        self._current_content = QPointF(event.position().x(), event.position().y() + self.verticalScrollBar().value())
        if self._dragged:
            self._preview_ids = self._ids_in_rect(QRectF(self._press_content, self._current_content).normalized())
        self._update_auto_scroll(event.position().y())
        self.viewport().update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press_content is None:
            return
        self._auto_scroll_timer.stop()
        additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if self._dragged:
            self.on_box_selected(set(self._preview_ids), additive)
        elif self._pressed_asset_id is not None:
            item = self.item_by_id.get(self._pressed_asset_id)
            if item is not None and self._pressed_preview_id == item.asset_id:
                self.on_preview_requested(item)
            elif item is not None and not self.pair_mode and self._manual_target is not None:
                if self._manual_target == "photo":
                    item.selected_photo = not item.selected_photo
                elif item.is_live:
                    item.selected_live = not item.selected_live
                self.on_selection_changed(item)
                self.viewport().update()
            else:
                self.on_card_clicked(self._pressed_asset_id, additive)
        elif not additive:
            self.on_box_selected(set(), False)
        self._press_viewport = None
        self._press_content = None
        self._current_content = None
        self._pressed_asset_id = None
        self._manual_target = None
        self._pressed_preview_id = None
        self._preview_ids.clear()
        self.viewport().update()

    def leaveEvent(self, event: Any) -> None:
        super().leaveEvent(event)
        if self._hovered_filename_id is not None:
            self._hovered_filename_id = None
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport().setToolTip("")
            self.viewport().update()

    def _card_at(self, point: QPointF) -> tuple[QRectF, MediaItem] | None:
        row = max(0, int(point.y() // self.ROW_HEIGHT))
        for candidate_row in (row - 1, row, row + 1):
            if candidate_row < 0:
                continue
            for column in range(self._columns):
                index = candidate_row * self._columns + column
                if index >= len(self.items):
                    break
                rect = self._card_rect(index)
                if rect.contains(point):
                    return rect, self.items[index]
        return None

    def _manual_target_at(self, rect: QRectF, point: QPointF, item: MediaItem) -> str | None:
        if self.pair_mode or point.y() < rect.bottom() - 45:
            return None
        if not item.is_live:
            return "photo"
        return "photo" if point.x() < rect.center().x() else "live"

    @staticmethod
    def _filename_rect(rect: QRectF, item: MediaItem) -> QRectF:
        name_width = rect.width() - (72 if item.is_live else 22)
        return QRectF(rect.left() + 11, rect.top() + 162, name_width, 24)

    def _ids_in_rect(self, selection: QRectF) -> set[str]:
        if not self.items:
            return set()
        first_row = max(0, int((selection.top() - self.CARD_HEIGHT) // self.ROW_HEIGHT))
        last_row = min(math.ceil(len(self.items) / self._columns) - 1, int(selection.bottom() // self.ROW_HEIGHT))
        selected: set[str] = set()
        for row in range(first_row, last_row + 1):
            for column in range(self._columns):
                index = row * self._columns + column
                if index >= len(self.items):
                    break
                if self._card_rect(index).intersects(selection):
                    selected.add(self.items[index].asset_id)
        return selected

    def _update_auto_scroll(self, y: float) -> None:
        margin = 58
        if y < margin:
            self._auto_scroll_direction = -max(1, min(8, round((margin - y) / 10)))
        elif y > self.viewport().height() - margin:
            self._auto_scroll_direction = max(1, min(8, round((y - (self.viewport().height() - margin)) / 10)))
        else:
            self._auto_scroll_direction = 0
        if self._auto_scroll_direction and not self._auto_scroll_timer.isActive():
            self._auto_scroll_timer.start()
        elif not self._auto_scroll_direction:
            self._auto_scroll_timer.stop()

    def _auto_scroll_step(self) -> None:
        if self._press_content is None or self._current_content is None:
            self._auto_scroll_timer.stop()
            return
        bar = self.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + self._auto_scroll_direction * 12)
        delta = bar.value() - before
        if delta == 0:
            self._auto_scroll_timer.stop()
            return
        self._current_content.setY(self._current_content.y() + delta)
        self._preview_ids = self._ids_in_rect(QRectF(self._press_content, self._current_content).normalized())
        self.viewport().update()
