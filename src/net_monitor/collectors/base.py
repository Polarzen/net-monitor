from __future__ import annotations

from abc import ABC, abstractmethod

from net_monitor.core.models import ProcessInfo, ProcessNetworkStats


class ProcessNetworkCollector(ABC):
    @abstractmethod
    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        """Return per-process network statistics for the supplied process list."""
        raise NotImplementedError
