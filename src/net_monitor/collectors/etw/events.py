from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NetworkDirection(str, Enum):
    SEND = "send"
    RECEIVE = "receive"


@dataclass(frozen=True, slots=True)
class NetworkEvent:
    timestamp: float
    pid: int
    direction: NetworkDirection
    size: int
    protocol: str | None = None

    def __post_init__(self) -> None:
        if self.pid < 0:
            raise ValueError("pid must be non-negative")
        if self.size < 0:
            raise ValueError("size must be non-negative")


@dataclass(frozen=True, slots=True)
class ProcessNetworkTotals:
    pid: int
    bytes_sent: int = 0
    bytes_received: int = 0
    send_events: int = 0
    receive_events: int = 0

    def __post_init__(self) -> None:
        if self.pid < 0:
            raise ValueError("pid must be non-negative")
        if self.bytes_sent < 0 or self.bytes_received < 0:
            raise ValueError("network totals must be non-negative")
        if self.send_events < 0 or self.receive_events < 0:
            raise ValueError("event totals must be non-negative")
