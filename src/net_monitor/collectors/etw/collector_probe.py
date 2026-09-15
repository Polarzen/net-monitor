from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from typing import Any, TextIO

from net_monitor.collectors.etw.session import EtwSession
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.models import ProcessInfo, ProcessNetworkStats

_PAYLOAD_SIZE = 512 * 1024
_SESSION_NAME_ENV = "NET_MONITOR_ETW_SESSION_NAME"
_CHILD_PID_TIMEOUT_SECONDS = 5.0
_CHILD_WAIT_TIMEOUT_SECONDS = 15.0
_SERVER_JOIN_TIMEOUT_SECONDS = 3.0
_SOCKET_POLL_INTERVAL_SECONDS = 0.25
_RESULT_TIMEOUT_SECONDS = 5.0
_RESULT_POLL_INTERVAL_SECONDS = 0.25


def _serve_once(
    listener: socket.socket,
    stop_event: threading.Event,
    errors: list[Exception],
) -> None:
    """Serve one bounded transfer and exit promptly when cleanup is requested."""

    try:
        listener.settimeout(_SOCKET_POLL_INTERVAL_SECONDS)
        while not stop_event.is_set():
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop_event.is_set():
                    return
                raise

            with conn:
                conn.settimeout(_SOCKET_POLL_INTERVAL_SECONDS)
                remaining = _PAYLOAD_SIZE
                while remaining and not stop_event.is_set():
                    try:
                        chunk = conn.recv(min(64 * 1024, remaining))
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    remaining -= len(chunk)
                if remaining or stop_event.is_set():
                    return

                response = b"R" * _PAYLOAD_SIZE
                sent = 0
                while sent < len(response) and not stop_event.is_set():
                    try:
                        count = conn.send(response[sent : sent + 64 * 1024])
                    except socket.timeout:
                        continue
                    if count <= 0:
                        return
                    sent += count
                return
    except BaseException as exc:
        if not stop_event.is_set():
            errors.append(exc)


def _start_stream_reader(stream: TextIO) -> tuple[threading.Thread, queue.Queue[str | None]]:
    """Read a subprocess pipe on a helper thread so the parent has a deadline."""

    lines: queue.Queue[str | None] = queue.Queue()

    def read() -> None:
        try:
            while True:
                line = stream.readline()
                if line == "":
                    break
                lines.put(line)
        finally:
            lines.put(None)

    thread = threading.Thread(target=read, name="NetMonitor-Probe-Output", daemon=True)
    thread.start()
    return thread, lines


def _read_child_pid(
    stdout: TextIO,
    *,
    timeout: float = _CHILD_PID_TIMEOUT_SECONDS,
) -> tuple[int, threading.Thread, queue.Queue[str | None]]:
    """Read the child-reported PID without allowing a pipe read to hang."""

    reader, lines = _start_stream_reader(stdout)
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"collector probe child PID was not reported within {timeout:.1f}s")
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError(f"collector probe child PID was not reported within {timeout:.1f}s") from exc
        if line is None:
            raise RuntimeError("collector probe child exited before reporting its PID")
        try:
            pid = int(line.strip())
        except ValueError as exc:
            raise RuntimeError(f"collector probe child reported an invalid PID: {line.strip()!r}") from exc
        if pid <= 0:
            raise RuntimeError(f"collector probe child reported an invalid PID: {pid}")
        return pid, reader, lines


def _baseline_then_signal(
    collector: WindowsProcessNetworkCollector,
    child: subprocess.Popen[str],
    child_pid: int,
) -> ProcessInfo:
    """Baseline the actual child PID before allowing it to create traffic."""

    process = ProcessInfo(pid=child_pid, name="net-monitor-probe-child")
    collector.collect((process,))
    if child.stdin is None:
        raise RuntimeError("collector probe child stdin is unavailable")
    child.stdin.write("start\n")
    child.stdin.flush()
    child.stdin.close()
    return process


def _terminate_child(
    child: subprocess.Popen[str],
    *,
    timeout: float = _CHILD_WAIT_TIMEOUT_SECONDS,
) -> None:
    """Stop the child through its owned Popen handle with bounded waits."""

    if child.poll() is not None:
        return
    try:
        child.terminate()
    except (OSError, ProcessLookupError):
        pass
    try:
        child.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        child.kill()
    except (OSError, ProcessLookupError):
        pass
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Cleanup remains bounded. The process handle is owned by Popen and
        # will be released when it is finalized; do not block the probe here.
        return


def _close_pipe(stream: Any) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _wait_for_bidirectional_stats(
    collector: WindowsProcessNetworkCollector,
    process: ProcessInfo,
) -> tuple[ProcessNetworkStats, float, float]:
    """Wait for bytes and observe positive rates across the bounded poll window.

    ProcessTrace may deliver send and receive events in different drain cycles.
    Because collector rates are interval deltas, a direction can legitimately
    return to 0 B/s on a later poll after its cumulative bytes were captured.
    The probe therefore keeps the peak positive rate observed for each direction
    independently while retaining the latest cumulative byte counters.
    """

    deadline = time.monotonic() + _RESULT_TIMEOUT_SECONDS
    peak_upload_rate = 0.0
    peak_download_rate = 0.0

    while True:
        latest = collector.collect((process,))[0]
        peak_upload_rate = max(
            peak_upload_rate,
            latest.upload_bytes_per_second or 0.0,
        )
        peak_download_rate = max(
            peak_download_rate,
            latest.download_bytes_per_second or 0.0,
        )
        if (
            (latest.upload_bytes or 0) > 0
            and (latest.download_bytes or 0) > 0
            and peak_upload_rate > 0
            and peak_download_rate > 0
        ):
            return latest, peak_upload_rate, peak_download_rate
        if time.monotonic() >= deadline:
            return latest, peak_upload_rate, peak_download_rate
        time.sleep(_RESULT_POLL_INTERVAL_SECONDS)


