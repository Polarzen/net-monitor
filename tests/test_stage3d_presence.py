from dataclasses import replace
from ctypes import wintypes

import pytest

from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import ProcessInfo, ProcessNetworkState, ProcessNetworkStatus
from net_monitor.ui.micro_model import (
    MicroProjection, PresenceContext, PresenceState, resolve_presence,
)
import net_monitor.ui.windows_foreground as windows_foreground
from test_stage3c_ui import app, make_controller, snapshot


@pytest.mark.parametrize(
    ("context", "pid", "expected"),
    [
        (PresenceContext("app", frozenset({101}), True), 101, PresenceState.FOREGROUND),
        (PresenceContext("app", frozenset({101}), True), 202, PresenceState.BACKGROUND),
        (PresenceContext("app", frozenset({101}), False), 202, PresenceState.UNKNOWN),
        (PresenceContext("app", frozenset({101}), False), 101, PresenceState.FOREGROUND),
        (PresenceContext("app", frozenset({101}), True), 0, PresenceState.UNKNOWN),
        (PresenceContext("app", frozenset({101}), True), None, PresenceState.UNKNOWN),
        (PresenceContext(None, frozenset(), False), 202, PresenceState.UNKNOWN),
    ],
)
def test_presence_rule_matrix(context, pid, expected):
    assert resolve_presence(context, pid) is expected


def test_presence_context_uses_cached_group_and_allows_trusted_partial_match():
    model = MicroProjection()
    data = snapshot()
    first = data.processes[0]
    second = replace(first, pid=first.pid + 1, create_time=None)
    model.receive(replace(data, processes=(first, second), process_network=(
        replace(data.process_network[0], pid=first.pid),
        replace(data.process_network[0], pid=second.pid),
    )))
    context = model.presence_context()
    assert context.selected_key == application_key(first)
    assert context.trusted_member_pids == frozenset({first.pid})
    assert not context.identity_complete
    assert context.member_identities == frozenset({first.identity, second.identity})
    assert resolve_presence(context, first.pid) is PresenceState.FOREGROUND
    assert resolve_presence(context, 9999) is PresenceState.UNKNOWN


def test_controller_injected_reader_queries_once_per_visible_refresh(make_controller):
    calls = []
    c = make_controller(foreground_pid_reader=lambda: calls.append(True) or 100)
    c.show_primary(activate=False)
    before = len(calls)
    assert len(calls) == before
    c._on_snapshot(snapshot())
    assert len(calls) == before
    c._heartbeat_refresh()
    assert len(calls) == before + 1
    assert c.projection.frame().presence is PresenceState.FOREGROUND
    before = len(calls)
    c._on_snapshot(snapshot())
    assert c.projection.frame().presence is PresenceState.FOREGROUND
    assert len(calls) == before
    c._refresh_views()
    assert len(calls) == before


def test_identity_change_invalidates_cached_presence_until_heartbeat(make_controller):
    calls = []
    c = make_controller(foreground_pid_reader=lambda: calls.append(True) or 100)
    data = snapshot()
    c._on_snapshot(data)
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    assert c.projection.frame().presence is PresenceState.FOREGROUND
    changed = replace(data.processes[0], create_time=999.0)
    c._on_snapshot(replace(data, processes=(changed, *data.processes[1:])))
    assert c.projection.frame().presence is PresenceState.UNKNOWN
    assert len(calls) == 1


def test_controller_reader_failure_is_unknown_and_does_not_change_collection(make_controller):
    c = make_controller(foreground_pid_reader=lambda: (_ for _ in ()).throw(OSError("no desktop")))
    data = snapshot()
    c.show_primary(activate=False)
    c._on_snapshot(data)
    c._heartbeat_refresh()
    assert c.projection.frame().presence is PresenceState.UNKNOWN
    assert c.latest_snapshot is data


def test_micro_presence_badge_states_and_layout_are_fixed(make_controller, app):
    current_pid = [100]
    c = make_controller(foreground_pid_reader=lambda: current_pid[0])
    data = snapshot()
    c._on_snapshot(data)
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    window = c.micro_window
    assert (window.width(), window.height()) == (220, 112)
    assert window.maximumSize().width() <= 240 and window.maximumSize().height() <= 140
    assert window.badge_label.text() == "前台"
    assert "当前有流量 · 自动显示" in window.state_label.text()
    assert window.name_label.toolTip() == data.processes[0].name
    assert window.name_label.text() != data.processes[0].name
    current_pid[0] = 999
    c._heartbeat_refresh()
    assert window.badge_label.text() == "后台"
    current_pid[0] = 0
    c._heartbeat_refresh()
    assert window.badge_label.text() == "状态未知"
    size = (window.width(), window.height())
    c._on_snapshot(snapshot())
    assert (window.width(), window.height()) == size


