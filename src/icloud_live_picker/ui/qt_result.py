from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .qt_widgets import COLORS, make_label, set_role


class DownloadResultDialog(QDialog):
    """Project-styled replacement for the platform QMessageBox download result."""

    def __init__(
        self,
        parent: QWidget,
        *,
        summary: str,
        output: Path,
        details: str = "",
        open_directory: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        has_issues = bool(details)
        self.setWindowTitle("下载完成，但有提示" if has_issues else "下载完成")
        self.setMinimumWidth(660)
        self.setMaximumWidth(820)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("surface")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(16)
        icon = QLabel("!" if has_issues else "✓")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(52, 52)
        icon.setStyleSheet(
            f"background:{'#F6E8D3' if has_issues else COLORS['primary_soft']};"
            f"color:{'#9A6619' if has_issues else COLORS['primary_hover']};"
            "border:0;border-radius:17px;font:700 23px 'Microsoft YaHei UI';"
        )
        card_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(7)
        text_layout.addWidget(
            make_label("下载完成，但有提示" if has_issues else "下载完成", object_name="sectionTitle")
        )
        text_layout.addWidget(make_label(summary, object_name="muted", word_wrap=True))
        path_label = QLabel(f"保存位置  {output}")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)
        path_label.setStyleSheet(
            f"background:{COLORS['surface_alt']};color:{COLORS['text']};"
            "border:0;border-radius:10px;padding:10px 12px;"
        )
        text_layout.addWidget(path_label)
        card_layout.addWidget(text, 1)
        layout.addWidget(card)

        if details:
            detail_box = QPlainTextEdit(details)
            detail_box.setReadOnly(True)
            detail_box.setMaximumHeight(180)
            detail_box.setStyleSheet(
                f"QPlainTextEdit{{background:{COLORS['surface']};color:{COLORS['text']};"
                f"border:1px solid {COLORS['border']};border-radius:12px;padding:10px;}}"
            )
            layout.addWidget(detail_box)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_button = QPushButton("打开下载目录")
        self.open_button.setObjectName("openDirectoryButton")
        set_role(self.open_button, "soft")
        self.open_button.clicked.connect(open_directory)
        buttons.addWidget(self.open_button)
        done_button = QPushButton("完成")
        set_role(done_button, "primary")
        done_button.setMinimumWidth(100)
        done_button.clicked.connect(self.accept)
        buttons.addWidget(done_button)
        layout.addLayout(buttons)
        done_button.setFocus()
