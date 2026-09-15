from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProcessNetworkStatus(str, Enum):
    STARTING = "starting"
    AVAILABLE = "available"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"
    STOPPED = "stopped"


@dataclass(slots=True, frozen=True)
class ProcessNetworkState:
    status: ProcessNetworkStatus
    message: str | None = None
    error_code: int | None = None

    @property
    def available(self) -> bool:
        return self.status is ProcessNetworkStatus.AVAILABLE


@dataclass(slots=True, frozen=True)
class ProcessInfo:
    pid: int
    name: str
    executable: str | None = None
    status: str | None = None
    create_time: float | None = None


@dataclass(slots=True, frozen=True)
class ProcessNetworkStats:
    pid: int
    name: str
    upload_bytes: int | None = None
    download_bytes: int | None = None
    upload_bytes_per_second: float | None = None
    download_bytes_per_second: float | None = None


@dataclass(slots=True, frozen=True)
class SystemNetworkStats:
    bytes_sent: int
    bytes_received: int
    upload_bytes_per_second: float
    download_bytes_per_second: float


@dataclass(slots=True, frozen=True)
class NetworkCounters:
    bytes_sent: int
    bytes_received: int


@dataclass(slots=True, frozen=True)
class MonitorSnapshot:
    system: SystemNetworkStats
    processes: tuple[ProcessInfo, ...]
    process_network: tuple[ProcessNetworkStats, ...]
    process_network_state: ProcessNetworkState = ProcessNetworkState(ProcessNetworkStatus.STARTING)
