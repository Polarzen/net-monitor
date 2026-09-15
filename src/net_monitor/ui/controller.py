from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal
from PySide6.QtWidgets import QApplication

from net_monitor.core.elevation import restart_as_administrator
from net_monitor.core.models import MonitorSnapshot
from net_monitor.services.monitor_service import MonitorService
from net_monitor.ui.compact_window import CompactWindow
from net_monitor.ui.detail_window import DetailWindow
from net_monitor.ui.sampling_worker import SamplingWorker
from net_monitor.ui.tray import TrayController


class UiController(QObject):
    snapshot_ready = Signal(object)
    sampling_failed = Signal(str)

    def __init__(
        self,
        *,
        service: MonitorService | None = None,
        sampling_interval_ms: int = 500,
        elevation_launcher: Callable[[], bool] | None = None,
        start_worker: bool = True,
    ) -> None:
        super().__init__()
        self._service = service or MonitorService()
        self._sampling_interval_ms = sampling_interval_ms
        self._thread: QThread | None = None
        self._worker: SamplingWorker | None = None
        self._latest_snapshot: MonitorSnapshot | None = None
        self._detail_window: DetailWindow | None = None
        self._shutdown_complete = False

        self.compact_window = CompactWindow(
            elevation_launcher=elevation_launcher or restart_as_administrator
        )
        self.compact_window.details_requested.connect(self.show_details)
        self.compact_window.exit_requested.connect(self.exit_application)
        self.compact_window.always_on_top_changed.connect(self.set_always_on_top)
        self.snapshot_ready.connect(self.compact_window.apply_snapshot)

        self.tray = TrayController(
            show_compact=self.show_compact,
            show_details=self.show_details,
            set_always_on_top=self.set_always_on_top,
            request_exit=self.exit_application,
        )
        self.compact_window.set_tray_available(self.tray.available)
        QApplication.instance().setQuitOnLastWindowClosed(not self.tray.available)

        if start_worker:
            self.start()

    @property
    def service(self) -> MonitorService:
        return self._service

    @property
    def detail_window(self) -> DetailWindow | None:
        return self._detail_window

    @property
    def latest_snapshot(self) -> MonitorSnapshot | None:
        return self._latest_snapshot

    def start(self) -> None:
        if self._thread is not None:
            return
        thread = QThread(self)
        worker = SamplingWorker(self._service, interval_ms=self._sampling_interval_ms)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.snapshot_ready.connect(self._on_snapshot)
        worker.sampling_failed.connect(self.sampling_failed.emit)
        self.sampling_failed.connect(self._on_sampling_failed)
        self._thread = thread
        self._worker = worker
        thread.start()

    def show_compact(self) -> None:
        self.compact_window.show()
        self.compact_window.raise_()
        self.compact_window.activateWindow()

    def show_details(self) -> DetailWindow:
        if self._detail_window is None:
            detail = DetailWindow(service=self._service)
            detail.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            self.snapshot_ready.connect(detail.apply_snapshot)
            self._detail_window = detail
            if self._latest_snapshot is not None:
                detail.apply_snapshot(self._latest_snapshot)
        detail = self._detail_window
        detail.show()
        detail.raise_()
        detail.activateWindow()
        return detail

    def set_always_on_top(self, enabled: bool) -> None:
        self.compact_window.set_always_on_top(enabled)
        self.tray.set_always_on_top_checked(enabled)
        detail = self._detail_window
        if detail is not None:
            was_visible = detail.isVisible()
            detail.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
            if was_visible:
                detail.show()

    def exit_application(self) -> None:
        self.shutdown()
        QApplication.quit()

    def shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        self.compact_window.set_shutdown_in_progress(True)
        self.tray.hide()
        if self._detail_window is not None:
            self._detail_window.set_shutdown_in_progress(True)
            self._detail_window.close()
        self.compact_window.close()

        thread = self._thread
        worker = self._worker
        if thread is not None and worker is not None and thread.isRunning():
            QMetaObject.invokeMethod(worker, "stop", Qt.ConnectionType.BlockingQueuedConnection)
            thread.quit()
            thread.wait()
        else:
            self._service.close()

    def _on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        self._latest_snapshot = snapshot
        self.snapshot_ready.emit(snapshot)

    def _on_sampling_failed(self, message: str) -> None:
        self.compact_window._status_label.setText("采样失败")
        self.compact_window._status_label.setObjectName("statusError")
        self.compact_window._status_label.setToolTip(message)
