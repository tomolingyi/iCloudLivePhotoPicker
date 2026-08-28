from __future__ import annotations

from .qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtCore import QRegularExpression, Qt
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .qt_widgets import COLORS, make_label, set_role


def _dialog_icon(text: str, *, warning: bool = False) -> QLabel:
    icon = QLabel(text)
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setFixedSize(52, 52)
    icon.setStyleSheet(
        f"background:{'#F6E8D3' if warning else COLORS['primary_soft']};"
        f"color:{'#9A6619' if warning else COLORS['primary_hover']};"
        "border:0;border-radius:17px;font:700 22px 'Microsoft YaHei UI';"
    )
    return icon


class NoticeDialog(QDialog):
    """Unified information, warning and error dialog used throughout the app."""

    _PRESENTATION = {
        "info": ("i", False),
        "warning": ("!", True),
        "error": ("×", True),
    }

    def __init__(self, parent: QWidget, *, title: str, message: str, kind: str = "info") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        icon_text, warning = self._PRESENTATION.get(kind, self._PRESENTATION["info"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("surface")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(16)
        card_layout.addWidget(_dialog_icon(icon_text, warning=warning), 0, Qt.AlignmentFlag.AlignTop)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addWidget(make_label(title, object_name="sectionTitle"))
        message_label = make_label(message, object_name="muted", word_wrap=True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(message_label)
        card_layout.addWidget(content, 1)
        layout.addWidget(card)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        done = QPushButton("知道了")
        set_role(done, "primary")
        done.setMinimumWidth(100)
        done.clicked.connect(self.accept)
        buttons.addWidget(done)
        layout.addLayout(buttons)
        done.setFocus()

    @classmethod
    def show_message(
        cls,
        parent: QWidget,
        *,
        title: str,
        message: str,
        kind: str = "info",
    ) -> None:
        cls(parent, title=title, message=message, kind=kind).exec()


class SessionClearDialog(QDialog):
    """Project-styled confirmation for deleting one account's local session."""

    def __init__(self, parent: QWidget, session_directory: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("清理本地会话")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("surface")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(16)
        card_layout.addWidget(_dialog_icon("?", warning=True), 0, Qt.AlignmentFlag.AlignTop)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addWidget(make_label("清理当前账号的本地会话？", object_name="sectionTitle"))
        content_layout.addWidget(
            make_label(
                "只会删除当前账号的会话令牌，不会删除照片、下载文件或其他账号的会话。",
                object_name="muted",
                word_wrap=True,
            )
        )
        path_label = QLabel(session_directory)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)
        path_label.setStyleSheet(
            f"background:{COLORS['surface_alt']};border:0;border-radius:10px;padding:10px 12px;"
        )
        content_layout.addWidget(path_label)
        card_layout.addWidget(content, 1)
        layout.addWidget(card)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        confirm = QPushButton("清理会话")
        set_role(confirm, "primary")
        confirm.setMinimumWidth(108)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        cancel.setFocus()


class VerificationCodeDialog(QDialog):
    """Project-styled six-digit Apple verification-code prompt."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("双重认证")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("surface")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(16)
        card_layout.addWidget(_dialog_icon("✓"), 0, Qt.AlignmentFlag.AlignTop)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addWidget(make_label("输入 Apple 验证码", object_name="sectionTitle"))
        content_layout.addWidget(
            make_label(
                "请输入发送到受信任 Apple 设备的 6 位数字验证码。验证码不会保存。",
                object_name="muted",
                word_wrap=True,
            )
        )
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("6 位验证码")
        self.code_edit.setMaxLength(6)
        self.code_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,6}"), self))
        self.code_edit.returnPressed.connect(self._accept_complete_code)
        content_layout.addWidget(self.code_edit)
        card_layout.addWidget(content, 1)
        layout.addWidget(card)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.confirm_button = QPushButton("验证")
        set_role(self.confirm_button, "primary")
        self.confirm_button.setMinimumWidth(100)
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

        self.code_edit.textChanged.connect(
            lambda text: self.confirm_button.setEnabled(len(text.strip()) == 6)
        )
        self.code_edit.setFocus()

    def _accept_complete_code(self) -> None:
        if self.confirm_button.isEnabled():
            self.accept()

    def code(self) -> str:
        return self.code_edit.text().strip()
