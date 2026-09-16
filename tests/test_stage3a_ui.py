from __future__ import annotations

import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from net_monitor.core.models import (
    MonitorSnapshot,
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
    SystemNetworkStats,
)
from net_monitor.core.process_visibility import ProcessClassifier
import net_monitor.ui.controller as controller_module
from net_monitor.ui.compact_window import CompactWindow
from net_monitor.ui.controller import UiController
from net_monitor.ui.tray import TrayController


class FakeService:
    def __init__(self) -> None:
        self.closed = 0

    def snapshot(self) -> MonitorSnapshot:
        return make_snapshot()

    def close(self) -> None:
        self.closed += 1


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_snapshot(
    status: ProcessNetworkStatus = ProcessNetworkStatus.AVAILABLE,
    *,
    rates: tuple[tuple[str, float | None, float | None], ...] | None = None,
) -> MonitorSnapshot:
    rates = rates or (
        ("Chrome.exe", 900 * 1024.0, 10 * 1024.0),
        ("Steam.exe", 1024 * 1024.0, 1 * 1024.0),
        ("WeChat.exe", 80 * 1024.0, 18 * 1024.0),
        ("Idle.exe", 0.0, 0.0),
    )
    processes = tuple(
        ProcessInfo(
            100 + index,
            name,
            executable=fr"D:\Apps\{name}",
            create_time=float(index + 1),
        )
        for index, (name, _, _) in enumerate(rates)
    )
    stats = tuple(
        ProcessNetworkStats(
            process.pid,
            process.name,
            upload_bytes=None if upload is None else int(upload * 10),
            download_bytes=None if download is None else int(download * 10),
            upload_bytes_per_second=upload,
            download_bytes_per_second=download,
        )
        for process, (_, download, upload) in zip(processes, rates, strict=True)
    )
    message = "需要管理员权限" if status is ProcessNetworkStatus.PERMISSION_DENIED else None
    return MonitorSnapshot(
        system=SystemNetworkStats(0, 0, 0.0, 0.0),
        processes=processes,
        process_network=stats,
        process_network_state=ProcessNetworkState(status, message, 5 if message else None),
    )


def make_compact() -> CompactWindow:
    qapp()
    return CompactWindow(classifier=ProcessClassifier(windows_directory=r"C:\Windows"))


def visible_row_names(window: CompactWindow) -> list[str]:
    return [row._name.text() for row in window._rows if not row.isHidden()]


def test_compact_window_is_small_and_consumes_snapshot() -> None:
    window = make_compact()
    window.apply_snapshot(make_snapshot())
    assert window.width() < 600
    assert window.height() < 500
    assert window._status_label.text() == "运行中"
    assert window._active_count.text() == "3 个应用正在联网"
    assert window._restart_button.isHidden()
    window.close()


def test_compact_top_apps_use_raw_numeric_activity_order() -> None:
    window = make_compact()
    window.apply_snapshot(make_snapshot())
    assert visible_row_names(window)[:3] == ["Steam.exe", "Chrome.exe", "WeChat.exe"]
    window.close()


def test_compact_empty_state_for_no_current_network_activity() -> None:
    window = make_compact()
    snapshot = make_snapshot(rates=(("Idle.exe", 0.0, 0.0),))
    window.apply_snapshot(snapshot)
    assert window._empty_frame.isHidden() is False
    assert "当前没有第三方应用" in window._empty_label.text()
    assert visible_row_names(window) == []
    window.close()


def test_compact_permission_denied_is_not_rendered_as_zero() -> None:
    window = make_compact()
    snapshot = make_snapshot(
        ProcessNetworkStatus.PERMISSION_DENIED,
        rates=(("Browser.exe", None, None),),
    )
    window.apply_snapshot(snapshot)
    assert window._status_label.text() == "需要管理员权限"
    assert window._permission_frame.isHidden() is False
    assert window._restart_button.isHidden() is False
    assert window._download_value.text() == "—"
    assert window._upload_value.text() == "—"
    assert visible_row_names(window) == []
    window.close()


def test_compact_always_on_top_toggle_updates_state() -> None:
    window = make_compact()
    window.set_always_on_top(True)
    assert window.always_on_top is True
    window.set_always_on_top(False)
    assert window.always_on_top is False
    window.close()


