from __future__ import annotations

from .qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .qt_widgets import COLORS, make_label


def preview_arrow_icon(direction: int) -> QIcon:
    """Draw a geometrically centered arrow instead of relying on font baselines."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(COLORS["primary_hover"]), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    if direction < 0:
        path.moveTo(14.5, 6.5)
        path.lineTo(8.5, 12)
        path.lineTo(14.5, 17.5)
    else:
        path.moveTo(9.5, 6.5)
        path.lineTo(15.5, 12)
        path.lineTo(9.5, 17.5)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class ScaledPreviewLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self._source = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(420, 320)
        self.setStyleSheet(f"background:{COLORS['surface_alt']}; border:0; border-radius:14px;")

    def set_source(self, pixmap: QPixmap) -> None:
        self._source = pixmap
        self._rescale()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._source.isNull() or self.width() < 2 or self.height() < 2:
            return
        self.setPixmap(
            self._source.scaled(
                QSize(max(1, self.width() - 20), max(1, self.height() - 20)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class ImagePreviewDialog(QDialog):
    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()

    def __init__(self, filename: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"照片预览 · {filename}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(760, 540)
        self.resize(1060, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        self.title_label = make_label(filename, object_name="sectionTitle")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header_layout.addWidget(self.title_label, 1)
        self.position_label = make_label("", object_name="badge")
        header_layout.addWidget(self.position_label)
        self.resolution_label = make_label("正在读取高清预览…", object_name="muted")
        header_layout.addWidget(self.resolution_label)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        self.previous_button = QPushButton()
        self.previous_button.setProperty("previewNav", True)
        self.previous_button.setIcon(preview_arrow_icon(-1))
        self.previous_button.setIconSize(QSize(24, 24))
        self.previous_button.setAccessibleName("上一张")
        self.previous_button.setToolTip("上一张（←）")
        self.previous_button.clicked.connect(self.previous_requested.emit)
        content_layout.addWidget(self.previous_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.stack = QStackedWidget()
        self.status_label = QLabel("正在从 iCloud 加载高清预览…")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_status_style(error=False)
        self.image_label = ScaledPreviewLabel()
        self.stack.addWidget(self.status_label)
        self.stack.addWidget(self.image_label)
        content_layout.addWidget(self.stack, 1)

        self.next_button = QPushButton()
        self.next_button.setProperty("previewNav", True)
        self.next_button.setIcon(preview_arrow_icon(1))
        self.next_button.setIconSize(QSize(24, 24))
        self.next_button.setAccessibleName("下一张")
        self.next_button.setToolTip("下一张（→）")
        self.next_button.clicked.connect(self.next_requested.emit)
        content_layout.addWidget(self.next_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(content, 1)

        self.previous_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.previous_shortcut.activated.connect(self.previous_button.click)
        self.next_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.next_shortcut.activated.connect(self.next_button.click)

        hint = make_label("← / → 切换照片 · Esc 关闭 · 预览不会下载到本地", object_name="muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    def begin_loading(
        self,
        filename: str,
        *,
        position_text: str,
        can_previous: bool,
        can_next: bool,
    ) -> None:
        self.setWindowTitle(f"照片预览 · {filename}")
        self.title_label.setText(filename)
        self.position_label.setText(position_text)
        self.previous_button.setEnabled(can_previous)
        self.next_button.setEnabled(can_next)
        self.resolution_label.setText("正在读取预览…")
        self.status_label.setText("正在从 iCloud 加载照片预览…")
        self._set_status_style(error=False)
        self.stack.setCurrentWidget(self.status_label)

    def show_image(self, rgba_bytes: bytes, width: int, height: int) -> None:
        image = QImage(
            rgba_bytes,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        self.image_label.set_source(QPixmap.fromImage(image))
        self.resolution_label.setText(f"{width} × {height}")
        self.stack.setCurrentWidget(self.image_label)

    def show_error(self, message: str) -> None:
        self.status_label.setText(f"预览加载失败\n\n{message}")
        self._set_status_style(error=True)
        self.resolution_label.setText("加载失败")
        self.stack.setCurrentWidget(self.status_label)

    def _set_status_style(self, *, error: bool) -> None:
        color = COLORS["danger"] if error else COLORS["muted"]
        self.status_label.setStyleSheet(
            f"background:{COLORS['surface_alt']}; color:{color}; "
            f"border:1px solid {COLORS['border']}; border-radius:14px;"
        )
