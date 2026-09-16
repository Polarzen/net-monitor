from __future__ import annotations

from collections.abc import Callable

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.collectors.etw.events import (
    NetworkDirection,
    NetworkEvent,
    ProcessNetworkTotals,
)
from net_monitor.collectors.etw.network import NetworkAggregator
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


def test_session_tracker_uses_directional_high_water_after_counter_rollback() -> None:
    tracker = ApplicationSessionTracker()
    process = app_process()

    snapshots = [
        tracker.update((process,), (stats(10, upload, download),))[0]
        for upload, download in ((150, 100), (120, 90), (130, 110), (170, 80))
    ]

    assert snapshots[-1].upload_bytes == 170
    assert snapshots[-1].download_bytes == 110

    second_tracker = ApplicationSessionTracker()
    second_process = app_process(pid=11, create_time=2.0)
    second_snapshots = [
        second_tracker.update((second_process,), (stats(11, upload, 0),))[0]
        for upload in (100, 0, 20, 101)
    ]
    assert second_snapshots[-1].upload_bytes == 101


def test_session_tracker_counts_unknown_ctime_as_active_for_existing_account() -> None:
    tracker = ApplicationSessionTracker()
    trusted = app_process()
    tracker.update((trusted,), (stats(10, 100, 200),))

    unknown = ProcessInfo(
        pid=trusted.pid,
        name=trusted.name,
        executable=trusted.executable,
        create_time=None,
    )
    groups = tracker.update((unknown,), ())

    assert len(groups) == 1
    assert groups[0].upload_bytes == 100
    assert groups[0].download_bytes == 200
    assert groups[0].active_process_count == 1


def test_session_tracker_skips_untrusted_or_mismatched_samples() -> None:
    tracker = ApplicationSessionTracker()
    unknown = ProcessInfo(pid=10, name="demo.exe", executable=r"D:\Apps\demo.exe")

    assert tracker.update((unknown,), (stats(10, 100, 200),)) == ()

    process = app_process()
    tracker.update((process,), (stats(10, 100, 200),))
    tracker.update(
        (process,),
        (
            ProcessNetworkStats(
                pid=999,
                name=process.name,
                upload_bytes=1_000,
                download_bytes=1_000,
            ),
        ),
    )
    result = tracker.update((process,), (stats(10, -5, -7),))[0]

    assert result.upload_bytes == 100
    assert result.download_bytes == 200


def test_session_tracker_skips_mismatched_retired_network_pid() -> None:
    tracker = ApplicationSessionTracker()
    process = app_process()
    tracker.update((process,), (stats(10, 150, 200),))

    mismatched = RetiredProcessNetworkStats(
        process=process,
        network=stats(999, 1_000, 1_000),
    )
    groups = tracker.update((), (), (mismatched,))

    assert len(groups) == 1
    assert groups[0].upload_bytes == 150
    assert groups[0].download_bytes == 200


def test_session_tracker_skips_unknown_ctime_retired_sample() -> None:
    tracker = ApplicationSessionTracker()
    unknown = ProcessInfo(
        pid=10,
        name="demo.exe",
        executable=r"D:\Apps\demo.exe",
        create_time=None,
    )
    retired = RetiredProcessNetworkStats(
        process=unknown,
        network=stats(10, 100, 200),
    )

    assert tracker.update((), (), (retired,)) == ()


def test_session_tracker_applies_high_water_to_repeated_retired_samples() -> None:
    tracker = ApplicationSessionTracker()
    process = app_process()
    tracker.update((process,), (stats(10, 150, 150),))

    groups = ()
    for value in (120, 130, 170, 170):
        retired = RetiredProcessNetworkStats(
            process=process,
            network=stats(10, value, value),
        )
        groups = tracker.update((), (), (retired,))

    assert len(groups) == 1
    assert groups[0].upload_bytes == 170
    assert groups[0].download_bytes == 170


def test_session_tracker_keeps_metadata_recovery_in_one_account() -> None:
    tracker = ApplicationSessionTracker()
    missing = ProcessInfo(pid=30, name="demo.exe", create_time=3.0)
    restored = ProcessInfo(
        pid=30,
        name="demo.exe",
        executable=r"D:\Apps\demo.exe",
        create_time=3.0,
    )

    tracker.update((missing,), (stats(30, 100, 200),))
    tracker.update((restored,), (stats(30, 150, 260),))
    tracker.update((missing,), (stats(30, 140, 250),))
    groups = tracker.update((restored,), (stats(30, 160, 270),))

    assert len(groups) == 1
    assert groups[0].upload_bytes == 160
    assert groups[0].download_bytes == 270
    assert groups[0].executable is None


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


def test_pid_reuse_baselines_against_mixed_bucket_at_atomic_cut() -> None:
    sessions: list[FakeSession] = []

    def factory(callback: Callable[[NetworkEvent], None]) -> FakeSession:
        session = FakeSession(callback)
        sessions.append(session)
        return session

    aggregator = NetworkAggregator()
    collector = WindowsProcessNetworkCollector(
        aggregator=aggregator,
        session_factory=factory,
        clock=FakeClock([1.0, 2.0, 3.0, 4.0]),
    )
    old = app_process(create_time=1.0)
    new = app_process(create_time=2.0)

    collector.collect((old,))
    sessions[0].emit(10, NetworkDirection.SEND, 100)
    collector.collect((old,))
    aggregator.record(NetworkEvent(0.0, 10, NetworkDirection.SEND, 50))

    first_new = collector.collect((new,))[0]
    retired = collector.drain_retired()
    assert first_new.upload_bytes == 0
    assert retired[0].network.upload_bytes == 100

    sessions[0].emit(10, NetworkDirection.SEND, 80)
    second_new = collector.collect((new,))[0]
    assert second_new.upload_bytes == 80


def test_collector_atomically_hands_off_totals_at_retirement_cut() -> None:
    sessions: list[FakeSession] = []

    def factory(callback: Callable[[NetworkEvent], None]) -> FakeSession:
        session = FakeSession(callback)
        sessions.append(session)
        return session

    class InjectingAggregator(NetworkAggregator):
        inject_after_snapshot = False

        def snapshot(self) -> dict[int, ProcessNetworkTotals]:
            result = super().snapshot()
            if self.inject_after_snapshot:
                self.inject_after_snapshot = False
                self.record(NetworkEvent(0.0, 10, NetworkDirection.SEND, 50))
            return result

    aggregator = InjectingAggregator()
    collector = WindowsProcessNetworkCollector(
        aggregator=aggregator,
        session_factory=factory,
        clock=FakeClock([1.0, 2.0, 3.0, 4.0]),
    )
    process = app_process()

    collector.collect((process,))
    sessions[0].emit(10, NetworkDirection.SEND, 100)
    collector.collect((process,))
    aggregator.inject_after_snapshot = True
    collector.collect(())

    retired = collector.drain_retired()
    assert len(retired) == 1
    assert retired[0].network.upload_bytes == 150
    assert collector.drain_retired() == ()


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
        # MonitorService samples the system clock once before process refresh
        # and again after counter collection for the system rate timestamp.
        clock=FakeClock([1.0, 1.5, 2.0, 2.5]),
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
