from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from net_monitor.core.models import MonitorSnapshot
from net_monitor.services.monitor_service import MonitorService


class SamplingWorker(QObject):
    """Own periodic MonitorService sampling on a dedicated Qt worker thread."""

    snapshot_ready = Signal(object)
    sampling_failed = Signal(str)
    stopped = Signal()

    def __init__(self, service: MonitorService, *, interval_ms: int = 500) -> None:
        super().__init__()
        self._service = service
        self._interval_ms = max(50, interval_ms)
        self._timer: QTimer | None = None
        self._running = False
        self._closed = False

    @Slot()
    def start(self) -> None:
        if self._running or self._closed:
            return
        self._running = True
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.sample_once)
        self._timer.start()
        self.sample_once()

    @Slot()
    def sample_once(self) -> None:
        if not self._running:
            return
        try:
            snapshot: MonitorSnapshot = self._service.snapshot()
        except Exception as exc:  # keep the UI responsive even if sampling fails
            self.sampling_failed.emit(str(exc))
            return
        self.snapshot_ready.emit(snapshot)

    @Slot()
    def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._service.close()
        self.stopped.emit()
