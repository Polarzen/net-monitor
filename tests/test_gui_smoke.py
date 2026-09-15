from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
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


class FakeService:
    def __init__(self, snapshot: MonitorSnapshot) -> None:
        self._snapshot = snapshot
        self.closed = False

    def snapshot(self) -> MonitorSnapshot:
        return self._snapshot

    def close(self) -> None:
        self.closed = True


def make_snapshot(
    status: ProcessNetworkStatus = ProcessNetworkStatus.AVAILABLE,
    stats: tuple[ProcessNetworkStats, ...] | None = None,
) -> MonitorSnapshot:
    processes = (
        ProcessInfo(pid=1, name="idle.exe", executable=r"C:\Program Files\Idle\idle.exe", create_time=1.0),
        ProcessInfo(pid=2, name="busy.exe", executable=r"D:\Apps\Busy\busy.exe", create_time=2.0),
    )
    if stats is None:
        stats = (
            ProcessNetworkStats(1, "idle.exe", 0, 0, 0.0, 0.0),
            ProcessNetworkStats(2, "busy.exe", 2048, 1024, 4096.0, 512.0),
        )
    message = None
    error_code = None
    if status is ProcessNetworkStatus.PERMISSION_DENIED:
        message = "需要以管理员身份运行 Net Monitor 才能获取每个进程的网络流量。"
        error_code = 5
    elif status is ProcessNetworkStatus.UNAVAILABLE:
        message = "进程网络监控当前不可用。"
    return MonitorSnapshot(
        system=SystemNetworkStats(100, 200, 10.0, 20.0),
        processes=processes,
        process_network=stats,
        process_network_state=ProcessNetworkState(status, message, error_code),
    )


def make_window(snapshot: MonitorSnapshot) -> tuple[QApplication, MainWindow, FakeService]:
    app = QApplication.instance() or QApplication([])
    service = FakeService(snapshot)
    window = MainWindow(
        service=service,
        start_worker=False,
        classifier=ProcessClassifier(windows_directory=r"C:\Windows"),
    )
    window._on_snapshot(snapshot)
    return app, window, service


def test_main_window_can_be_created_and_shutdown_closes_service() -> None:
    app, window, service = make_window(make_snapshot())
    assert window.windowTitle() == "Net Monitor"
    assert window.centralWidget() is not None
    window.close()
    app.processEvents()
    assert service.closed is True


def test_available_state_and_real_zero_are_distinct_from_unavailable() -> None:
    app, window, _ = make_window(make_snapshot(ProcessNetworkStatus.AVAILABLE))
    assert window._network_status_label.text() == "进程网络监控：运行中"
    assert window._table.item(0, 2).text() == "0 B/s"
    assert window._table.item(0, 3).text() == "0 B/s"
    window.close()
    app.processEvents()


def test_permission_denied_and_unavailable_status_text() -> None:
    app, denied, _ = make_window(
        make_snapshot(
            ProcessNetworkStatus.PERMISSION_DENIED,
            (
                ProcessNetworkStats(1, "idle.exe"),
                ProcessNetworkStats(2, "busy.exe"),
            ),
        )
    )
    assert denied._network_status_label.text() == "进程网络监控：不可用（需要管理员权限）"
    assert denied._network_status_label.toolTip().startswith("需要以管理员身份运行")
    assert denied._table.item(0, 2).text() == "—"
    assert denied._upload_label.text() == "第三方应用总上传速度: —"
    denied.close()
    app.processEvents()

    app, unavailable, _ = make_window(
        make_snapshot(
            ProcessNetworkStatus.UNAVAILABLE,
            (
                ProcessNetworkStats(1, "idle.exe"),
                ProcessNetworkStats(2, "busy.exe"),
            ),
        )
    )
    assert unavailable._network_status_label.text() == "进程网络监控：不可用"
    unavailable.close()
    app.processEvents()


def test_network_activity_filter_uses_session_totals() -> None:
    app, window, _ = make_window(make_snapshot())
    assert window._table.rowCount() == 2

    window._network_activity_only.setChecked(True)
    app.processEvents()

    assert window._table.rowCount() == 1
    assert window._table.item(0, 0).text() == "busy.exe"
    window.close()
    app.processEvents()


