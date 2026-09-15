from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time

from net_monitor.collectors.etw.session import EtwSession
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.models import ProcessInfo

_PAYLOAD_SIZE = 512 * 1024
_SESSION_NAME_ENV = "NET_MONITOR_ETW_SESSION_NAME"


def _serve_once(listener: socket.socket) -> None:
    conn, _ = listener.accept()
    with conn:
        remaining = _PAYLOAD_SIZE
        while remaining:
            chunk = conn.recv(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        conn.sendall(b"R" * _PAYLOAD_SIZE)


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
        "import socket,sys,time;"
        "time.sleep(0.75);"
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
    try:
        collector.collect(())
        if not collector.available:
            raise RuntimeError(f"collector did not start: {collector.last_error!r}")

        server = threading.Thread(target=_serve_once, args=(listener,), daemon=False)
        server.start()
        child = subprocess.Popen(
            [sys.executable, "-c", child_code, str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process = ProcessInfo(pid=child.pid, name="net-monitor-probe-child")
        collector.collect((process,))

        _, stderr = child.communicate(timeout=15)
        if child.returncode != 0:
            raise RuntimeError(f"collector probe child failed: {stderr.strip()}")
        server.join(timeout=12)
        if server.is_alive():
            raise RuntimeError("collector probe TCP server did not finish")
        time.sleep(1.5)

        stats = collector.collect((process,))[0]
        result = {
            "test_pid": child.pid,
            "upload_bytes": stats.upload_bytes or 0,
            "download_bytes": stats.download_bytes or 0,
            "upload_bytes_per_second": stats.upload_bytes_per_second or 0.0,
            "download_bytes_per_second": stats.download_bytes_per_second or 0.0,
            "collector_available": collector.available,
        }
    finally:
        listener.close()
        collector.close()

    result["collector_closed"] = not collector.available
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
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
