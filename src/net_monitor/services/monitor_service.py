from __future__ import annotations

import time
from collections.abc import Callable

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.collectors.process import ProcessCollector
from net_monitor.collectors.system_network import SystemNetworkCollector
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.application_session import ApplicationSessionTracker
from net_monitor.core.models import (
    MonitorSnapshot,
    NetworkCounters,
    ProcessInfo,
    RetiredProcessNetworkStats,
    SnapshotPerformance,
    SystemNetworkStats,
)


class MonitorService:
    def __init__(
        self,
        process_collector: ProcessCollector | None = None,
        system_network_collector: SystemNetworkCollector | None = None,
        process_network_collector: ProcessNetworkCollector | None = None,
        clock: Callable[[], float] = time.monotonic,
        *,
        process_refresh_interval: float = 2.0,
        perf_clock: Callable[[], float] = time.perf_counter,
        application_session_tracker: ApplicationSessionTracker | None = None,
    ) -> None:
        self._process_collector = process_collector or ProcessCollector()
        self._system_network_collector = system_network_collector or SystemNetworkCollector()
        self._process_network_collector = process_network_collector or WindowsProcessNetworkCollector()
        self._clock = clock
        self._perf_clock = perf_clock
        self._process_refresh_interval = max(0.0, process_refresh_interval)
        self._application_session_tracker = (
            application_session_tracker or ApplicationSessionTracker()
        )
        self._previous_counters: NetworkCounters | None = None
        self._previous_time: float | None = None
        self._processes: tuple[ProcessInfo, ...] = ()
        self._last_process_refresh: float | None = None
        self._last_performance = SnapshotPerformance(0.0, None, 0)

    def snapshot(self) -> MonitorSnapshot:
        started = self._perf_clock()
        now = self._clock()
        enumeration_seconds: float | None = None

        if self._should_refresh_processes(now):
            enumeration_started = self._perf_clock()
            self._processes = self._process_collector.collect()
            enumeration_seconds = self._perf_clock() - enumeration_started
            self._last_process_refresh = now

        counters = self._system_network_collector.collect()
        system = self._build_system_stats(counters, now)
        process_network = self._process_network_collector.collect(self._processes)
        retired = self._drain_retired_process_network()
        application_session = self._application_session_tracker.update(
            self._processes,
            process_network,
            retired,
        )
        snapshot = MonitorSnapshot(
            system=system,
            processes=self._processes,
            process_network=process_network,
            process_network_state=self._process_network_collector.state,
            application_session=application_session,
        )
        self._last_performance = SnapshotPerformance(
            total_seconds=self._perf_clock() - started,
            process_enumeration_seconds=enumeration_seconds,
            process_count=len(self._processes),
        )
        return snapshot

    @property
    def last_performance(self) -> SnapshotPerformance:
        return self._last_performance

    def close(self) -> None:
        close = getattr(self._process_network_collector, "close", None)
        if callable(close):
            close()

    def _drain_retired_process_network(self) -> tuple[RetiredProcessNetworkStats, ...]:
        drain = getattr(self._process_network_collector, "drain_retired", None)
        if not callable(drain):
            return ()
        retired = drain()
        return tuple(retired)

    def _should_refresh_processes(self, now: float) -> bool:
        if self._last_process_refresh is None:
            return True
        return now - self._last_process_refresh >= self._process_refresh_interval

    def _build_system_stats(self, counters: NetworkCounters, now: float) -> SystemNetworkStats:
        upload_rate = 0.0
        download_rate = 0.0
        if self._previous_counters is not None and self._previous_time is not None:
            elapsed = now - self._previous_time
            if elapsed > 0:
                upload_delta = max(0, counters.bytes_sent - self._previous_counters.bytes_sent)
                download_delta = max(0, counters.bytes_received - self._previous_counters.bytes_received)
                upload_rate = upload_delta / elapsed
                download_rate = download_delta / elapsed

        self._previous_counters = counters
        self._previous_time = now
        return SystemNetworkStats(
            bytes_sent=counters.bytes_sent,
            bytes_received=counters.bytes_received,
            upload_bytes_per_second=upload_rate,
            download_bytes_per_second=download_rate,
        )
