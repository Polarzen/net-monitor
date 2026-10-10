from types import SimpleNamespace

import psutil
import pytest

from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent
from net_monitor.collectors.etw.network import NetworkAggregator
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.models import NetworkCounters, ProcessInfo
from net_monitor.services.monitor_service import MonitorService


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


class Session:
    def __init__(self, callback):
        pass

    def start(self):
        pass

    def stop(self, **kwargs):
        pass

    def raise_if_failed(self):
        pass


class Processes:
    def __init__(self):
        self.current = ProcessInfo(10, "old.exe", r"D:\Apps\old.exe", create_time=1.0)
        self.calls = 0
        self.error = None
        self.identity_queries = 0

    def collect(self):
        self.calls += 1
        return (self.current,)

    def query(self, pid):
        self.identity_queries += 1
        if self.error is not None:
            raise self.error
        assert pid == self.current.pid
        return SimpleNamespace(create_time=lambda: self.current.create_time)


def totals(snapshot):
    return {row.name: row.upload_bytes for row in snapshot.application_session}


def setup_monitor(monkeypatch, *, window=0.0, aggregator=None):
    clock = Clock()
    processes = Processes()
    monkeypatch.setattr(psutil, "Process", processes.query)
    aggregator = aggregator or NetworkAggregator()
    collector = WindowsProcessNetworkCollector(
        aggregator=aggregator, session_factory=Session, clock=clock,
        rate_window_seconds=window,
    )
    service = MonitorService(
        process_collector=processes,
        system_network_collector=SimpleNamespace(collect=lambda: NetworkCounters(0, 0)),
        process_network_collector=collector, clock=clock, process_refresh_interval=2.0,
    )
    service.snapshot()
    clock.value = 0.5
    aggregator.record(NetworkEvent(0.5, 10, NetworkDirection.SEND, 100))
    assert totals(service.snapshot()) == {"old.exe": 100}
    return service, collector, aggregator, processes, clock


@pytest.mark.parametrize("window", [0.0, 2.0])
def test_cached_pid_reuse_never_charges_new_bytes_to_old_application(monkeypatch, window):
    service, collector, aggregator, processes, clock = setup_monitor(monkeypatch, window=window)
    processes.current = ProcessInfo(10, "new.exe", r"D:\Apps\new.exe", create_time=2.0)
    clock.value = 1.0
    aggregator.record(NetworkEvent(1.0, 10, NetworkDirection.SEND, 50))
    stale = service.snapshot()
    assert processes.calls == 1  # Preserve the two-second full-enumeration interval.
    assert totals(stale) == {"old.exe": 100}
    assert stale.process_network[0].upload_bytes is None
    assert stale.process_network[0].upload_bytes_per_second is None
    clock.value = 2.1
    assert totals(service.snapshot()) == {"old.exe": 100, "new.exe": 0}
    aggregator.record(NetworkEvent(2.5, 10, NetworkDirection.SEND, 80))
    clock.value = 2.6
    assert totals(service.snapshot()) == {"old.exe": 100, "new.exe": 80}
    assert processes.calls == 2
    assert (10, 1.0) not in collector._states
    service.close()


def test_identity_is_checked_after_network_snapshot(monkeypatch):
    service, collector, aggregator, processes, clock = setup_monitor(monkeypatch)
    original_snapshot = aggregator.snapshot

    def reuse_during_snapshot():
        processes.current = ProcessInfo(10, "new.exe", create_time=2.0)
        aggregator.record(NetworkEvent(1.0, 10, NetworkDirection.SEND, 50))
        return original_snapshot()

    monkeypatch.setattr(aggregator, "snapshot", reuse_during_snapshot)
    clock.value = 1.0
    assert totals(service.snapshot()) == {"old.exe": 100}
    service.close()


def test_retirement_cut_cannot_charge_reused_pid_tail_to_old_identity(monkeypatch):
    service, collector, aggregator, processes, clock = setup_monitor(monkeypatch)
    original_retain = aggregator.retain_pids

    def reuse_at_retirement_cut(pids):
        processes.current = ProcessInfo(10, "new.exe", create_time=2.0)
        aggregator.record(NetworkEvent(1.0, 10, NetworkDirection.SEND, 50))
        return original_retain(pids)

    monkeypatch.setattr(aggregator, "retain_pids", reuse_at_retirement_cut)
    clock.value = 1.0
    collector.collect(())
    retired = collector.drain_retired()
    assert len(retired) == 1
    assert retired[0].network.upload_bytes == 100
    service.close()


@pytest.mark.parametrize("error_type", [psutil.AccessDenied, psutil.NoSuchProcess])
@pytest.mark.parametrize("window", [0.0, 2.0])
def test_uncertain_identity_preserves_confirmed_totals_and_resumes_without_guessing(
    monkeypatch, error_type, window
):
    service, collector, aggregator, processes, clock = setup_monitor(monkeypatch, window=window)
    processes.error = error_type(10)
    clock.value = 1.0
    aggregator.record(NetworkEvent(1.0, 10, NetworkDirection.SEND, 50))
    unknown = service.snapshot()
    assert unknown.process_network[0].upload_bytes is None
    assert totals(unknown) == {"old.exe": 100}
    processes.error = None
    clock.value = 1.5
    resumed = service.snapshot()
    assert totals(resumed) == {"old.exe": 100}  # Uncertain interval is not retroactively assigned.
    assert resumed.process_network[0].upload_bytes_per_second == 0
    clock.value = 2.1
    aggregator.record(NetworkEvent(2.1, 10, NetworkDirection.SEND, 80))
    assert totals(service.snapshot()) == {"old.exe": 180}
    service.close()


def test_unverified_retirement_preserves_last_confirmed_totals(monkeypatch):
    service, collector, aggregator, processes, clock = setup_monitor(monkeypatch)
    processes.error = psutil.NoSuchProcess(10)
    aggregator.record(NetworkEvent(1.0, 10, NetworkDirection.SEND, 50))
    clock.value = 1.0
    collector.collect(())
    assert collector.drain_retired()[0].network.upload_bytes == 100
    service.close()


def test_unknown_creation_time_does_not_produce_confirmed_zero(monkeypatch):
    monkeypatch.setattr(psutil, "Process", lambda pid: pytest.fail("Unknown identity must not be guessed"))
    collector = WindowsProcessNetworkCollector(session_factory=Session)
    result = collector.collect((ProcessInfo(10, "unknown.exe"),))[0]
    assert result.upload_bytes is None
    assert result.download_bytes_per_second is None
    collector.close()