def run_probe(*, session_name: str | None = None) -> dict[str, object]:
    configured_name = session_name or os.environ.get(_SESSION_NAME_ENV)
    collector = WindowsProcessNetworkCollector(
        session_factory=lambda callback: EtwSession(callback, session_name=configured_name)
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.settimeout(10.0)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    child_code = (
        "import os,socket,sys\n"
        "print(os.getpid(), flush=True)\n"
        "if sys.stdin.readline().strip() != 'start':\n"
        " sys.exit(2)\n"
        "s=socket.create_connection(('127.0.0.1', int(sys.argv[1])));"
        f"s.sendall(b'S'*{_PAYLOAD_SIZE});"
        "remaining=" + str(_PAYLOAD_SIZE) + ";"
        "\nwhile remaining:\n"
        " data=s.recv(min(65536, remaining))\n"
        " if not data: break\n"
        " remaining-=len(data)\n"
        "s.close()"
    )

    child: subprocess.Popen[str] | None = None
    child_pid: int | None = None
    stdout_reader: threading.Thread | None = None
    stdout_lines: queue.Queue[str | None] | None = None
    stderr_reader: threading.Thread | None = None
    stderr_lines: queue.Queue[str | None] | None = None
    server: threading.Thread | None = None
    server_stop = threading.Event()
    server_errors: list[Exception] = []
    result: dict[str, object] | None = None
    try:
        collector.collect(())
        if not collector.available:
            raise RuntimeError(f"collector did not start: {collector.last_error!r}")

        server = threading.Thread(
            target=_serve_once,
            args=(listener, server_stop, server_errors),
            name="NetMonitor-Probe-Server",
            daemon=True,
        )
        server.start()
        child = subprocess.Popen(
            [sys.executable, "-c", child_code, str(port)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if child.stdout is None or child.stderr is None:
            raise RuntimeError("collector probe child output pipes are unavailable")
        stderr_reader, stderr_lines = _start_stream_reader(child.stderr)
        child_pid, stdout_reader, stdout_lines = _read_child_pid(child.stdout)
        process = _baseline_then_signal(collector, child, child_pid)

        try:
            child.wait(timeout=_CHILD_WAIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("collector probe child did not finish within 15.0s") from exc
        if stdout_reader is not None:
            stdout_reader.join(timeout=1.0)
        if stderr_reader is not None:
            stderr_reader.join(timeout=1.0)
        stderr = "".join(line for line in _drain_lines(stderr_lines) if line is not None)
        if child.returncode != 0:
            raise RuntimeError(f"collector probe child failed: {stderr.strip()}")
        if server is not None:
            server.join(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
        if server.is_alive():
            raise RuntimeError("collector probe TCP server did not finish")
        if server_errors:
            raise RuntimeError(f"collector probe TCP server failed: {server_errors[0]}")

        stats, observed_upload_rate, observed_download_rate = _wait_for_bidirectional_stats(
            collector,
            process,
        )
        result = {
            "test_pid": child_pid,
            "upload_bytes": stats.upload_bytes or 0,
            "download_bytes": stats.download_bytes or 0,
            "upload_bytes_per_second": observed_upload_rate,
            "download_bytes_per_second": observed_download_rate,
            "collector_available": collector.available,
        }
    finally:
        server_stop.set()
        if child is not None:
            _close_pipe(child.stdin)
            _terminate_child(child)
            _close_pipe(child.stdout)
            _close_pipe(child.stderr)
        listener.close()
        if server is not None:
            server.join(timeout=_SERVER_JOIN_TIMEOUT_SECONDS)
        collector.close()

    if result is None:
        raise RuntimeError("collector probe did not produce a result")
    result["collector_closed"] = not collector.available
    return result


def _drain_lines(lines: queue.Queue[str | None] | None) -> list[str | None]:
    if lines is None:
        return []
    drained: list[str | None] = []
    while True:
        try:
            drained.append(lines.get_nowait())
        except queue.Empty:
            return drained


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not bool(result.get("collector_available", False)):
        print("production collector was unavailable", file=sys.stderr)
        return 1
    if int(result["upload_bytes"]) <= 0 or int(result["download_bytes"]) <= 0:
        print("production collector did not report bidirectional bytes", file=sys.stderr)
        return 2
    if float(result["upload_bytes_per_second"]) <= 0 or float(result["download_bytes_per_second"]) <= 0:
        print("production collector did not report bidirectional rates", file=sys.stderr)
        return 3
    if not bool(result["collector_closed"]):
        print("production collector did not close its ETW session", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
