from __future__ import annotations

from typing import Any

from .qt_bootstrap import prepare_qt_runtime

prepare_qt_runtime()

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFrame,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)


COLORS = {
    "bg": "#F5F8F7",
    "surface": "#FFFFFF",
    "surface_alt": "#EFF5F3",
    "sidebar": "#FBFDFC",
    "primary": "#278B82",
    "primary_hover": "#1E756E",
    "primary_soft": "#DCEFEB",
    "text": "#102120",
    "muted": "#72817E",
    "border": "#DDE7E3",
    "selection": "#BFE2DB",
    "danger": "#D84B4B",
}


APP_STYLESHEET = f"""
* {{
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
    color: {COLORS['text']};
}}
QMainWindow, QDialog, QWidget#appRoot {{ background: {COLORS['bg']}; }}
QWidget#sidebar {{ background: {COLORS['sidebar']}; border-right: 1px solid {COLORS['border']}; }}
QWidget#topbar {{ background: {COLORS['surface']}; border-bottom: 1px solid {COLORS['border']}; }}
QFrame#surface {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 18px;
}}
QFrame#statusSoft {{
    background: {COLORS['primary_soft']};
    border: 0;
    border-radius: 11px;
}}
QLabel#eyebrow {{ color: {COLORS['primary_hover']}; font-weight: 700; }}
QLabel#pageTitle {{ color: {COLORS['text']}; font-size: 30px; font-weight: 700; }}
QLabel#sectionTitle {{ color: {COLORS['text']}; font-size: 15px; font-weight: 700; }}
QLabel#muted {{ color: {COLORS['muted']}; }}
QLabel#badge {{
    color: {COLORS['primary_hover']};
    background: {COLORS['primary_soft']};
    border-radius: 10px;
    padding: 6px 10px;
    font-weight: 700;
}}
QPushButton {{
    min-height: 38px;
    padding: 0 16px;
    border-radius: 11px;
    border: 1px solid {COLORS['border']};
    background: {COLORS['surface']};
    color: {COLORS['muted']};
}}
QPushButton:hover {{ background: {COLORS['surface_alt']}; color: {COLORS['text']}; }}
QPushButton:pressed {{ background: {COLORS['primary_soft']}; }}
QPushButton:disabled {{ color: #AAB5B2; background: #F2F5F4; }}
QPushButton[role="primary"] {{
    background: {COLORS['primary']};
    color: white;
    border: 0;
    font-weight: 700;
}}
QPushButton[role="primary"]:hover {{ background: {COLORS['primary_hover']}; }}
QPushButton[role="soft"] {{
    background: {COLORS['primary_soft']};
    color: {COLORS['primary_hover']};
    border: 0;
    font-weight: 700;
}}
QPushButton[role="soft"]:hover {{
    background: {COLORS['selection']};
    color: {COLORS['primary_hover']};
}}
QPushButton[role="soft"]:pressed {{
    background: #A9D5CD;
}}
QPushButton[nav="true"] {{
    min-height: 44px;
    text-align: left;
    padding-left: 16px;
    border: 0;
    background: transparent;
}}
QPushButton[nav="true"]:checked {{
    background: {COLORS['primary_soft']};
    color: {COLORS['primary_hover']};
    font-weight: 700;
}}
QPushButton[previewNav="true"] {{
    min-width: 48px;
    max-width: 48px;
    min-height: 64px;
    max-height: 64px;
    padding: 0;
    border-radius: 16px;
    background: {COLORS['surface']};
    color: {COLORS['primary_hover']};
}}
QPushButton[previewNav="true"]:hover {{
    background: {COLORS['primary_soft']};
    border-color: {COLORS['selection']};
}}
QPushButton[previewNav="true"]:disabled {{
    background: transparent;
    color: #C3CDCA;
    border-color: #E8EEEC;
}}
QLineEdit {{
    min-height: 40px;
    padding: 0 13px;
    background: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 11px;
    selection-background-color: {COLORS['selection']};
}}
QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; background: {COLORS['surface']}; }}
QComboBox {{
    min-height: 40px;
    padding: 0 38px 0 13px;
    background: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 11px;
}}
QComboBox:hover, QComboBox:on {{ border: 1px solid {COLORS['primary']}; background: {COLORS['surface']}; }}
QComboBox:disabled {{ color: #9AA7A4; background: #F1F4F3; }}
QComboBox::drop-down {{ width: 34px; border: 0; background: transparent; }}
QComboBox::down-arrow {{ image: none; }}
QProgressBar {{
    min-height: 8px;
    max-height: 8px;
    border: 0;
    border-radius: 4px;
    background: {COLORS['surface_alt']};
    text-align: center;
}}
QProgressBar::chunk {{ background: {COLORS['primary']}; border-radius: 4px; }}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 8px 1px;
}}
QScrollBar::handle:vertical {{
    background: #9CCFC6;
    min-height: 46px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{ background: {COLORS['primary']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QToolTip {{
    background: {COLORS['surface']}; color: {COLORS['text']};
    border: 1px solid {COLORS['border']}; padding: 5px;
}}
"""


class ComboItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), 40)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        painter.save()
        rect = option.rect.adjusted(5, 2, -5, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["primary_soft"] if selected else COLORS["surface_alt"]))
            painter.drawRoundedRect(QRectF(rect), 9, 9)
        painter.setPen(QColor(COLORS["primary_hover"] if selected else COLORS["text"]))
        font = option.font
        font.setBold(selected)
        painter.setFont(font)
        text_rect = rect.adjusted(10, 0, -8, 0)
        text = painter.fontMetrics().elidedText(
            str(index.data()), Qt.TextElideMode.ElideRight, max(20, int(text_rect.width()))
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


class ComboPopup(QFrame):
    dismissed = pyqtSignal()

    def __init__(self, combo: "CleanComboBox") -> None:
        super().__init__(
            combo,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.combo = combo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("cleanComboPopup")
        self.setStyleSheet(
            "QListWidget { background:transparent; border:0; padding:4px 0; outline:0; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        self.list = QListWidget(self)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setMinimumSize(0, 0)
        self.list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setItemDelegate(ComboItemDelegate(self.list))
        self.list.itemClicked.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        layout.addWidget(self.list)

    def sync_items(self) -> None:
        self.list.clear()
        for index in range(self.combo.count()):
            item = QListWidgetItem(self.combo.itemText(index))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.list.addItem(item)
        if self.combo.currentIndex() >= 0:
            self.list.setCurrentRow(self.combo.currentIndex())
        self.list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if self.combo.count() <= 8
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["surface"]))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        painter.end()

    def _choose(self, item: QListWidgetItem) -> None:
        self.combo.setCurrentIndex(self.list.row(item))
        self.combo.hidePopup()

    def hideEvent(self, event: Any) -> None:
        super().hideEvent(event)
        self.dismissed.emit()


class CleanComboBox(QComboBox):
    """Single, clean Qt popup implementation used by every selector."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        view = QListView(self)
        view.setObjectName("comboPopup")
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setUniformItemSizes(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setItemDelegate(ComboItemDelegate(view))
        view.setStyleSheet(
            f"QListView {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; "
            "padding: 4px 0; outline: 0; }}"
        )
        self.setView(view)
        self._arrow = QLabel("▾", self)
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(
            f"color: {COLORS['primary_hover']}; background: transparent; border: 0; font-family: 'Segoe UI Symbol';"
        )
        self._arrow.resize(32, 38)
        self._popup = ComboPopup(self)
        self._popup.dismissed.connect(self._popup_dismissed)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._arrow.setGeometry(self.width() - 35, 1, 32, max(1, self.height() - 2))

    def showPopup(self) -> None:
        if not self.isEnabled() or self.count() == 0:
            return
        self._arrow.setText("▴")
        self._popup.sync_items()
        visible_rows = min(8, self.count())
        popup_height = visible_rows * 40 + 14
        popup_width = self.width()
        origin = self.mapToGlobal(QPoint(0, self.height() + 5))
        screen = self.screen().availableGeometry()
        if origin.y() + popup_height > screen.bottom():
            origin.setY(self.mapToGlobal(QPoint(0, -popup_height - 5)).y())
        origin.setX(max(screen.left(), min(origin.x(), screen.right() - popup_width + 1)))
        self._popup.setGeometry(origin.x(), origin.y(), popup_width, popup_height)
        self._popup.show()
        self._popup.raise_()
        self._popup.list.setFocus()
        self._popup.list.scrollToItem(self._popup.list.currentItem())

    def hidePopup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
        self._arrow.setText("▾")

    def _popup_dismissed(self) -> None:
        self._arrow.setText("▾")


class ToggleSwitch(QAbstractButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(30)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(54 + metrics.horizontalAdvance(self.text()), 30)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, 5, 38, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["primary"] if self.isChecked() else "#A5AFAD"))
        painter.drawRoundedRect(track, 10, 10)
        knob_x = 21 if self.isChecked() else 3
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(knob_x, 7, 16, 16))
        painter.setPen(QColor(COLORS["text"] if self.isEnabled() else "#9AA7A4"))
        painter.drawText(
            QRectF(50, 0, self.width() - 50, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )


def set_role(widget: QWidget, role: str) -> QWidget:
    widget.setProperty("role", role)
    if isinstance(widget, QAbstractButton):
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def make_label(text: str = "", *, object_name: str = "", word_wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(word_wrap)
    return label


def make_nav_icon(kind: str) -> QIcon:
    """Build dependency-free, consistently sized line icons for the sidebar."""
    if kind not in {"library", "account", "settings"}:
        raise KeyError(kind)

    def render(color: str) -> QPixmap:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "library":
            painter.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2.5, 2.5)
            painter.drawEllipse(QRectF(14.3, 7.1, 2.6, 2.6))
            path = QPainterPath()
            path.moveTo(5.7, 17)
            path.lineTo(10, 12.4)
            path.lineTo(12.8, 15.1)
            path.lineTo(15.1, 12.9)
            path.lineTo(18.6, 17)
            painter.drawPath(path)
        elif kind == "account":
            painter.drawEllipse(QRectF(8.3, 3.8, 7.4, 7.4))
            path = QPainterPath()
            path.moveTo(4.8, 20)
            path.cubicTo(5.1, 14.4, 8.1, 12.5, 12, 12.5)
            path.cubicTo(15.9, 12.5, 18.9, 14.4, 19.2, 20)
            painter.drawPath(path)
        else:
            for y, knob_x in ((6.0, 9.0), (12.0, 15.0), (18.0, 7.0)):
                painter.drawLine(QPoint(4, int(y)), QPoint(20, int(y)))
                painter.setBrush(QColor(COLORS["surface"]))
                painter.drawEllipse(QRectF(knob_x - 2, y - 2, 4, 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.end()
        return pixmap

    icon = QIcon()
    icon.addPixmap(render(COLORS["muted"]), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(render(COLORS["primary_hover"]), QIcon.Mode.Normal, QIcon.State.On)
    return icon
