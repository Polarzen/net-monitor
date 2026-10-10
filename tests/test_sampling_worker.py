from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from net_monitor.core.models import (
    MonitorSnapshot,
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
    SystemNetworkStats,
)
from net_monitor.core.process_visibility import ProcessClassifier
from net_monitor.ui.main_window import MainWindow


class ThreadRecordingService:
    def __init__(self) -> None:
        self.snapshot_thread_ids: list[int] = []
        self.closed = False

    def snapshot(self) -> MonitorSnapshot:
        self.snapshot_thread_ids.append(threading.get_ident())
        process = ProcessInfo(42, "demo.exe", executable=r"D:\Apps\demo.exe", create_time=1.0)
        return MonitorSnapshot(
            system=SystemNetworkStats(0, 0, 0.0, 0.0),
            processes=(process,),
            process_network=(ProcessNetworkStats(42, "demo.exe", 1, 1, 1.0, 1.0),),
            process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
        )

    def close(self) -> None:
        self.closed = True


def test_main_window_samples_off_ui_thread_and_stops_worker_cleanly() -> None:
    app = QApplication.instance() or QApplication([])
    service = ThreadRecordingService()
    main_thread_id = threading.get_ident()
    window = MainWindow(
        service=service,  # type: ignore[arg-type]
        sampling_interval_ms=100,
        classifier=ProcessClassifier(windows_directory=r"C:\Windows"),
    )

    deadline = time.monotonic() + 2.0
    while not service.snapshot_thread_ids and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert service.snapshot_thread_ids
    assert all(thread_id != main_thread_id for thread_id in service.snapshot_thread_ids)
    assert window._tree.topLevelItemCount() == 1
    assert window._tree.topLevelItem(0).text(0) == "demo.exe"

    thread = window._sampling_thread
    window.close()
    app.processEvents()

    assert service.closed is True
    assert thread is not None
    assert not thread.isRunning()


def test_shutdown_is_idempotent_without_worker() -> None:
    app = QApplication.instance() or QApplication([])
    service = ThreadRecordingService()
    window = MainWindow(
        service=service,  # type: ignore[arg-type]
        start_worker=False,
        classifier=ProcessClassifier(windows_directory=r"C:\Windows"),
    )
    window.shutdown()
    window.shutdown()
    assert service.closed is True
    window.close()
    app.processEvents()
