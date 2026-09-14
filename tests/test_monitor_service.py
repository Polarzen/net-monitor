from __future__ import annotations

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.core.models import NetworkCounters, ProcessInfo, ProcessNetworkStats
from net_monitor.services.monitor_service import MonitorService


class FakeProcessCollector:
    def collect(self) -> tuple[ProcessInfo, ...]:
        return (ProcessInfo(pid=1, name="demo.exe"),)


class FakeSystemCollector:
    def __init__(self, samples: list[NetworkCounters]) -> None:
        self._samples = iter(samples)

    def collect(self) -> NetworkCounters:
        return next(self._samples)


class FakeProcessNetworkCollector(ProcessNetworkCollector):
    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        return tuple(ProcessNetworkStats(pid=p.pid, name=p.name) for p in processes)


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


def make_service(samples: list[NetworkCounters], times: list[float]) -> MonitorService:
    return MonitorService(
        process_collector=FakeProcessCollector(),
        system_network_collector=FakeSystemCollector(samples),
        process_network_collector=FakeProcessNetworkCollector(),
        clock=FakeClock(times),
    )


def test_first_sample_has_zero_rates() -> None:
    service = make_service([NetworkCounters(100, 200)], [10.0])
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0
    assert len(snapshot.processes) == 1


def test_second_sample_uses_real_elapsed_time() -> None:
    service = make_service(
        [NetworkCounters(100, 200), NetworkCounters(300, 700)],
        [10.0, 12.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 100
    assert snapshot.system.download_bytes_per_second == 250


def test_counter_rollback_never_creates_negative_rate() -> None:
    service = make_service(
        [NetworkCounters(500, 900), NetworkCounters(100, 200)],
        [1.0, 2.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0


def test_zero_elapsed_time_has_zero_rates() -> None:
    service = make_service(
        [NetworkCounters(100, 200), NetworkCounters(300, 600)],
        [5.0, 5.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0


def test_no_network_change_has_zero_rates() -> None:
    service = make_service(
        [NetworkCounters(100, 200), NetworkCounters(100, 200)],
        [1.0, 3.0],
    )
    service.snapshot()
    snapshot = service.snapshot()
    assert snapshot.system.upload_bytes_per_second == 0
    assert snapshot.system.download_bytes_per_second == 0
