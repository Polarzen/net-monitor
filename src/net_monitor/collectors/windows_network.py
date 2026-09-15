from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from net_monitor.collectors.base import ProcessNetworkCollector
from net_monitor.collectors.etw.api import EtwPermissionError
from net_monitor.collectors.etw.events import NetworkEvent, ProcessNetworkTotals
from net_monitor.collectors.etw.network import NetworkAggregator
from net_monitor.collectors.etw.session import EtwSession
from net_monitor.core.models import (
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
    RetiredProcessNetworkStats,
)


class _SessionProtocol(Protocol):
    def start(self) -> None: ...

    def stop(self, *, timeout: float = 5.0) -> None: ...

    def raise_if_failed(self) -> None: ...


SessionFactory = Callable[[Callable[[NetworkEvent], None]], _SessionProtocol]
ProcessIdentity = tuple[int, float | None]


@dataclass(slots=True)
class _ProcessState:
    process: ProcessInfo
    baseline_sent: int
    baseline_received: int
    previous_sent: int = 0
    previous_received: int = 0


class WindowsProcessNetworkCollector(ProcessNetworkCollector):
    """Production per-process network collector backed by Windows ETW."""

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
        self._retired: list[RetiredProcessNetworkStats] = []
        self._previous_time: float | None = None
        self._last_error: Exception | None = None
        self._start_attempted = False
        self._closed = False
        self._state = ProcessNetworkState(ProcessNetworkStatus.STARTING)

    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        if self._closed or not self._ensure_started():
            return self._unavailable(processes)

        session = self._session
        if session is not None:
            try:
                session.raise_if_failed()
            except Exception as exc:
                self._record_session_failure(session, exc)
                return self._unavailable(processes)

        totals = self._aggregator.snapshot()
        now = self._clock()
        elapsed = None if self._previous_time is None else now - self._previous_time
        active_identities: set[ProcessIdentity] = set()
        active_pids = {process.pid for process in processes}
        results: list[ProcessNetworkStats] = []

        for process in processes:
            identity = process.identity
            active_identities.add(identity)
            total = totals.get(process.pid, ProcessNetworkTotals(pid=process.pid))
            state = self._states.get(identity)

            if state is None:
                state = _ProcessState(
                    process=process,
                    baseline_sent=total.bytes_sent,
                    baseline_received=total.bytes_received,
                )
                self._states[identity] = state
                observed_sent = 0
                observed_received = 0
                upload_rate = 0.0
                download_rate = 0.0
            else:
                state.process = process
                observed_sent, observed_received = self._observed_totals(state, total)
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

        self._capture_retired(totals, active_identities, active_pids)
        self._states = {
            identity: state for identity, state in self._states.items() if identity in active_identities
        }
        self._aggregator.retain_pids(active_pids)
        self._previous_time = now
        return tuple(results)

    def drain_retired(self) -> tuple[RetiredProcessNetworkStats, ...]:
        """Return and clear final counters for identities retired by the last collects."""

        retired = tuple(self._retired)
        self._retired.clear()
        return retired

    @staticmethod
    def _observed_totals(
        state: _ProcessState,
        total: ProcessNetworkTotals,
    ) -> tuple[int, int]:
        return (
            max(0, total.bytes_sent - state.baseline_sent),
            max(0, total.bytes_received - state.baseline_received),
        )

    def _capture_retired(
        self,
        totals: dict[int, ProcessNetworkTotals],
        active_identities: set[ProcessIdentity],
        active_pids: set[int],
    ) -> None:
        for identity, state in self._states.items():
            if identity in active_identities:
                continue

            pid = identity[0]
            # If the PID is already occupied by a new identity, the ETW
            # aggregator's PID bucket may contain bytes from both lifetimes.
            # Keep the old identity's last confirmed counters rather than
            # attributing any of the new process's bytes to it.
            if pid in active_pids:
                observed_sent = state.previous_sent
                observed_received = state.previous_received
            else:
                total = totals.get(pid, ProcessNetworkTotals(pid=pid))
                observed_sent, observed_received = self._observed_totals(state, total)
                observed_sent = max(observed_sent, state.previous_sent)
                observed_received = max(observed_received, state.previous_received)

            self._retired.append(
                RetiredProcessNetworkStats(
                    process=state.process,
                    network=ProcessNetworkStats(
                        pid=pid,
                        name=state.process.name,
                        upload_bytes=observed_sent,
                        download_bytes=observed_received,
                    ),
                )
            )

    def _ensure_started(self) -> bool:
        if self._session is not None:
            return self._state.status is ProcessNetworkStatus.AVAILABLE
        if self._start_attempted:
            return False

        self._start_attempted = True
        self._state = ProcessNetworkState(ProcessNetworkStatus.STARTING)
        try:
            session = self._session_factory(self._aggregator.record)
            session.start()
        except EtwPermissionError as exc:
            self._last_error = exc
            self._state = ProcessNetworkState(
                ProcessNetworkStatus.PERMISSION_DENIED,
                "需要以管理员身份运行 Net Monitor 才能获取每个进程的网络流量。",
                exc.error_code,
            )
            if "session" in locals():
                try:
                    session.stop()
                except Exception:
                    self._session = session
            return False
        except Exception as exc:
            self._last_error = exc
            self._state = ProcessNetworkState(
                ProcessNetworkStatus.UNAVAILABLE,
                "进程网络监控当前不可用。",
                getattr(exc, "error_code", None),
            )
            if "session" in locals():
                try:
                    session.stop()
                except Exception:
                    self._session = session
            return False

        self._session = session
        self._last_error = None
        self._state = ProcessNetworkState(ProcessNetworkStatus.AVAILABLE)
        return True

    def _record_session_failure(self, session: _SessionProtocol, exc: Exception) -> None:
        self._last_error = exc
        self._state = ProcessNetworkState(
            ProcessNetworkStatus.UNAVAILABLE,
            "进程网络监控当前不可用。",
            getattr(exc, "error_code", None),
        )
        if self._session is session:
            self._session = None
        try:
            session.stop()
        except Exception:
            # Retain ownership so a later close/retry can finish cleanup.
            if self._session is None:
                self._session = session

    @staticmethod
    def _unavailable(processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        return tuple(ProcessNetworkStats(pid=process.pid, name=process.name) for process in processes)

    def close(self) -> None:
        if self._closed and self._session is None:
            return
        self._closed = True
        session = self._session
        self._state = ProcessNetworkState(ProcessNetworkStatus.STOPPED)
        if session is None:
            return
        try:
            session.stop()
        except Exception as exc:
            self._last_error = exc
        else:
            if self._session is session:
                self._session = None

    @property
    def state(self) -> ProcessNetworkState:
        return self._state

    @property
    def available(self) -> bool:
        return self._state.available and self._session is not None and not self._closed

    @property
    def last_error(self) -> Exception | None:
        return self._last_error
