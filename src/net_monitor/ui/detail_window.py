from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from net_monitor.core.elevation import restart_as_administrator
from net_monitor.core.models import MonitorSnapshot
from net_monitor.services.monitor_service import MonitorService
from net_monitor.ui.main_window import MainWindow
from net_monitor.ui.micro_model import SESSION_CAPTION
from net_monitor.ui.session_view import SessionView


class DetailWindow(MainWindow):
    """Detailed view that consumes the controller's shared snapshots.

    MainWindow remains backward-compatible for the Stage 2 test surface. This
    subclass deliberately owns no SamplingWorker and never closes the shared
    MonitorService when the user closes only the detailed view.
    """

    def __init__(
        self,
        service: MonitorService,
        *,
        elevation_launcher: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(
            service=service,
            start_worker=False,
            elevation_launcher=elevation_launcher or restart_as_administrator,
        )
        self._controller_shutdown = False
        # Reparent the existing live page, preserving its tree, filters and signals.
        self.live_page = self.takeCentralWidget()
        self.tabs = QTabWidget()
        self.session_view = SessionView()
        self.tabs.addTab(self.live_page, "当前应用 / PID")
        self.tabs.addTab(self.session_view, SESSION_CAPTION)
        self.setCentralWidget(self.tabs)

    def apply_snapshot(self, snapshot: MonitorSnapshot) -> None:
        self._on_snapshot(snapshot)
        self.session_view.apply_snapshot(snapshot)

    def set_shutdown_in_progress(self, shutting_down: bool) -> None:
        self._controller_shutdown = shutting_down

    def closeEvent(self, event: QCloseEvent) -> None:
        # Bypass MainWindow.closeEvent(): DetailWindow does not own the shared
        # worker/service. Closing this view must not stop ETW collection.
        QMainWindow.closeEvent(self, event)

    def _restart_with_elevation(self) -> None:
        self._restart_as_admin_button.setEnabled(False)
        self._restart_as_admin_button.setText("正在请求管理员权限…")
        try:
            started = self._elevation_launcher()
        except Exception as exc:  # pragma: no cover - defensive OS boundary
            started = False
            self._restart_as_admin_button.setToolTip(f"管理员重启失败：{exc}")
        if started:
            QApplication.quit()
            return
        self._restart_as_admin_button.setText("以管理员身份重启")
        self._restart_as_admin_button.setEnabled(True)