def test_network_columns_sort_by_raw_numeric_values() -> None:
    stats = (
        ProcessNetworkStats(1, "small.exe", 900 * 1024, 0, 900 * 1024.0, 0.0),
        ProcessNetworkStats(2, "large.exe", 1024 * 1024, 0, 1024 * 1024.0, 0.0),
    )
    snapshot = MonitorSnapshot(
        system=SystemNetworkStats(0, 0, 0.0, 0.0),
        processes=(
            ProcessInfo(1, "small.exe", executable=r"D:\Apps\small.exe", create_time=1.0),
            ProcessInfo(2, "large.exe", executable=r"D:\Apps\large.exe", create_time=2.0),
        ),
        process_network=stats,
        process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
    )
    app, window, _ = make_window(snapshot)

    window._table.sortItems(3, Qt.SortOrder.DescendingOrder)
    app.processEvents()

    assert window._table.item(0, 0).text() == "large.exe"
    assert window._table.item(0, 3).data(Qt.ItemDataRole.UserRole) == 1024 * 1024.0
    window.close()
    app.processEvents()


def test_system_hidden_by_default_unknown_visible_and_toggle_restores_system() -> None:
    snapshot = MonitorSnapshot(
        system=SystemNetworkStats(999999, 999999, 999999.0, 999999.0),
        processes=(
            ProcessInfo(100, "svchost.exe", executable=r"C:\Windows\System32\svchost.exe", create_time=1.0),
            ProcessInfo(200, "browser.exe", executable=r"C:\Program Files\Browser\browser.exe", create_time=2.0),
            ProcessInfo(300, "mystery.exe", executable=None, create_time=3.0),
        ),
        process_network=(
            ProcessNetworkStats(100, "svchost.exe", 9000, 8000, 7000.0, 6000.0),
            ProcessNetworkStats(200, "browser.exe", 5000, 4000, 3000.0, 2000.0),
            ProcessNetworkStats(300, "mystery.exe", 1000, 500, 100.0, 50.0),
        ),
        process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
    )
    app, window, _ = make_window(snapshot)

    assert window._table.rowCount() == 2
    assert {window._table.item(row, 0).text() for row in range(2)} == {"browser.exe", "mystery.exe"}
    assert window._upload_label.text() == "第三方应用总上传速度: 3.03 KB/s"

    window._show_system_processes.setChecked(True)
    app.processEvents()
    assert window._table.rowCount() == 3
    assert {window._table.item(row, 0).text() for row in range(3)} == {
        "svchost.exe",
        "browser.exe",
        "mystery.exe",
    }
    window.close()
    app.processEvents()


def test_filters_combine_and_incremental_update_preserves_existing_items() -> None:
    app, window, _ = make_window(make_snapshot())
    busy_name_item = next(
        window._table.item(row, 0)
        for row in range(window._table.rowCount())
        if window._table.item(row, 0).text() == "busy.exe"
    )

    base = make_snapshot()
    updated = MonitorSnapshot(
        system=SystemNetworkStats(200, 300, 20.0, 30.0),
        processes=base.processes,
        process_network=(
            ProcessNetworkStats(1, "idle.exe", 0, 0, 0.0, 0.0),
            ProcessNetworkStats(2, "busy.exe", 4096, 2048, 8192.0, 1024.0),
        ),
        process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
    )
    window._on_snapshot(updated)
    same_busy_item = next(
        window._table.item(row, 0)
        for row in range(window._table.rowCount())
        if window._table.item(row, 0).text() == "busy.exe"
    )
    assert same_busy_item is busy_name_item

    window._network_activity_only.setChecked(True)
    window._show_system_processes.setChecked(False)
    app.processEvents()
    assert window._table.rowCount() == 1
    assert window._table.item(0, 0).text() == "busy.exe"
    window.close()
    app.processEvents()


def test_large_snapshot_is_applied_without_losing_rows() -> None:
    processes = tuple(
        ProcessInfo(index, f"app-{index}.exe", executable=fr"D:\Apps\app-{index}.exe", create_time=float(index))
        for index in range(10, 310)
    )
    stats = tuple(
        ProcessNetworkStats(index, f"app-{index}.exe", index, index, float(index), float(index))
        for index in range(10, 310)
    )
    snapshot = MonitorSnapshot(
        system=SystemNetworkStats(0, 0, 0.0, 0.0),
        processes=processes,
        process_network=stats,
        process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
    )
    app, window, _ = make_window(snapshot)
    assert window._table.rowCount() == 300
    assert window.last_visible_rows == 300
    assert window.last_apply_seconds >= 0.0
    window.close()
    app.processEvents()