def test_controller_reuses_one_detail_instance_and_one_service() -> None:
    app = qapp()
    service = FakeService()
    controller = UiController(service=service, start_worker=False)
    controller._on_snapshot(make_snapshot())

    first = controller.show_details()
    second = controller.show_details()
    assert first is second
    assert first._service is service
    assert controller.service is service
    assert controller.compact_window.latest_snapshot is controller.latest_snapshot
    assert first._latest_snapshot is controller.latest_snapshot

    first.close()
    app.processEvents()
    assert service.closed == 0
    controller.shutdown()
    controller.shutdown()
    assert service.closed == 1


def test_controller_default_service_uses_status_free_process_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qapp()
    collectors: list[object] = []
    network_collectors: list[object] = []
    services: list[dict[str, object]] = []

    class SpyProcessCollector:
        def __init__(self, *, include_status: bool) -> None:
            collectors.append(self)
            assert include_status is False

    class SpyNetworkCollector:
        def __init__(self, *, rate_window_seconds: float) -> None:
            network_collectors.append(self)
            assert rate_window_seconds == 2.0

    class SpyMonitorService(FakeService):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()
            services.append(kwargs)

    monkeypatch.setattr(controller_module, "ProcessCollector", SpyProcessCollector)
    monkeypatch.setattr(controller_module, "WindowsProcessNetworkCollector", SpyNetworkCollector)
    monkeypatch.setattr(controller_module, "MonitorService", SpyMonitorService)

    controller = UiController(start_worker=False)

    assert len(collectors) == 1
    assert len(network_collectors) == 1
    assert services == [
        {
            "process_collector": collectors[0],
            "process_network_collector": network_collectors[0],
        }
    ]
    assert controller.service is not None
    controller.shutdown()


def test_controller_explicit_service_does_not_create_process_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qapp()

    class RaisingProcessCollector:
        def __init__(self, *, include_status: bool) -> None:
            raise AssertionError("explicit services must be reused")

    class RaisingNetworkCollector:
        def __init__(self, *, rate_window_seconds: float) -> None:
            raise AssertionError("explicit services must be reused")

    monkeypatch.setattr(controller_module, "ProcessCollector", RaisingProcessCollector)
    monkeypatch.setattr(controller_module, "WindowsProcessNetworkCollector", RaisingNetworkCollector)
    service = FakeService()
    controller = UiController(service=service, start_worker=False)

    assert controller.service is service
    controller.shutdown()


def test_compact_and_detail_consume_same_snapshot_object() -> None:
    qapp()
    controller = UiController(service=FakeService(), start_worker=False)
    detail = controller.show_details()
    snapshot = make_snapshot()
    controller._on_snapshot(snapshot)
    assert controller.compact_window.latest_snapshot is snapshot
    assert detail._latest_snapshot is snapshot
    controller.shutdown()


def test_no_tray_compact_close_requests_full_shutdown() -> None:
    app = qapp()
    service = FakeService()
    controller = UiController(service=service, start_worker=False)
    controller.compact_window.set_tray_available(False)
    controller.compact_window.close()
    app.processEvents()
    assert service.closed == 1
    assert controller._shutdown_complete is True


def test_tray_controller_smoke_when_platform_has_no_tray() -> None:
    qapp()
    calls: list[str] = []
    tray = TrayController(
        show_compact=lambda: calls.append("show"),
        show_details=lambda: calls.append("details"),
        set_always_on_top=lambda enabled: calls.append(f"pin:{enabled}"),
        request_exit=lambda: calls.append("exit"),
    )
    assert tray.available is QSystemTrayIcon.isSystemTrayAvailable()
    tray.set_always_on_top_checked(True)
    tray.hide()


def test_real_system_tray_can_be_created_when_supported() -> None:
    qapp()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        pytest.skip("runner has no real system tray")
    tray = TrayController(
        show_compact=lambda: None,
        show_details=lambda: None,
        set_always_on_top=lambda enabled: None,
        request_exit=lambda: None,
    )
    assert tray.available is True
    tray.hide()


def test_gui_script_is_declared() -> None:
    data = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "[project.gui-scripts]" in data
    assert 'net-monitor = "net_monitor.app:main"' in data


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher subsystem check")
def test_installed_gui_launcher_uses_windows_gui_subsystem() -> None:
    launcher = Path(os.sys.executable).with_name("net-monitor.exe")
    assert launcher.exists(), "editable install must create the GUI launcher"
    data = launcher.read_bytes()
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    optional_header = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional_header)[0]
    assert magic in (0x10B, 0x20B)
    subsystem = struct.unpack_from("<H", data, optional_header + 68)[0]
    assert subsystem == 2, "net-monitor.exe must use IMAGE_SUBSYSTEM_WINDOWS_GUI"
