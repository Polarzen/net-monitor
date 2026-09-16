from __future__ import annotations

from collections.abc import Callable

import pytest

from net_monitor.collectors.etw.api import EtwPermissionError
from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent, ProcessNetworkTotals
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
    stop_error: Exception | None = None

    def __init__(self, on_event: Callable[[NetworkEvent], None]) -> None:
        self.on_event = on_event
        self.started = False
        self.stopped = False
        self.start_calls = 0
        self.stop_calls = 0
        self.stop_errors = [self.stop_error] if self.stop_error is not None else []
        self.health_error: Exception | None = None
        self.health_calls = 0
        FakeSession.instances.append(self)

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        self.started = True

    def stop(self, *, timeout: float = 5.0) -> None:
        self.stop_calls += 1
        if self.stop_errors:
            raise self.stop_errors.pop(0)
        self.stopped = True
        self.started = False

    def raise_if_failed(self) -> None:
        self.health_calls += 1
        if self.health_error is not None:
            raise self.health_error

    def emit(self, pid: int, direction: NetworkDirection, size: int) -> None:
        self.on_event(NetworkEvent(timestamp=0.0, pid=pid, direction=direction, size=size))


class SequenceAggregator:
    def __init__(self, values: list[tuple[int, int]]) -> None:
        self._values = iter(values)

    def snapshot(self) -> dict[int, ProcessNetworkTotals]:
        sent, received = next(self._values)
        return {10: ProcessNetworkTotals(pid=10, bytes_sent=sent, bytes_received=received)}

    def record(self, event: NetworkEvent) -> None:
        pass

    def retain_pids(self, pids: set[int]) -> None:
        pass


def setup_function() -> None:
    FakeSession.instances.clear()
    FakeSession.start_error = None
    FakeSession.stop_error = None


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


def test_windowed_rates_use_real_elapsed_time_and_hold_until_window_expires() -> None:
    collector = WindowsProcessNetworkCollector(
        session_factory=FakeSession,
        clock=FakeClock([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]),
        rate_window_seconds=2.0,
    )

    assert collector.collect((process(),))[0].upload_bytes_per_second == 0
    session = FakeSession.instances[0]
    session.emit(10, NetworkDirection.SEND, 100)
    rates = [collector.collect((process(),))[0].upload_bytes_per_second]
    session.emit(10, NetworkDirection.SEND, 100)
    rates.extend(collector.collect((process(),))[0].upload_bytes_per_second for _ in range(1))
    rates.append(collector.collect((process(),))[0].upload_bytes_per_second)
    session.emit(10, NetworkDirection.SEND, 100)
    rates.extend(
        collector.collect((process(),))[0].upload_bytes_per_second for _ in range(4)
    )
    rates.append(collector.collect((process(),))[0].upload_bytes_per_second)

    assert rates[:5] == pytest.approx([200.0, 200.0, 133.33333333333333, 150.0, 100.0])
    assert all(rate > 0 for rate in rates[:7])
    assert rates[-1] == 0


def test_windowed_rate_uses_jittered_sample_elapsed_time() -> None:
    collector = WindowsProcessNetworkCollector(
        session_factory=FakeSession,
        clock=FakeClock([10.0, 10.7]),
        rate_window_seconds=2.0,
    )
    collector.collect((process(),))
    FakeSession.instances[0].emit(10, NetworkDirection.SEND, 100)

    stats = collector.collect((process(),))[0]

    assert stats.upload_bytes == 100
    assert stats.upload_bytes_per_second == pytest.approx(100 / 0.7)