def test_micro_quiet_and_followed_idle_states(make_controller, app):
    c = make_controller(foreground_pid_reader=lambda: 103)
    idle = snapshot(idle=True)
    c._on_snapshot(idle)
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    assert c.micro_window.name_label.text() == "Net Monitor"
    assert "当前安静" in c.micro_window.state_label.text()
    assert "暂无明显网络活动" in c.micro_window.state_label.text()
    key = application_key(idle.processes[3])
    c.follow(key)
    assert c.micro_window.name_label.toolTip() == idle.processes[3].name
    assert "当前无流量 · 固定关注" in c.micro_window.state_label.text()
    assert c.micro_window.upload_label.text() == "↑ 上传 0 B/s"


def test_micro_unavailable_state_is_distinct_from_presence_unknown(make_controller):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    c.show_primary(activate=False)
    c._on_snapshot(replace(data, process_network_state=ProcessNetworkState(
        ProcessNetworkStatus.UNAVAILABLE)))
    assert "采集不可用 · 自动显示" in c.micro_window.state_label.text()


def test_frame_does_not_reaggregate_or_query_presence():
    model = MicroProjection()
    data = snapshot()
    model.receive(data)
    context = model.presence_context()
    model.set_presence_state(resolve_presence(context, data.processes[0].pid))
    first = model.frame()
    model.receive(data)
    second = model.frame()
    assert first == second
    changed = replace(data.processes[0], create_time=999.0)
    model.receive(replace(data, processes=(changed, *data.processes[1:])))
    assert model.frame().presence is PresenceState.UNKNOWN


class _FakeUser32:
    def __init__(self, hwnd=0, thread_id=0, pid=0, error=None):
        self.hwnd = hwnd
        self.thread_id = thread_id
        self.pid = pid
        self.error = error

    def GetForegroundWindow(self):
        if self.error is not None:
            raise self.error
        return self.hwnd

    def GetWindowThreadProcessId(self, _hwnd, output):
        output._obj.value = self.pid
        return self.thread_id


class _SignatureFunction:
    def __init__(self, callback):
        self.callback = callback
        self.restype = None
        self.argtypes = None

    def __call__(self, *args):
        return self.callback(*args)


@pytest.mark.parametrize(
    ("api", "expected"),
    [
        (_FakeUser32(hwnd=0), None),
        (_FakeUser32(hwnd=123, thread_id=0, pid=456), None),
        (_FakeUser32(hwnd=2**40, thread_id=99, pid=456), 456),
        (_FakeUser32(error=OSError("query failed")), None),
    ],
)
def test_win32_foreground_wrapper_is_conservative(monkeypatch, api, expected):
    monkeypatch.setattr(windows_foreground.os, "name", "nt")
    monkeypatch.setattr(windows_foreground.ctypes, "windll",
                        type("Windll", (), {"user32": api})(), raising=False)
    assert windows_foreground.read_foreground_pid() == expected


def test_win32_foreground_wrapper_sets_pointer_safe_signatures(monkeypatch):
    get_foreground = _SignatureFunction(lambda: 2**40)

    def get_pid(_hwnd, output):
        output._obj.value = 456
        return 99

    get_process = _SignatureFunction(get_pid)
    api = type("Windll", (), {"user32": type(
        "User32", (), {"GetForegroundWindow": get_foreground,
                        "GetWindowThreadProcessId": get_process})()})()
    monkeypatch.setattr(windows_foreground.os, "name", "nt")
    monkeypatch.setattr(windows_foreground.ctypes, "windll", api, raising=False)
    assert windows_foreground.read_foreground_pid() == 456
    assert get_foreground.restype is wintypes.HWND
    assert get_process.argtypes == (wintypes.HWND, windows_foreground.ctypes.POINTER(wintypes.DWORD))
    assert get_process.restype is wintypes.DWORD
