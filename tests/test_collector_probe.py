from __future__ import annotations

import io
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

import net_monitor.collectors.etw.collector_probe as collector_probe
from net_monitor.collectors.etw.collector_probe import (
    _baseline_then_signal,
    _get_child_process_info,
    _read_child_pid,
    _serve_once,
    _terminate_child,
    _wait_for_idle_stats,
)
from net_monitor.core.models import ProcessInfo, ProcessNetworkStats


class _RecordingStdin:
    def __init__(self, events: list[tuple[str, str]]) -> None:
        self._events = events

    def write(self, value: str) -> None:
        self._events.append(("write", value))

    def flush(self) -> None:
        self._events.append(("flush", ""))

    def close(self) -> None:
        self._events.append(("close", ""))


class _BaselineCollector:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = events

    def collect(self, processes: tuple[object, ...]) -> None:
        self.events.append(("collect", processes))


def test_reported_child_pid_is_used_when_launcher_pid_differs() -> None:
    launcher_pid = 101
    actual_child_pid = 202
    events: list[tuple[str, object]] = []
    child = SimpleNamespace(
        pid=launcher_pid,
        stdin=_RecordingStdin(events),
    )
    collector = _BaselineCollector(events)

    reported_pid, reader, _ = _read_child_pid(io.StringIO(f"{actual_child_pid}\n"), timeout=1.0)
    process = _baseline_then_signal(
        collector,
        child,
        ProcessInfo(reported_pid, "python.exe", executable=r"C:\Python\python.exe", create_time=1.0),
    )
    reader.join(timeout=1.0)

    assert child.pid == launcher_pid
    assert reported_pid == actual_child_pid
    assert process.pid == actual_child_pid
    assert [name for name, _ in events] == ["collect", "write", "flush", "close"]


def test_baseline_is_collected_before_start_signal() -> None:
    events: list[tuple[str, object]] = []
    child = SimpleNamespace(stdin=_RecordingStdin(events))
    collector = _BaselineCollector(events)

    process = _baseline_then_signal(
        collector,
        child,
        ProcessInfo(4242, "python.exe", executable=r"C:\Python\python.exe", create_time=1.0),
    )

    assert process.pid == 4242
    assert events[0][0] == "collect"
    assert events[0][1][0].pid == 4242  # type: ignore[index]
    assert events[1:] == [("write", "start\n"), ("flush", ""), ("close", "")]


def test_handshake_timeout_and_server_shutdown_are_bounded() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    stop_event = threading.Event()
    server_errors: list[Exception] = []
    server = threading.Thread(
        target=_serve_once,
        args=(listener, stop_event, server_errors),
        daemon=True,
    )
    server.start()
    try:
        assert child.stdout is not None
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="PID was not reported"):
            _read_child_pid(child.stdout, timeout=0.1)
        assert time.monotonic() - started < 1.0
    finally:
        _terminate_child(child, timeout=1.0)
        stop_event.set()
        listener.close()
        server.join(timeout=1.0)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()

    assert child.poll() is not None
    assert not server.is_alive()
    assert server_errors == []


def test_child_identity_requires_complete_process_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        def name(self) -> str:
            return "python.exe"

        def exe(self) -> str:
            return r"C:\Python\python.exe"

        def create_time(self) -> float:
            return 123.0

    monkeypatch.setattr(collector_probe.psutil, "Process", lambda pid: FakeProcess())

    process = _get_child_process_info(4242)

    assert process == ProcessInfo(4242, "python.exe", executable=r"C:\Python\python.exe", create_time=123.0)


def test_child_identity_failure_cannot_be_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    class IncompleteProcess:
        def name(self) -> str:
            return "python.exe"

        def exe(self) -> str | None:
            return None

        def create_time(self) -> float:
            return 123.0

    monkeypatch.setattr(collector_probe.psutil, "Process", lambda pid: IncompleteProcess())

    with pytest.raises(RuntimeError, match="identity was incomplete"):
        _get_child_process_info(4242)


class _IdleStatsCollector:
    def __init__(self, stats: list[ProcessNetworkStats]) -> None:
        self._stats = stats
        self.calls = 0

    def collect(self, processes: tuple[ProcessInfo, ...]) -> tuple[ProcessNetworkStats, ...]:
        self.calls += 1
        return (self._stats[min(self.calls - 1, len(self._stats) - 1)],)


def _stats(
    *,
    upload_bytes: int = 100,
    download_bytes: int = 200,
    upload_rate: float,
    download_rate: float,
) -> ProcessNetworkStats:
    return ProcessNetworkStats(
        pid=42,
        name="python.exe",
        upload_bytes=upload_bytes,
        download_bytes=download_bytes,
        upload_bytes_per_second=upload_rate,
        download_bytes_per_second=download_rate,
    )


def test_idle_stats_require_stable_totals_and_exact_zero_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector_probe, "_RESULT_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(collector_probe, "_RESULT_TIMEOUT_SECONDS", 0.2)
    active = _stats(upload_rate=10.0, download_rate=20.0)
    delayed = _stats(upload_bytes=150, download_bytes=300, upload_rate=10.0, download_rate=20.0)
    idle = _stats(upload_bytes=150, download_bytes=300, upload_rate=0.0, download_rate=0.0)
    collector = _IdleStatsCollector([delayed, idle, idle])

    latest, window, totals_stable, recovered = _wait_for_idle_stats(
        collector,
        ProcessInfo(42, "python.exe", executable=r"C:\Python\python.exe", create_time=1.0),
        active,
    )

    assert recovered is True
    assert totals_stable is True
    assert window >= 0
    assert latest.upload_bytes == delayed.upload_bytes
    assert latest.download_bytes == delayed.download_bytes
    assert latest.upload_bytes_per_second == 0
    assert latest.download_bytes_per_second == 0


def test_idle_stats_timeout_when_rates_remain_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector_probe, "_RESULT_POLL_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(collector_probe, "_RESULT_TIMEOUT_SECONDS", 0.01)
    collector = _IdleStatsCollector([_stats(upload_rate=10.0, download_rate=20.0)])

    latest, window, totals_stable, recovered = _wait_for_idle_stats(
        collector,
        ProcessInfo(42, "python.exe", executable=r"C:\Python\python.exe", create_time=1.0),
        _stats(upload_rate=10.0, download_rate=20.0),
    )

    assert recovered is False
    assert totals_stable is False
    assert window >= 0.01
    assert latest.upload_bytes_per_second == 10.0
    assert latest.download_bytes_per_second == 20.0
