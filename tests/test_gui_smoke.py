from __future__ import annotations

import os
from collections.abc import Callable

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


def make_window(
    snapshot: MonitorSnapshot,
    *,
    elevation_launcher: Callable[[], bool] | None = None,
) -> tuple[QApplication, MainWindow, FakeService]:
    app = QApplication.instance() or QApplication([])
    service = FakeService(snapshot)
    window = MainWindow(
        service=service,
        start_worker=False,
        classifier=ProcessClassifier(windows_directory=r"C:\Windows"),
        elevation_launcher=elevation_launcher,
    )
    window._on_snapshot(snapshot)
    return app, window, service


def top_level_items(window: MainWindow):
    return [window._tree.topLevelItem(index) for index in range(window._tree.topLevelItemCount())]


def top_level_names(window: MainWindow) -> set[str]:
    return {item.text(0) for item in top_level_items(window)}


def find_top_level(window: MainWindow, name: str):
    return next(item for item in top_level_items(window) if item.text(0) == name)


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
    assert window._restart_as_admin_button.isHidden() is True

    window._network_activity_only.setChecked(False)
    app.processEvents()
    idle = find_top_level(window, "idle.exe")
    assert idle.text(2) == "0 B/s"
    assert idle.text(3) == "0 B/s"
    window.close()
    app.processEvents()


def test_permission_denied_exposes_explicit_elevation_action() -> None:
    launches: list[bool] = []

    def launch() -> bool:
        launches.append(True)
        return False

    app, denied, _ = make_window(
        make_snapshot(
            ProcessNetworkStatus.PERMISSION_DENIED,
            (
                ProcessNetworkStats(1, "idle.exe"),
                ProcessNetworkStats(2, "busy.exe"),
            ),
        ),
        elevation_launcher=launch,
    )
    assert denied._network_status_label.text() == "进程网络监控：不可用（需要管理员权限）"
    assert denied._network_status_label.toolTip().startswith("需要以管理员身份运行")
    assert find_top_level(denied, "idle.exe").text(2) == "—"
    assert denied._upload_label.text() == "第三方应用总上传速度: —"
    assert denied._network_activity_only.isEnabled() is False
    assert denied._restart_as_admin_button.isHidden() is False

    denied._restart_as_admin_button.click()
    app.processEvents()
    assert launches == [True]
    assert denied._restart_as_admin_button.isEnabled() is True
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
    assert unavailable._restart_as_admin_button.isHidden() is True
    unavailable.close()
    app.processEvents()


def test_current_network_activity_filter_is_enabled_by_default() -> None:
    app, window, _ = make_window(make_snapshot())
    assert window._network_activity_only.isChecked() is True
    assert window._tree.topLevelItemCount() == 1
    assert window._tree.topLevelItem(0).text(0) == "busy.exe"

    totals_without_current_rate = make_snapshot(
        stats=(
            ProcessNetworkStats(1, "idle.exe", 0, 0, 0.0, 0.0),
            ProcessNetworkStats(2, "busy.exe", 2048, 1024, 0.0, 0.0),
        )
    )
    window._on_snapshot(totals_without_current_rate)
    assert window._tree.topLevelItemCount() == 0

    window._network_activity_only.setChecked(False)
    app.processEvents()
    assert window._tree.topLevelItemCount() == 2
    window.close()
    app.processEvents()


def test_network_columns_sort_by_raw_aggregate_numeric_values() -> None:
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

    window._tree.sortItems(3, Qt.SortOrder.DescendingOrder)
    app.processEvents()

    assert window._tree.topLevelItem(0).text(0) == "large.exe"
    assert window._tree.topLevelItem(0).data(3, Qt.ItemDataRole.UserRole) == 1024 * 1024.0
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

    assert window._tree.topLevelItemCount() == 2
    assert top_level_names(window) == {"browser.exe", "mystery.exe"}
    assert window._upload_label.text() == "第三方应用总上传速度: 3.03 KB/s"

    window._show_system_processes.setChecked(True)
    app.processEvents()
    assert window._tree.topLevelItemCount() == 3
    assert top_level_names(window) == {"svchost.exe", "browser.exe", "mystery.exe"}
    window.close()
    app.processEvents()


def test_filters_combine_and_incremental_update_preserves_existing_group_item() -> None:
    app, window, _ = make_window(make_snapshot())
    busy_item = find_top_level(window, "busy.exe")

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
    assert find_top_level(window, "busy.exe") is busy_item

    window._network_activity_only.setChecked(True)
    window._show_system_processes.setChecked(False)
    app.processEvents()
    assert window._tree.topLevelItemCount() == 1
    assert window._tree.topLevelItem(0).text(0) == "busy.exe"
    window.close()
    app.processEvents()


def test_same_executable_processes_are_one_expandable_application() -> None:
    processes = (
        ProcessInfo(10, "chrome.exe", executable=r"C:\Program Files\Google\Chrome\chrome.exe", create_time=1.0),
        ProcessInfo(20, "chrome.exe", executable=r"C:\Program Files\Google\Chrome\chrome.exe", create_time=2.0),
    )
    snapshot = MonitorSnapshot(
        system=SystemNetworkStats(0, 0, 0.0, 0.0),
        processes=processes,
        process_network=(
            ProcessNetworkStats(10, "chrome.exe", 1000, 2000, 100.0, 200.0),
            ProcessNetworkStats(20, "chrome.exe", 3000, 4000, 300.0, 400.0),
        ),
        process_network_state=ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
    )
    app, window, _ = make_window(snapshot)

    assert window._tree.topLevelItemCount() == 1
    chrome = window._tree.topLevelItem(0)
    assert chrome.text(0) == "chrome.exe"
    assert chrome.text(1) == "2"
    assert chrome.data(3, Qt.ItemDataRole.UserRole) == 400.0
    assert chrome.data(2, Qt.ItemDataRole.UserRole) == 600.0
    assert chrome.data(5, Qt.ItemDataRole.UserRole) == 4000
    assert chrome.data(4, Qt.ItemDataRole.UserRole) == 6000
    assert chrome.childCount() == 2
    assert {chrome.child(index).text(1) for index in range(chrome.childCount())} == {"10", "20"}

    chrome.setExpanded(True)
    updated = MonitorSnapshot(
        system=snapshot.system,
        processes=processes,
        process_network=(
            ProcessNetworkStats(10, "chrome.exe", 2000, 3000, 200.0, 300.0),
            ProcessNetworkStats(20, "chrome.exe", 4000, 5000, 400.0, 500.0),
        ),
        process_network_state=snapshot.process_network_state,
    )
    window._on_snapshot(updated)
    same_chrome = window._tree.topLevelItem(0)
    assert same_chrome is chrome
    assert same_chrome.isExpanded() is True
    assert same_chrome.data(3, Qt.ItemDataRole.UserRole) == 600.0
    window.close()
    app.processEvents()


def test_large_snapshot_is_aggregated_without_losing_active_applications() -> None:
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
    assert window._tree.topLevelItemCount() == 300
    assert window.last_visible_rows == 300
    assert window.last_apply_seconds >= 0.0
    window.close()
    app.processEvents()
