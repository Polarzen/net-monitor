from __future__ import annotations

from threading import Lock

from net_monitor.collectors.etw.events import NetworkDirection, NetworkEvent, ProcessNetworkTotals


class NetworkAggregator:
    """Thread-safe accumulation of ETW network bytes and event counts by PID."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._totals: dict[int, ProcessNetworkTotals] = {}

    def record(self, event: NetworkEvent) -> None:
        with self._lock:
            current = self._totals.get(event.pid, ProcessNetworkTotals(pid=event.pid))
            if event.direction is NetworkDirection.SEND:
                updated = ProcessNetworkTotals(
                    pid=event.pid,
                    bytes_sent=current.bytes_sent + event.size,
                    bytes_received=current.bytes_received,
                    send_events=current.send_events + 1,
                    receive_events=current.receive_events,
                )
            else:
                updated = ProcessNetworkTotals(
                    pid=event.pid,
                    bytes_sent=current.bytes_sent,
                    bytes_received=current.bytes_received + event.size,
                    send_events=current.send_events,
                    receive_events=current.receive_events + 1,
                )
            self._totals[event.pid] = updated

    def snapshot(self) -> dict[int, ProcessNetworkTotals]:
        with self._lock:
            return dict(self._totals)

    def retain_pids(self, pids: set[int]) -> None:
        """Discard counters for processes that are no longer active."""
        with self._lock:
            self._totals = {pid: total for pid, total in self._totals.items() if pid in pids}

    def clear(self) -> None:
        with self._lock:
            self._totals.clear()
