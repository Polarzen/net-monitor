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
        ProcessInfo(pid=1, name="idle.exe"),
        ProcessInfo(pid=2, name="busy.exe"),
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
    window = MainWindow(service=service)
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
    assert denied._download_label.text() == "第三方应用总下载速度: —"
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
        processes=(ProcessInfo(1, "small.exe"), ProcessInfo(2, "large.exe")),
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


def test_system_processes_and_system_traffic_are_excluded_from_app_view() -> None:
    snapshot = MonitorSnapshot(
        system=SystemNetworkStats(999999, 999999, 999999.0, 999999.0),
        processes=(
            ProcessInfo(100, "svchost.exe", executable=r"C:\Windows\System32\svchost.exe"),
            ProcessInfo(200, "browser.exe", executable=r"C:\Program Files\Browser\browser.exe"),
        ),
        process_network=(
            ProcessNetworkStats(100, "svchost.exe", 9000, 8000, 7000.0, 6000.0),
            ProcessNetworkStats(200, "browser.exe", 5000, 4000, 3000.0, 2000.0),
        ),
        process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
    )
    app, window, _ = make_window(snapshot)

    assert window._table.rowCount() == 1
    assert window._table.item(0, 0).text() == "browser.exe"
    assert window._process_count_label.text() == "第三方进程数: 1"
    assert window._upload_label.text() == "第三方应用总上传速度: 2.93 KB/s"
    assert window._download_label.text() == "第三方应用总下载速度: 1.95 KB/s"

    window.close()
    app.processEvents()
