from __future__ import annotations

import io
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from net_monitor.collectors.etw.collector_probe import (
    _baseline_then_signal,
    _read_child_pid,
    _serve_once,
    _terminate_child,
)


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
    process = _baseline_then_signal(collector, child, reported_pid)
    reader.join(timeout=1.0)

    assert child.pid == launcher_pid
    assert reported_pid == actual_child_pid
    assert process.pid == actual_child_pid
    assert [name for name, _ in events] == ["collect", "write", "flush", "close"]


def test_baseline_is_collected_before_start_signal() -> None:
    events: list[tuple[str, object]] = []
    child = SimpleNamespace(stdin=_RecordingStdin(events))
    collector = _BaselineCollector(events)

    process = _baseline_then_signal(collector, child, 4242)

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
