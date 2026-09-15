from __future__ import annotations

from collections.abc import Callable

from net_monitor.collectors.etw.api import EtwPermissionError
from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.models import ProcessInfo, ProcessNetworkStatus


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class FakeSession:
    instances: list["FakeSession"] = []
    start_error: Exception | None = None

    def __init__(self, on_event: Callable[[NetworkEvent], None]) -> None:
        self.on_event = on_event
        self.started = False
        self.stopped = False
        self.start_calls = 0
        FakeSession.instances.append(self)

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        self.started = True

    def stop(self, *, timeout: float = 5.0) -> None:
        self.stopped = True
        self.started = False

    def emit(self, pid: int, direction: NetworkDirection, size: int) -> None:
        self.on_event(NetworkEvent(timestamp=0.0, pid=pid, direction=direction, size=size))


def setup_function() -> None:
    FakeSession.instances.clear()
    FakeSession.start_error = None


def process(pid: int = 10, create_time: float | None = 100.0) -> ProcessInfo:
    return ProcessInfo(pid=pid, name="demo.exe", create_time=create_time)


def test_collector_starts_in_starting_state() -> None:
    collector = WindowsProcessNetworkCollector(session_factory=FakeSession)
    assert collector.state.status is ProcessNetworkStatus.STARTING
    assert collector.available is False


def test_collector_starts_lazily_and_computes_rates() -> None:
    collector = WindowsProcessNetworkCollector(
        session_factory=FakeSession,
        clock=FakeClock([1.0, 3.0]),
    )

    first = collector.collect((process(),))[0]
    session = FakeSession.instances[0]
    assert session.started is True
    assert collector.state.status is ProcessNetworkStatus.AVAILABLE
    assert collector.available is True
    assert first.upload_bytes == 0
    assert first.download_bytes == 0
    assert first.upload_bytes_per_second == 0
    assert first.download_bytes_per_second == 0

    session.emit(10, NetworkDirection.SEND, 200)
    session.emit(10, NetworkDirection.RECEIVE, 600)
    second = collector.collect((process(),))[0]

    assert second.upload_bytes == 200
    assert second.download_bytes == 600
    assert second.upload_bytes_per_second == 100
    assert second.download_bytes_per_second == 300


def test_new_process_identity_resets_baseline_for_reused_pid() -> None:
    collector = WindowsProcessNetworkCollector(
        session_factory=FakeSession,
        clock=FakeClock([1.0, 2.0, 3.0, 4.0]),
    )

    collector.collect((process(create_time=100.0),))
    session = FakeSession.instances[0]
    session.emit(10, NetworkDirection.SEND, 100)
    old_stats = collector.collect((process(create_time=100.0),))[0]
    assert old_stats.upload_bytes == 100

    session.emit(10, NetworkDirection.SEND, 50)
    reused_first = collector.collect((process(create_time=200.0),))[0]
    assert reused_first.upload_bytes == 0
    assert reused_first.upload_bytes_per_second == 0

    session.emit(10, NetworkDirection.SEND, 80)
    reused_second = collector.collect((process(create_time=200.0),))[0]
    assert reused_second.upload_bytes == 80
    assert reused_second.upload_bytes_per_second == 80


def test_etw_access_denied_maps_to_permission_denied_without_retrying() -> None:
    FakeSession.start_error = EtwPermissionError("StartTraceW", 5)
    collector = WindowsProcessNetworkCollector(session_factory=FakeSession)

    first = collector.collect((process(),))[0]
    second = collector.collect((process(),))[0]

    assert first.upload_bytes is None
    assert first.download_bytes_per_second is None
    assert second.upload_bytes is None
    assert len(FakeSession.instances) == 1
    assert FakeSession.instances[0].start_calls == 1
    assert collector.state.status is ProcessNetworkStatus.PERMISSION_DENIED
    assert collector.state.error_code == 5
    assert collector.available is False


def test_other_session_start_failure_maps_to_unavailable() -> None:
    FakeSession.start_error = RuntimeError("ETW failed")
    collector = WindowsProcessNetworkCollector(session_factory=FakeSession)

    result = collector.collect((process(),))[0]

    assert result.upload_bytes is None
    assert collector.state.status is ProcessNetworkStatus.UNAVAILABLE
    assert collector.available is False
    assert isinstance(collector.last_error, RuntimeError)


def test_session_factory_failure_maps_to_unavailable() -> None:
    def failing_factory(on_event: Callable[[NetworkEvent], None]) -> FakeSession:
        raise RuntimeError("factory failed")

    collector = WindowsProcessNetworkCollector(session_factory=failing_factory)
    result = collector.collect((process(),))[0]

    assert result.download_bytes is None
    assert collector.state.status is ProcessNetworkStatus.UNAVAILABLE


def test_close_stops_session_is_idempotent_and_sets_stopped_state() -> None:
    collector = WindowsProcessNetworkCollector(
        session_factory=FakeSession,
        clock=FakeClock([1.0]),
    )
    collector.collect((process(),))
    session = FakeSession.instances[0]

    collector.close()
    collector.close()

    assert session.stopped is True
    assert collector.available is False
    assert collector.state.status is ProcessNetworkStatus.STOPPED
    unavailable = collector.collect((process(),))[0]
    assert unavailable.upload_bytes is None
