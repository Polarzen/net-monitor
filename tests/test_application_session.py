from __future__ import annotations

from collections.abc import Callable

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.application_session import ApplicationSessionTracker
from net_monitor.core.models import (
    NetworkCounters,
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
    RetiredProcessNetworkStats,
)
from net_monitor.services.monitor_service import MonitorService


def app_process(
    pid: int = 10,
    *,
    create_time: float = 1.0,
    executable: str = r"D:\Apps\demo.exe",
) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name="demo.exe",
        executable=executable,
        create_time=create_time,
    )


def stats(pid: int, upload: int, download: int) -> ProcessNetworkStats:
    return ProcessNetworkStats(
        pid=pid,
        name="demo.exe",
        upload_bytes=upload,
        download_bytes=download,
        upload_bytes_per_second=0.0,
        download_bytes_per_second=0.0,
    )


def test_session_tracker_counts_cumulative_deltas_only_once() -> None:
    tracker = ApplicationSessionTracker()
    process = app_process()

    first = tracker.update((process,), (stats(10, 100, 200),))[0]
    second = tracker.update((process,), (stats(10, 150, 260),))[0]
    repeated = tracker.update((process,), (stats(10, 150, 260),))[0]

    assert first.upload_bytes == 100
    assert first.download_bytes == 200
    assert second.upload_bytes == 150
    assert second.download_bytes == 260
    assert repeated.upload_bytes == 150
    assert repeated.download_bytes == 260
    assert repeated.active_process_count == 1


def test_session_tracker_keeps_retired_bytes_and_combines_later_same_app() -> None:
    tracker = ApplicationSessionTracker()
    first_process = app_process(create_time=1.0)

    tracker.update((first_process,), (stats(10, 100, 200),))
    retired = RetiredProcessNetworkStats(
        process=first_process,
        network=stats(10, 125, 240),
    )
    after_exit = tracker.update((), (), (retired,))[0]

    assert after_exit.upload_bytes == 125
    assert after_exit.download_bytes == 240
    assert after_exit.active_process_count == 0

    second_process = app_process(pid=20, create_time=2.0)
    restarted = tracker.update((second_process,), (stats(20, 30, 40),))[0]

    assert restarted.upload_bytes == 155
    assert restarted.download_bytes == 280
    assert restarted.active_process_count == 1


def test_session_tracker_keeps_same_pid_lifetimes_separate() -> None:
    tracker = ApplicationSessionTracker()
    old = app_process(pid=10, create_time=1.0, executable=r"D:\Apps\old.exe")
    new = app_process(pid=10, create_time=2.0, executable=r"D:\Apps\new.exe")

    tracker.update((old,), (stats(10, 100, 200),))
    groups = tracker.update((new,), (stats(10, 25, 50),))

    by_name = {group.name: group for group in groups}
    assert by_name["old.exe"].upload_bytes == 100
    assert by_name["old.exe"].active_process_count == 0
    assert by_name["new.exe"].upload_bytes == 25
    assert by_name["new.exe"].active_process_count == 1


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class FakeSession:
    def __init__(self, on_event: Callable[[NetworkEvent], None]) -> None:
        self.on_event = on_event

    def start(self) -> None:
        return None

    def stop(self, *, timeout: float = 5.0) -> None:
        return None

    def raise_if_failed(self) -> None:
        return None

    def emit(self, pid: int, direction: NetworkDirection, size: int) -> None:
        self.on_event(NetworkEvent(timestamp=0.0, pid=pid, direction=direction, size=size))


def test_collector_captures_final_counter_when_process_retires() -> None:
    sessions: list[FakeSession] = []

    def factory(callback: Callable[[NetworkEvent], None]) -> FakeSession:
        session = FakeSession(callback)
        sessions.append(session)
        return session

    collector = WindowsProcessNetworkCollector(
        session_factory=factory,
        clock=FakeClock([1.0, 2.0, 3.0]),
    )
    process = app_process()

    collector.collect((process,))
    sessions[0].emit(10, NetworkDirection.SEND, 100)
    sessions[0].emit(10, NetworkDirection.RECEIVE, 200)
    collector.collect((process,))
    sessions[0].emit(10, NetworkDirection.SEND, 50)
    sessions[0].emit(10, NetworkDirection.RECEIVE, 75)

    collector.collect(())
    retired = collector.drain_retired()

    assert len(retired) == 1
    assert retired[0].process.identity == process.identity
    assert retired[0].network.upload_bytes == 150
    assert retired[0].network.download_bytes == 275
    assert collector.drain_retired() == ()


def test_collector_does_not_charge_reused_pid_bytes_to_old_identity() -> None:
    sessions: list[FakeSession] = []

    def factory(callback: Callable[[NetworkEvent], None]) -> FakeSession:
        session = FakeSession(callback)
        sessions.append(session)
        return session

    collector = WindowsProcessNetworkCollector(
        session_factory=factory,
        clock=FakeClock([1.0, 2.0, 3.0]),
    )
    old = app_process(create_time=1.0)
    new = app_process(create_time=2.0)

    collector.collect((old,))
    sessions[0].emit(10, NetworkDirection.SEND, 100)
    collector.collect((old,))
    sessions[0].emit(10, NetworkDirection.SEND, 50)

    new_first = collector.collect((new,))[0]
    retired = collector.drain_retired()

    assert new_first.upload_bytes == 0
    assert len(retired) == 1
    assert retired[0].process.identity == old.identity
    assert retired[0].network.upload_bytes == 100


class SequenceProcessCollector:
    def __init__(self, samples: list[tuple[ProcessInfo, ...]]) -> None:
        self._samples = iter(samples)

    def collect(self) -> tuple[ProcessInfo, ...]:
        return next(self._samples)


class SequenceSystemCollector:
    def __init__(self, samples: list[NetworkCounters]) -> None:
        self._samples = iter(samples)

    def collect(self) -> NetworkCounters:
        return next(self._samples)


class RetiringNetworkCollector(ProcessNetworkCollector):
    def __init__(self, process: ProcessInfo) -> None:
        self._process = process
        self._calls = 0
        self._retired: tuple[RetiredProcessNetworkStats, ...] = ()
        self._state = ProcessNetworkState(ProcessNetworkStatus.AVAILABLE)

    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        self._calls += 1
        if self._calls == 1:
            return (stats(self._process.pid, 100, 200),)
        self._retired = (
            RetiredProcessNetworkStats(
                process=self._process,
                network=stats(self._process.pid, 125, 250),
            ),
        )
        return ()

    def drain_retired(self) -> tuple[RetiredProcessNetworkStats, ...]:
        result = self._retired
        self._retired = ()
        return result

    @property
    def state(self) -> ProcessNetworkState:
        return self._state


def test_monitor_service_exposes_session_totals_after_process_exit() -> None:
    process = app_process()
    service = MonitorService(
        process_collector=SequenceProcessCollector([(process,), ()]),
        system_network_collector=SequenceSystemCollector(
            [NetworkCounters(0, 0), NetworkCounters(0, 0)]
        ),
        process_network_collector=RetiringNetworkCollector(process),
        clock=FakeClock([1.0, 2.0]),
        process_refresh_interval=0.0,
    )

    first = service.snapshot()
    second = service.snapshot()

    assert first.application_session[0].upload_bytes == 100
    assert first.application_session[0].active_process_count == 1
    assert second.processes == ()
    assert second.application_session[0].upload_bytes == 125
    assert second.application_session[0].download_bytes == 250
    assert second.application_session[0].active_process_count == 0
