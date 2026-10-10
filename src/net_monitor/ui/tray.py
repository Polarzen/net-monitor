from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon


class TrayController:
    def __init__(self, *, show_compact, show_details, set_always_on_top, request_exit) -> None:
        self._show_compact = show_compact
        self._show_details = show_details
        self._set_always_on_top = set_always_on_top
        self._request_exit = request_exit
        self._tray: QSystemTrayIcon | None = None
        self._pin_action: QAction | None = None
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.available:
            return

        style = QApplication.style()
        icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        tray = QSystemTrayIcon(icon)
        tray.setToolTip("Net Monitor")
        menu = QMenu()

        show_action = menu.addAction("显示 Net Monitor")
        show_action.triggered.connect(self._show_compact)
        details_action = menu.addAction("详细信息")
        details_action.triggered.connect(self._show_details)
        menu.addSeparator()
        self._pin_action = menu.addAction("总在最前")
        self._pin_action.setCheckable(True)
        self._pin_action.toggled.connect(self._set_always_on_top)
        menu.addSeparator()
        exit_action = menu.addAction("退出")
        exit_action.triggered.connect(self._request_exit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_activated)
        tray.show()
        self._tray = tray

    def set_always_on_top_checked(self, enabled: bool) -> None:
        if self._pin_action is None or self._pin_action.isChecked() == enabled:
            return
        self._pin_action.blockSignals(True)
        self._pin_action.setChecked(enabled)
        self._pin_action.blockSignals(False)

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_compact()
