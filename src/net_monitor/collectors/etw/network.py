from __future__ import annotations

from threading import Lock

from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent, ProcessNetworkTotals


class NetworkAggregator:
    """Thread-safe accumulation of ETW network bytes by PID.

    PID reuse is intentionally not solved in the 2A PoC. The 2B production
    collector should key long-lived process state by (pid, process create time).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._totals: dict[int, ProcessNetworkTotals] = {}

    def record(self, event: NetworkEvent) -> None:
        if event.size < 0:
            raise ValueError("event size must be non-negative")

        with self._lock:
            current = self._totals.get(event.pid, ProcessNetworkTotals(pid=event.pid))
            if event.direction is NetworkDirection.SEND:
                updated = ProcessNetworkTotals(
                    pid=event.pid,
                    bytes_sent=current.bytes_sent + event.size,
                    bytes_received=current.bytes_received,
                )
            else:
                updated = ProcessNetworkTotals(
                    pid=event.pid,
                    bytes_sent=current.bytes_sent,
                    bytes_received=current.bytes_received + event.size,
                )
            self._totals[event.pid] = updated

    def snapshot(self) -> dict[int, ProcessNetworkTotals]:
        with self._lock:
            return dict(self._totals)

    def clear(self) -> None:
        with self._lock:
            self._totals.clear()
