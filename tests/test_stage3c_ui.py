from __future__ import annotations

from dataclasses import replace
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import net_monitor.ui.controller as module
from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import (
    ApplicationSessionStats, MonitorSnapshot, ProcessInfo, ProcessNetworkState,
    ProcessNetworkStats, ProcessNetworkStatus, SystemNetworkStats,
)
from net_monitor.ui.controller import UiController
from net_monitor.ui.micro_model import DisplayState, MICRO_SIZE
from net_monitor.ui.micro_window import KeyButton
from net_monitor.ui.preferences import PreferencesStore


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now


def snapshot(*, status=ProcessNetworkStatus.AVAILABLE, idle=False):
    processes = tuple(ProcessInfo(100 + i, name, rf"D:\Apps\{name}", create_time=float(i + 1))
                      for i, name in enumerate(("中文应用名称很长需要省略.exe", "b.exe", "c.exe", "idle.exe")))
    rows = tuple(ProcessNetworkStats(p.pid, p.name, 10 + i, 20 + i,
                                    0.0 if idle or i == 3 else 1024.0 * (4 - i),
                                    0.0 if idle or i == 3 else 900.0 * (4 - i))
                 for i, p in enumerate(processes))
    accounts = tuple(ApplicationSessionStats(application_key(p), p.name, p.executable,
                                            10 + i, 20 + i, 1) for i, p in enumerate(processes))
    return MonitorSnapshot(SystemNetworkStats(0, 0, 0, 0), processes, rows,
                           ProcessNetworkState(status), accounts)


class Service:
    def __init__(self):
        self.closed = 0
        self.thread_ids = []
    def snapshot(self):
        self.thread_ids.append(threading.get_ident())
        return snapshot()
    def close(self):
        self.closed += 1


class Tray:
    def __init__(self, **callbacks):
        self.available = False
        self.callbacks = callbacks
        self.checked = False
    def set_always_on_top_checked(self, enabled):
        self.checked = enabled
    def hide(self):
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_controller(app, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "TrayController", Tray)
    controllers = []
    def make(**kwargs):
        service = kwargs.pop("service", Service())
        clock = kwargs.pop("clock", Clock())
        controller = UiController(service=service, start_worker=kwargs.pop("start_worker", False),
                                  clock=clock, preferences_store=PreferencesStore(tmp_path / f"{len(controllers)}.json"),
                                  icon_reader=lambda path: None, **kwargs)
        controllers.append(controller)
        return controller
    yield make
    for controller in controllers:
        controller.shutdown()
    app.processEvents()


def test_micro_default_fixed_dimensions_name_elision_and_plain_text(make_controller, app):
    c = make_controller()
    c.show_primary(activate=False)
    c._on_snapshot(snapshot())
    app.processEvents()
    window = c.micro_window
    assert c.mode == "micro"
    assert (window.width(), window.height()) == MICRO_SIZE
    assert not c.compact_window.isVisible()
    assert window.name_label.text() != snapshot().processes[0].name
    assert window.name_label.toolTip() == snapshot().processes[0].name
    assert window.download_label.text().startswith("↓ ")
    assert window.upload_label.text().startswith("↑ ")
    assert "KiB/s" in window.upload_label.text()
    for label in (window.name_label, window.upload_label, window.download_label):
        assert window.rect().contains(label.geometry())
    c._on_snapshot(snapshot(idle=True))
    assert (window.width(), window.height()) == MICRO_SIZE
    assert window.upload_label.text() == "↑ 上传 0 B/s"


def test_preview_and_updates_do_not_activate_windows(make_controller, monkeypatch):
    c = make_controller()
    activations = []
    monkeypatch.setattr(c.card, "activateWindow", lambda: activations.append("card"))
    monkeypatch.setattr(c.micro_window, "activateWindow", lambda: activations.append("micro"))
    c.show_primary(activate=False)
    c._on_snapshot(snapshot())
    c.show_card(interactive=False)
    c._refresh_views()
    assert activations == []
    assert c.card.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert c.micro_window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    c.show_card(interactive=True)
    assert activations == ["card"]


def test_card_and_detail_singletons_and_timers_do_not_multiply(make_controller):
    c = make_controller()
    c._on_snapshot(snapshot())
    timers = tuple(c.findChildren(QTimer))
    card = c.show_card(interactive=True)
    detail = c.show_details()
    for _ in range(12):
        c.collapse_card()
        assert c.show_card() is card
        detail.close()
        assert c.show_details() is detail
    assert tuple(c.findChildren(QTimer)) == timers
    assert len(timers) == 3
    assert c.service.closed == 0
    assert detail._sampling_thread is None
    assert detail._service is c.service


def test_modes_and_tray_restore_keep_focus_and_snapshot(make_controller):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    key = application_key(data.processes[3])
    c.follow(key)
    for mode in ("compact", "micro", "compact", "micro"):
        c.set_mode(mode)
        assert c.latest_snapshot is data
        assert c.projection.frame().selected.key == key
        assert c.projection.frame().account is data.application_session[3]
        assert c.primary_window.isVisible()
        assert not (c.micro_window.isVisible() and c.compact_window.isVisible())
    c.tray.available = True
    c._close_primary()
    assert not c.primary_window.isVisible()
    c.tray.callbacks["show_compact"]()
    assert c.micro_window.isVisible()
    assert c.service.closed == 0


