"""Small desktop entrance and a singleton, non-activating preview card."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QKeyEvent, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from net_monitor.ui.micro_model import MICRO_SIZE, AppChoice, DisplayState, WidgetFrame, format_rate
from net_monitor.ui.sparkline import Sparkline
from net_monitor.ui.session_view import SessionTotals


def set_text(label: QLabel, text: str) -> None:
    if label.text() != text:
        label.setText(text)


def plain_label(text: str = "", *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    return label


class KeyButton(QPushButton):
    """Capture identity on press, not after the next sorting/refresh tick."""
    key_activated = Signal(str)

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.key = ""
        self._pressed_key: str | None = None
        self.pressed.connect(self._capture)
        self.released.connect(self._release)
        self.clicked.connect(self._activate)
        self._released_key: str | None = None

    def _capture(self) -> None:
        self._pressed_key = self.key
        self._released_key = None

    def _release(self) -> None:
        self._released_key = self._pressed_key
        self._pressed_key = None

    def _activate(self) -> None:
        key = self._released_key if self._released_key is not None else self.key
        self._released_key = None
        if key:
            self.key_activated.emit(key)

    def bind(self, key: str, text: str, *, enabled: bool = True) -> None:
        # Avoid visually replacing A while the user is holding down A's button.
        if self.isDown():
            return
        self.key = key
        if self.text() != text:
            self.setText(text)
        if self.isEnabled() != enabled:
            self.setEnabled(enabled)


class ApplicationChooser(QFrame):
    """Bounded popup for browsing every application choice."""

    closed = Signal()
    choice_selected = Signal(str)

    WIDTH = 372
    HEIGHT = 460

    def __init__(self, choices: tuple[AppChoice, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("applicationChooser")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            "QFrame#applicationChooser { background:#20242b; border:1px solid #465260; "
            "border-radius:10px; }"
        )
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._closed_emitted = False

        title = plain_label("选择应用")
        title.setStyleSheet("font-weight:600; padding:4px 6px 2px 6px;")

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(4)
        self._buttons: list[QPushButton] = []
        for choice in choices:
            # Keep the visible row compact even when the executable path is very
            # long; the full identity remains available in the tooltip and key
            # binding below.
            button = QPushButton(choice.name.replace("&", "&&"))
            button.setEnabled(choice.can_follow)
            button.setMinimumHeight(40)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setToolTip(
                f"{choice.name}\n{choice.executable or choice.key}\n"
                + ("固定关注此 application key" if choice.can_follow
                   else "身份不稳定，不能固定关注")
            )
            button.clicked.connect(
                lambda checked=False, key=choice.key: self._select(key)
            )
            body_layout.addWidget(button)
            self._buttons.append(button)
        if not choices:
            empty = plain_label("暂无可选择的应用")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_layout.addWidget(empty)
        body_layout.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setObjectName("applicationChooserScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setWidget(body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        layout.addWidget(title)
        layout.addWidget(self.scroll, 1)

    def show_at(self, anchor: QPoint, reference: QWidget) -> None:
        """Place below the trigger when possible, clamped to screen work area."""

        screen = QApplication.screenAt(anchor) or reference.screen() or QApplication.primaryScreen()
        if screen is None:
            self.show()
            return
        area = screen.availableGeometry()
        width = min(self.WIDTH, max(1, area.width()))
        height = min(self.HEIGHT, max(1, area.height()))
        self.setFixedSize(width, height)
        right = area.right() - width + 1
        bottom = area.bottom() - height + 1
        x = min(max(anchor.x(), area.left()), right)
        y = anchor.y()
        if y > bottom:
            reference_top = reference.mapToGlobal(QPoint(0, 0)).y()
            y = reference_top - height
        y = min(max(y, area.top()), bottom)
        self.move(x, y)
        self.show()
        self.raise_()

    def _select(self, key: str) -> None:
        self.close()
        self.choice_selected.emit(key)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._notify_closed()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        # Qt.Popup can dismiss itself by hiding on an outside click. Keep the
        # card's lifecycle state in sync for both hide and close paths.
        self._notify_closed()
        super().hideEvent(event)

    def _notify_closed(self) -> None:
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit()


class MicroWindow(QFrame):
    clicked = Signal()
    entered = Signal()
    left = Signal()
    drag_started = Signal()
    drag_finished = Signal()
    moved = Signal()
    menu_requested = Signal(object)
    close_requested = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Net Monitor · 微型窗")
        self.setObjectName("microWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(*MICRO_SIZE)
        self.setStyleSheet("QFrame#microWindow { background:#20242b; border:1px solid #465260; border-radius:10px; }")
        self._press: QPoint | None = None
        self._origin = QPoint()
        self._dragging = False
        self._shutdown = False
        self._frame: WidgetFrame | None = None

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        self.name_label = plain_label("启动中")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.badge_label = plain_label("·")
        self.badge_label.setMinimumWidth(48)
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header = QHBoxLayout()
        header.setSpacing(3)
        header.addWidget(self.icon_label)
        header.addWidget(self.name_label, 1)
        header.addWidget(self.badge_label)
        self.download_label = plain_label("↓ —")
        self.upload_label = plain_label("↑ —")
        for label in (self.download_label, self.upload_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.state_label = plain_label("启动中", wrap=True)
        self.state_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._sparkline = Sparkline()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self.download_label)
        layout.addWidget(self.upload_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self._sparkline)
        for label in self.findChildren(QLabel):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def apply_frame(self, frame: WidgetFrame) -> None:
        if frame == self._frame:
            return
        self._frame = frame
        name = frame.selected.name if frame.selected else "Net Monitor"
        display_name = self.name_label.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideRight, max(1, self.name_label.width()))
        set_text(self.name_label, display_name)
        self.name_label.setToolTip(name)
        if not frame.source_usable:
            badge = "!"
        else:
            badge = frame.presence.value
        set_text(self.badge_label, badge)
        mode = "固定关注" if frame.focused else "自动显示"
        self.badge_label.setToolTip(mode + "；" + frame.presence.value)
        set_text(self.download_label, "↓ 下载 " + format_rate(frame.download, compact=True))
        set_text(self.upload_label, "↑ 上传 " + format_rate(frame.upload, compact=True))
        if frame.selected is None and frame.source_usable:
            activity = f"当前安静 · {mode}\n暂无明显网络活动"
        elif frame.state is DisplayState.ACTIVE:
            activity = f"当前有流量 · {mode}"
        elif frame.state is DisplayState.IDLE:
            activity = f"当前无流量 · {mode}"
        elif frame.source_state is DisplayState.STALE:
            activity = f"{frame.presence.value} · 数据已过期"
        elif frame.source_state is DisplayState.FAILED:
            activity = f"{frame.presence.value} · 采样失败"
        elif frame.source_state is DisplayState.PERMISSION:
            activity = f"{frame.presence.value} · 需要管理员权限"
        elif frame.source_state is DisplayState.UNAVAILABLE:
            activity = f"采集不可用 · {mode}"
        elif frame.state is DisplayState.NOT_RUNNING:
            activity = f"当前未运行 · {mode}"
        else:
            activity = f"状态未知 · {mode}"
        set_text(self.state_label, activity)
        self.setToolTip(f"{name}\n{frame.presence.value}\n{activity}\n{frame.message}\n"
                        "↓ 下载 / ↑ 上传；B 是字节，KiB=1024 B。点击展开，右键菜单。")
        if hasattr(frame, 'rate_history'):
            self._sparkline.set_data(frame.rate_history)

    def set_icon(self, icon: QIcon) -> None:
        self.icon_label.setPixmap(icon.pixmap(16, 16))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._frame is not None:
            frame, self._frame = self._frame, None
            self.apply_frame(frame)

    def enterEvent(self, event) -> None:
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.left.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None:
            return super().mouseMoveEvent(event)
        delta = event.globalPosition().toPoint() - self._press
        if not self._dragging and delta.manhattanLength() >= QApplication.startDragDistance():
            self._dragging = True
            self.drag_started.emit()
        if self._dragging:
            self.move(self._origin + delta)
            self.moved.emit()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return super().mouseReleaseEvent(event)
        dragged = self._dragging
        self._press, self._dragging = None, False
        if dragged:
            self.drag_finished.emit()
        elif self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        event.accept()

    def contextMenuEvent(self, event) -> None:
        self.menu_requested.emit(event.globalPos())
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._shutdown:
            event.ignore()
            self.close_requested.emit()
        else:
            super().closeEvent(event)


class ApplicationCard(QFrame):
    entered = Signal()
    left = Signal()
    interacted = Signal()
    collapse_requested = Signal()
    details_requested = Signal()
    follow_requested = Signal(str)
    unfollow_requested = Signal()
    elevate_requested = Signal()
    menu_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Net Monitor · 应用卡片")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("applicationCard")
        self.setStyleSheet("QFrame#applicationCard { border:1px solid #465260; border-radius:10px; }")
        self.resize(372, 460)
        self._frame: WidgetFrame | None = None
        self._chooser: ApplicationChooser | None = None
        self._menu_open = False
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.name_label = plain_label("启动中", wrap=True)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label = plain_label("路径不可用", wrap=True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.path_label.setMaximumHeight(64)
        self.state_label = plain_label("启动中", wrap=True)
        self.mode_label = plain_label("自动显示（对象切换有防抖）")
        self.rates_label = plain_label("↓ 下载 —\n↑ 上传 —", wrap=True)
        self.focus_button = KeyButton("固定关注")
        self.focus_button.key_activated.connect(self.follow_requested.emit)
        self.unfocus_button = QPushButton("取消关注")
        self.unfocus_button.clicked.connect(self.unfollow_requested.emit)
        self.choose_button = QPushButton("选择应用…")
        self.choose_button.clicked.connect(self._show_chooser)
        self.restart_button = QPushButton("以管理员身份重启")
        self.restart_button.clicked.connect(self.elevate_requested.emit)
        self.restart_button.hide()
        self.details_button = QPushButton("详细信息")
        self.details_button.clicked.connect(self.details_requested.emit)
        self.menu_button = QPushButton("菜单")
        self.menu_button.clicked.connect(lambda: self.menu_requested.emit(
            self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft())))
        self._top_rows = [KeyButton() for _ in range(3)]
        for row in self._top_rows:
            row.key_activated.connect(self.follow_requested.emit)
            row.hide()
        self.top_caption = plain_label("当前可见应用 Top 3（按当前速率）")
        self.session_totals = SessionTotals()

        header = QHBoxLayout()
        header.addWidget(self.icon_label)
        header.addWidget(self.name_label, 1)
        attention = QHBoxLayout()
        attention.addWidget(self.focus_button)
        attention.addWidget(self.unfocus_button)
        attention.addWidget(self.choose_button)
        footer = QHBoxLayout()
        footer.addWidget(self.details_button)
        footer.addStretch()
        footer.addWidget(self.menu_button)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(10, 10, 10, 10)
        self.body_layout.setSpacing(6)
        self.body_layout.addLayout(header)
        self.body_layout.addWidget(self.path_label)
        self.body_layout.addWidget(self.state_label)
        self.body_layout.addWidget(self.mode_label)
        self.body_layout.addWidget(self.rates_label)
        self.body_layout.addLayout(attention)
        self.body_layout.addWidget(self.session_totals)
        self.body_layout.addWidget(self.top_caption)
        for row in self._top_rows:
            self.body_layout.addWidget(row)
        self._sparkline = Sparkline()
        self.body_layout.addWidget(self._sparkline)
        self.body_layout.addWidget(self.restart_button)
        self.body_layout.addLayout(footer)
        self.body_layout.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(body)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self.scroll)
        self.escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape.activated.connect(self.collapse_requested.emit)
        for widget in (self, *self.findChildren(QWidget)):
            widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            self.interacted.emit()
        return super().eventFilter(watched, event)

    def apply_frame(self, frame: WidgetFrame) -> None:
        if frame == self._frame:
            return
        self._frame = frame
        choice = frame.selected
        set_text(self.name_label, choice.name if choice else "Net Monitor")
        path = choice.executable if choice and choice.executable else "无可读取的可执行文件路径"
        set_text(self.path_label, path)
        self.path_label.setToolTip(path)
        set_text(self.state_label, frame.message)
        set_text(self.mode_label, "固定关注" if frame.focused else "自动显示（对象切换有防抖）")
        set_text(self.rates_label, "↓ 下载 " + format_rate(frame.download)
                 + "\n↑ 上传 " + format_rate(frame.upload))
        self.session_totals.apply_frame(frame)
        self.focus_button.bind(choice.key if choice else "", "固定关注",
                               enabled=bool(choice and choice.can_follow and not frame.focused))
        self.unfocus_button.setVisible(frame.focused)
        self.focus_button.setVisible(not frame.focused)
        self.restart_button.setVisible(frame.source_state.value == "需要管理员权限")
        for index, row in enumerate(self._top_rows):
            if row.isDown():
                continue
            if index >= len(frame.top):
                row.hide()
                continue
            app = frame.top[index]
            # Full name/path are available without widening the card.
            name = row.fontMetrics().elidedText(app.choice.name, Qt.TextElideMode.ElideRight, 125)
            text = f"{name}  ↓{format_rate(app.download, compact=True)} ↑{format_rate(app.upload, compact=True)}"
            row.bind(app.choice.key, text, enabled=app.choice.can_follow)
            row.setToolTip(f"{app.choice.name}\n{app.choice.executable or app.choice.key}\n点击固定关注")
            row.show()
        if hasattr(frame, 'rate_history'):
            self._sparkline.set_data(frame.rate_history)

    def set_icon(self, icon: QIcon) -> None:
        self.icon_label.setPixmap(icon.pixmap(24, 24))

    def _show_chooser(self) -> None:
        self.interacted.emit()
        if self._frame is None:
            return
        if self._chooser is not None and self._chooser.isVisible():
            self._chooser.raise_()
            return
        # Freeze this popup's key bindings until it closes. Never update it on tick.
        chooser = ApplicationChooser(self._frame.choices, self)
        chooser.choice_selected.connect(self.follow_requested.emit)
        chooser.closed.connect(lambda chooser=chooser: self._chooser_closed(chooser))
        self._chooser = chooser
        self._menu_open = True
        chooser.show_at(
            self.choose_button.mapToGlobal(self.choose_button.rect().bottomLeft()),
            self.choose_button,
        )

    def _chooser_closed(self, chooser: ApplicationChooser) -> None:
        if self._chooser is not chooser:
            return
        self._menu_open = False
        self._chooser = None
        chooser.deleteLater()

    def hideEvent(self, event) -> None:
        if self._chooser is not None:
            self._chooser.close()
        super().hideEvent(event)

    def enterEvent(self, event) -> None:
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.left.emit()
        super().leaveEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.collapse_requested.emit()