def test_windowed_rate_isolated_on_pid_reuse_and_counter_rollback() -> None:
    collector = WindowsProcessNetworkCollector(
        session_factory=FakeSession,
        clock=FakeClock([1.0, 2.0, 3.0, 4.0]),
        rate_window_seconds=2.0,
    )
    old = process(create_time=100.0)
    reused = process(create_time=200.0)
    collector.collect((old,))
    session = FakeSession.instances[0]
    session.emit(10, NetworkDirection.SEND, 100)
    assert collector.collect((old,))[0].upload_bytes == 100
    session.emit(10, NetworkDirection.SEND, 50)
    assert collector.collect((reused,))[0].upload_bytes == 0
    session.emit(10, NetworkDirection.SEND, 80)
    assert collector.collect((reused,))[0].upload_bytes == 80
    assert (10, 100.0) not in collector._states

    rollback = WindowsProcessNetworkCollector(
        aggregator=SequenceAggregator([(0, 0), (100, 200), (20, 300), (30, 350)]),
        session_factory=FakeSession,
        clock=FakeClock([1.0, 2.0, 3.0, 4.0]),
        rate_window_seconds=2.0,
    )
    assert rollback.collect((process(),))[0].upload_bytes_per_second == 0
    assert rollback.collect((process(),))[0].upload_bytes_per_second == 100
    reset = rollback.collect((process(),))[0]
    assert reset.upload_bytes == 20
    assert reset.download_bytes == 300
    assert reset.upload_bytes_per_second == 0
    assert reset.download_bytes_per_second == 0
    resumed = rollback.collect((process(),))[0]
    assert resumed.upload_bytes == 30
    assert resumed.download_bytes == 350
    assert resumed.upload_bytes_per_second == 10
    assert resumed.download_bytes_per_second == 50


def test_windowed_rate_reanchors_after_clock_rollback() -> None:
    collector = WindowsProcessNetworkCollector(
        aggregator=SequenceAggregator([(0, 0), (100, 0), (110, 0), (120, 0)]),
        session_factory=FakeSession,
        clock=FakeClock([100.0, 101.0, 10.0, 11.0]),
        rate_window_seconds=2.0,
    )

    assert collector.collect((process(),))[0].upload_bytes_per_second == 0
    assert collector.collect((process(),))[0].upload_bytes_per_second == 100
    assert collector.collect((process(),))[0].upload_bytes_per_second == 0
    assert collector.collect((process(),))[0].upload_bytes_per_second == 10


def test_window_rate_requires_finite_nonnegative_duration() -> None:
    for value in (-1.0, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            WindowsProcessNetworkCollector(rate_window_seconds=value)


def test_collector_reports_asynchronous_session_failure_before_snapshot() -> None:
    collector = WindowsProcessNetworkCollector(session_factory=FakeSession)
    collector.collect((process(),))
    session = FakeSession.instances[0]
    error = RuntimeError("consumer exploded")
    session.health_error = error

    result = collector.collect((process(),))[0]

    assert result.upload_bytes is None
    assert collector.state.status is ProcessNetworkStatus.UNAVAILABLE
    assert collector.available is False
    assert collector.last_error is error
    assert session.stopped is True
    assert session.health_calls == 2


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


def test_close_retains_failed_session_for_retry_while_staying_stopped() -> None:
    collector = WindowsProcessNetworkCollector(session_factory=FakeSession)
    collector.collect((process(),))
    session = FakeSession.instances[0]
    cleanup_error = RuntimeError("cleanup failed")
    session.stop_errors = [cleanup_error]

    collector.close()

    assert collector.state.status is ProcessNetworkStatus.STOPPED
    assert collector.available is False
    assert collector.last_error is cleanup_error
    assert session.stop_calls == 1
    assert collector._session is session

    collector.close()

    assert session.stop_calls == 2
    assert session.stopped is True
    assert collector._session is None
    assert collector.collect((process(),))[0].upload_bytes is None
    assert len(FakeSession.instances) == 1


def test_start_failure_retains_session_when_startup_cleanup_fails_until_close() -> None:
    start_error = RuntimeError("start failed")
    cleanup_error = RuntimeError("startup cleanup failed")
    FakeSession.start_error = start_error
    FakeSession.stop_error = cleanup_error
    collector = WindowsProcessNetworkCollector(session_factory=FakeSession)

    result = collector.collect((process(),))[0]
    session = FakeSession.instances[0]

    assert result.upload_bytes is None
    assert collector.state.status is ProcessNetworkStatus.UNAVAILABLE
    assert collector.last_error is start_error
    assert session.stop_calls == 1
    assert collector._session is session

    collector.close()

    assert session.stop_calls == 2
    assert session.stopped is True
    assert collector._session is None
    assert collector.state.status is ProcessNetworkStatus.STOPPED
    assert collector.collect((process(),))[0].upload_bytes is None
    assert len(FakeSession.instances) == 1
