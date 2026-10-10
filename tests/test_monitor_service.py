from __future__ import annotations

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.core.models import (
    NetworkCounters,
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
)
from net_monitor.services.monitor_service import MonitorService


class FakeProcessCollector:
    def __init__(self) -> None:
        self.calls = 0

    def collect(self) -> tuple[ProcessInfo, ...]:
        self.calls += 1
        return (ProcessInfo(pid=1, name="demo.exe"),)


class FakeSystemCollector:
    def __init__(self, samples: list[NetworkCounters]) -> None:
        self._samples = iter(samples)

    def collect(self) -> NetworkCounters:
        return next(self._samples)


class FakeProcessNetworkCollector(ProcessNetworkCollector):
    def __init__(self, state: ProcessNetworkState | None = None) -> None:
        self._state = state or ProcessNetworkState(ProcessNetworkStatus.AVAILABLE)

    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        return tuple(ProcessNetworkStats(pid=p.pid, name=p.name) for p in processes)

    @property
    def state(self) -> ProcessNetworkState:
        return self._state


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class MutableClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class AdvancingProcessCollector(FakeProcessCollector):
    def __init__(self, clock: MutableClock, durations: list[float]) -> None:
        super().__init__()
        self._clock = clock
        self._durations = iter(durations)

    def collect(self) -> tuple[ProcessInfo, ...]:
        processes = super().collect()
        self._clock.advance(next(self._durations))
        return processes


class ConstantRateSystemCollector:
    def __init__(self, clock: MutableClock, upload_rate: int, download_rate: int) -> None:
        self._clock = clock
        self._upload_rate = upload_rate
        self._download_rate = download_rate

    def collect(self) -> NetworkCounters:
        return NetworkCounters(
            int(self._clock.value * self._upload_rate),
            int(self._clock.value * self._download_rate),
        )


def make_service(
    samples: list[NetworkCounters],
    times: list[float],
    process_network_collector: ProcessNetworkCollector | None = None,
    *,
    process_collector: FakeProcessCollector | None = None,
    process_refresh_interval: float = 2.0,
) -> MonitorService:
    return MonitorService(
        process_collector=process_collector or FakeProcessCollector(),
        system_network_collector=FakeSystemCollector(samples),
        process_network_collector=process_network_collector or FakeProcessNetworkCollector(),
        clock=FakeClock(times),
        process_refresh_interval=process_refresh_interval,
    )


def test_first_sample_has_zero_rates() -> None:
    service = make_service([NetworkCounters(100, 200)], [10.0, 10.0])
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0
    assert len(snapshot.processes) == 1


def test_snapshot_exposes_process_network_state() -> None:
    state = ProcessNetworkState(
        ProcessNetworkStatus.PERMISSION_DENIED,
        "需要管理员权限",
        5,
    )
    service = make_service(
        [NetworkCounters(100, 200)],
        [10.0, 10.0],
        FakeProcessNetworkCollector(state),
    )
    snapshot = service.snapshot()
    assert snapshot.process_network_state == state


def test_second_sample_uses_real_elapsed_time() -> None:
    service = make_service(
        [NetworkCounters(100, 200), NetworkCounters(300, 700)],
        [10.0, 10.0, 12.0, 12.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 100
    assert snapshot.system.download_bytes_per_second == 250


def test_counter_rollback_never_creates_negative_rate() -> None:
    service = make_service(
        [NetworkCounters(500, 900), NetworkCounters(100, 200)],
        [1.0, 1.0, 2.0, 2.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0


def test_zero_elapsed_time_has_zero_rates() -> None:
    service = make_service(
        [NetworkCounters(100, 200), NetworkCounters(300, 600)],
        [5.0, 5.0, 5.0, 5.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0


def test_no_network_change_has_zero_rates() -> None:
    service = make_service(
        [NetworkCounters(100, 200), NetworkCounters(100, 200)],
        [1.0, 1.0, 3.0, 3.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0


def test_process_enumeration_is_cached_between_fast_network_snapshots() -> None:
    process_collector = FakeProcessCollector()
    service = make_service(
        [NetworkCounters(1, 1), NetworkCounters(2, 2), NetworkCounters(3, 3)],
        [10.0, 10.0, 10.5, 10.5, 12.1, 12.1],
        process_collector=process_collector,
    )

    service.snapshot()
    first_metrics = service.last_performance
    service.snapshot()
    cached_metrics = service.last_performance
    service.snapshot()
    refreshed_metrics = service.last_performance

    assert process_collector.calls == 2
    assert first_metrics.process_enumeration_seconds is not None
    assert cached_metrics.process_enumeration_seconds is None
    assert refreshed_metrics.process_enumeration_seconds is not None
    assert refreshed_metrics.process_count == 1


def test_system_rate_uses_time_after_process_enumeration() -> None:
    clock = MutableClock()
    service = MonitorService(
        process_collector=AdvancingProcessCollector(clock, [3.0, 1.0]),
        system_network_collector=ConstantRateSystemCollector(clock, 100, 200),
        process_network_collector=FakeProcessNetworkCollector(),
        clock=clock,
    )

    service.snapshot()
    snapshot = service.snapshot()

    assert snapshot.system.upload_bytes_per_second == 100
    assert snapshot.system.download_bytes_per_second == 200
