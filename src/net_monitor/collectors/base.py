from __future__ import annotations

from abc import ABC, abstractmethod

from net_monitor.core.models import (
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
)


class ProcessNetworkCollector(ABC):
    @abstractmethod
    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        """Return per-process network statistics for the supplied process list."""
        raise NotImplementedError

    @property
    def state(self) -> ProcessNetworkState:
        return ProcessNetworkState(
            ProcessNetworkStatus.UNAVAILABLE,
            "进程网络采集器未提供状态信息",
        )
