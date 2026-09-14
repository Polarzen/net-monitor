from __future__ import annotations

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.core.models import ProcessInfo, ProcessNetworkStats


class WindowsProcessNetworkCollector(ProcessNetworkCollector):
    """Placeholder for the future Windows-native per-process collector.

    psutil does not expose reliable per-process byte counters on Windows, so this
    collector deliberately reports unavailable values instead of inventing data.
    """

    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        return tuple(ProcessNetworkStats(pid=p.pid, name=p.name) for p in processes)
