from __future__ import annotations

import psutil

from net_monitor.core.models import NetworkCounters


class SystemNetworkCollector:
    def collect(self) -> NetworkCounters:
        counters = psutil.net_io_counters()
        if counters is None:
            return NetworkCounters(bytes_sent=0, bytes_received=0)
        return NetworkCounters(
            bytes_sent=max(0, int(counters.bytes_sent)),
            bytes_received=max(0, int(counters.bytes_recv)),
        )