def test_topmost_never_changes_detail_flags(make_controller):
    c = make_controller()
    detail = c.show_details()
    c.set_always_on_top(True)
    assert c.micro_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not detail.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    c.set_always_on_top(False)
    assert not c.micro_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_stale_and_failure_mask_legacy_rates_without_modifying_snapshot(make_controller):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    detail = c.show_details()
    c.show_card()
    c.projection.clock.now = 4.0
    c._refresh_views()
    assert c.projection.frame().state is DisplayState.STALE
    assert c.compact_window._upload_value.text() == "—"
    assert detail._upload_label.text().endswith("—")
    assert "数据更新已停止" in c.card.state_label.text()
    assert c.latest_snapshot is data
    assert data.process_network[0].upload_bytes_per_second > 0
    c._on_snapshot(data)
    c.sampling_failed.emit("failure")
    assert c.projection.frame().state is DisplayState.FAILED
    assert c.compact_window._status_label.text() == "采样失败"
    assert c.projection.frame().account is data.application_session[0]


def test_hidden_card_does_not_apply_frames_or_request_icons(make_controller, monkeypatch):
    c = make_controller()
    calls = []
    monkeypatch.setattr(c.card, "apply_frame", lambda frame: calls.append(frame))
    monkeypatch.setattr(c._icons, "request", lambda *args: calls.append(args))
    c._on_snapshot(snapshot())
    c._refresh_views()
    assert calls == []


def test_hover_delay_union_region_and_escape(make_controller, monkeypatch, app):
    c = make_controller()
    c.show_primary(activate=False)
    monkeypatch.setattr(c.micro_window, "underMouse", lambda: True)
    c._enter_micro()
    assert c._hover_timer.interval() == 350 and c._hover_timer.isActive()
    assert not c.card.isVisible()
    c._hover_preview()
    assert c.card.isVisible()
    assert not c._card_persistent
    monkeypatch.setattr(QCursor, "pos", lambda: c.card.frameGeometry().center())
    c._collapse_if_outside()
    assert c.card.isVisible()
    monkeypatch.setattr(QCursor, "pos", lambda: QPoint(-1_000_000, -1_000_000))
    c._collapse_if_outside()
    assert not c.card.isVisible()
    c.show_card(interactive=True)
    c.card.escape.activated.emit()
    assert not c.card.isVisible()


def test_click_and_drag_have_different_signals(make_controller, app):
    c = make_controller()
    window = c.micro_window
    window.show()
    app.processEvents()
    calls = []
    window.clicked.connect(lambda: calls.append("click"))
    window.drag_finished.connect(lambda: calls.append("drag"))
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert calls == ["click"]
    c.collapse_card()
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    local = QPoint(10 + QApplication.startDragDistance() + 5, 10)
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(local), QPointF(window.mapToGlobal(local)),
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, event)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
    assert calls == ["click", "drag"]
    assert not c.card.isVisible()


def test_key_button_press_is_not_rebound_by_refresh(app):
    button = KeyButton()
    keys = []
    button.key_activated.connect(keys.append)
    button.bind("A", "A")
    button.show()
    QTest.mousePress(button, Qt.MouseButton.LeftButton)
    button.bind("B", "B")
    QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
    assert keys == ["A"]
    button.bind("B", "B")
    button.click()
    assert keys == ["A", "B"]
    button.close()


@pytest.mark.parametrize("raises", [False, True])
def test_uac_cancel_or_failure_keeps_instance(make_controller, raises):
    def launch():
        if raises:
            raise OSError("UAC failed")
        return False
    c = make_controller(elevation_launcher=launch)
    c._on_snapshot(snapshot(status=ProcessNetworkStatus.PERMISSION_DENIED))
    c.show_card(interactive=True)
    assert c.card.restart_button.isVisible()
    c.card.restart_button.click()
    assert not c._shutdown_complete
    assert c.service.closed == 0
    assert c.card.restart_button.isEnabled()


def test_no_tray_exit_and_shutdown_idempotent(make_controller, monkeypatch):
    c = make_controller()
    calls = []
    monkeypatch.setattr(QApplication, "quit", lambda: calls.append("quit"))
    c.micro_window.close()
    assert c.service.closed == 1
    assert calls == ["quit"]
    c.shutdown()
    c.start()
    assert c.service.closed == 1
    assert c._thread is None
    assert c.icon_worker_stopped
    assert not any(timer.isActive() for timer in c.findChildren(QTimer))


def test_single_worker_remains_same_across_mode_changes(make_controller, app):
    service = Service()
    c = make_controller(service=service, start_worker=True, sampling_interval_ms=50)
    thread, worker = c._thread, c._worker
    deadline = time.monotonic() + 2
    while not service.thread_ids and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    assert service.thread_ids
    assert all(ident != threading.get_ident() for ident in service.thread_ids)
    c.show_compact()
    c.show_micro()
    c.show_details().close()
    c.start()
    assert c._thread is thread and c._worker is worker
    c.shutdown()
    assert not thread.isRunning()
    assert service.closed == 1
