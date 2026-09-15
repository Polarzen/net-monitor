from __future__ import annotations

import time
from collections.abc import Callable

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.collectors.process import ProcessCollector
from net_monitor.collectors.system_network import SystemNetworkCollector
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.models import MonitorSnapshot, NetworkCounters, SystemNetworkStats


class MonitorService:
    def __init__(
        self,
        process_collector: ProcessCollector | None = None,
        system_network_collector: SystemNetworkCollector | None = None,
        process_network_collector: ProcessNetworkCollector | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._process_collector = process_collector or ProcessCollector()
        self._system_network_collector = system_network_collector or SystemNetworkCollector()
        self._process_network_collector = process_network_collector or WindowsProcessNetworkCollector()
        self._clock = clock
        self._previous_counters: NetworkCounters | None = None
        self._previous_time: float | None = None

    def snapshot(self) -> MonitorSnapshot:
        processes = self._process_collector.collect()
        counters = self._system_network_collector.collect()
        now = self._clock()
        system = self._build_system_stats(counters, now)
        process_network = self._process_network_collector.collect(processes)
        return MonitorSnapshot(system=system, processes=processes, process_network=process_network)

    def close(self) -> None:
        close = getattr(self._process_network_collector, "close", None)
        if callable(close):
            close()

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
