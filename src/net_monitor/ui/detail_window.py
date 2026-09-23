from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from net_monitor.core.elevation import restart_as_administrator
from net_monitor.core.models import MonitorSnapshot
from net_monitor.services.monitor_service import MonitorService
from net_monitor.ui.main_window import MainWindow
from net_monitor.ui.micro_model import SESSION_CAPTION
from net_monitor.ui.network_spotlight import SpotlightFrame
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
        # Spotlight summary label
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt
        self._spotlight_label = QLabel()
        self._spotlight_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._spotlight_label.setWordWrap(True)
        self._spotlight_label.setStyleSheet('QLabel { padding: 8px; background: #2a2a2a; border-radius: 4px; margin: 4px; }')
        self._spotlight_label.setVisible(False)
        
        self.tabs = QTabWidget()
        self.session_view = SessionView()
        self.tabs.addTab(self.live_page, "当前应用 / PID")
        self.tabs.addTab(self.session_view, SESSION_CAPTION)
        
        # Vertical layout with spotlight on top
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._spotlight_label)
        central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

    def update_spotlight(self, frame) -> None:
        """Update spotlight summary from WidgetFrame."""
        if frame is None or not hasattr(frame, 'spotlight') or frame.spotlight is None:
            self._spotlight_label.setVisible(False)
            return
        
        spotlight = frame.spotlight
        if not spotlight.source_usable:
            self._spotlight_label.setVisible(False)
            return
        
        lines = []
        
        # Foreground
        if spotlight.foreground is not None:
            fg_name = spotlight.foreground.name
            fg_total = spotlight.foreground.total_bps
            if fg_total is not None:
                from net_monitor.core.formatting import format_bytes_per_second
                lines.append(f'前台: {fg_name} ({format_bytes_per_second(fg_total)})')
            else:
                lines.append(f'前台: {fg_name}')
        else:
            lines.append('前台: 未知')
        
        # Background
        bg_total = spotlight.background_total_bps
        if bg_total is not None:
            from net_monitor.core.formatting import format_bytes_per_second
            bg_text = format_bytes_per_second(bg_total)
            if spotlight.background_share is not None and spotlight.share_reliable:
                pct = round(spotlight.background_share * 100)
                lines.append(f'后台: {bg_text} ({pct}%)')
            else:
                lines.append(f'后台: {bg_text}')
        else:
            lines.append('后台: 无活动')
        
        # Dominant background
        if spotlight.dominant_background is not None:
            dom_name = spotlight.dominant_background.name
            dom_total = spotlight.dominant_background.total_bps
            if dom_total is not None:
                from net_monitor.core.formatting import format_bytes_per_second
                lines.append(f'主导后台: {dom_name} ({format_bytes_per_second(dom_total)})')
            else:
                lines.append(f'主导后台: {dom_name}')
        
        self._spotlight_label.setText('\n'.join(lines))
        self._spotlight_label.setVisible(True)

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
