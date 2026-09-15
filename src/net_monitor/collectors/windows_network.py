from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.collectors.etw.events import NetworkEvent, ProcessNetworkTotals
from net_monitor.collectors.etw.network import NetworkAggregator
from net_monitor.collectors.etw.session import EtwSession
from net_monitor.core.models import ProcessInfo, ProcessNetworkStats


class _SessionProtocol(Protocol):
    def start(self) -> None: ...

    def stop(self, *, timeout: float = 5.0) -> None: ...


SessionFactory = Callable[[Callable[[NetworkEvent], None]], _SessionProtocol]
ProcessIdentity = tuple[int, float | None]


@dataclass(slots=True)
class _ProcessState:
    baseline_sent: int
    baseline_received: int
    previous_sent: int = 0
    previous_received: int = 0


class WindowsProcessNetworkCollector(ProcessNetworkCollector):
    """Production per-process network collector backed by Windows ETW.

    The ETW session starts lazily on the first collection. If Windows denies ETW
    access, the collector keeps the application usable and reports unavailable
    per-process values instead of inventing data.
    """

    def __init__(
        self,
        *,
        aggregator: NetworkAggregator | None = None,
        session_factory: SessionFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._aggregator = aggregator or NetworkAggregator()
        self._session_factory = session_factory or (lambda callback: EtwSession(callback))
        self._clock = clock
        self._session: _SessionProtocol | None = None
        self._states: dict[ProcessIdentity, _ProcessState] = {}
        self._previous_time: float | None = None
        self._last_error: Exception | None = None
        self._start_attempted = False
        self._closed = False

    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        if self._closed or not self._ensure_started():
            return self._unavailable(processes)

        totals = self._aggregator.snapshot()
        now = self._clock()
        elapsed = None if self._previous_time is None else now - self._previous_time
        active_identities: set[ProcessIdentity] = set()
        results: list[ProcessNetworkStats] = []

        for process in processes:
            identity = (process.pid, process.create_time)
            active_identities.add(identity)
            total = totals.get(process.pid, ProcessNetworkTotals(pid=process.pid))
            state = self._states.get(identity)

            if state is None:
                state = _ProcessState(
                    baseline_sent=total.bytes_sent,
                    baseline_received=total.bytes_received,
                )
                self._states[identity] = state
                observed_sent = 0
                observed_received = 0
                upload_rate = 0.0
                download_rate = 0.0
            else:
                observed_sent = max(0, total.bytes_sent - state.baseline_sent)
                observed_received = max(0, total.bytes_received - state.baseline_received)
                if elapsed is not None and elapsed > 0:
                    upload_rate = max(0, observed_sent - state.previous_sent) / elapsed
                    download_rate = max(0, observed_received - state.previous_received) / elapsed
                else:
                    upload_rate = 0.0
                    download_rate = 0.0

            state.previous_sent = observed_sent
            state.previous_received = observed_received
            results.append(
                ProcessNetworkStats(
                    pid=process.pid,
                    name=process.name,
                    upload_bytes=observed_sent,
                    download_bytes=observed_received,
                    upload_bytes_per_second=upload_rate,
                    download_bytes_per_second=download_rate,
                )
            )

        self._states = {
            identity: state for identity, state in self._states.items() if identity in active_identities
        }
        self._aggregator.retain_pids({process.pid for process in processes})
        self._previous_time = now
        return tuple(results)

    def _ensure_started(self) -> bool:
        if self._session is not None:
            return True
        if self._start_attempted:
            return False

        self._start_attempted = True
        session = self._session_factory(self._aggregator.record)
        try:
            session.start()
        except Exception as exc:
            self._last_error = exc
            try:
                session.stop()
            except Exception:
                pass
            return False

        self._session = session
        self._last_error = None
        return True

    @staticmethod
    def _unavailable(processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        return tuple(ProcessNetworkStats(pid=process.pid, name=process.name) for process in processes)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        session = self._session
        self._session = None
        if session is None:
            return
        try:
            session.stop()
        except Exception as exc:
            self._last_error = exc

    @property
    def available(self) -> bool:
        return self._session is not None and not self._closed

    @property
    def last_error(self) -> Exception | None:
        return self._last_error
