from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time

from net_monitor.collectors.etw.constants import PROVIDER_GUID, PROVIDER_NAME
from net_monitor.collectors.etw.network import NetworkAggregator
from net_monitor.collectors.etw.session import EtwSession

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
    aggregator = NetworkAggregator()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.settimeout(10.0)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    child_code = (
        "import os,socket,sys;"
        "print(os.getpid(), flush=True);"
        "s=socket.create_connection(('127.0.0.1', int(sys.argv[1])));"
        f"s.sendall(b'S'*{_PAYLOAD_SIZE});"
        "remaining=" + str(_PAYLOAD_SIZE) + ";"
        "\nwhile remaining:\n"
        " data=s.recv(min(65536, remaining))\n"
        " if not data: break\n"
        " remaining-=len(data)\n"
        "s.close()"
    )

    configured_name = session_name or os.environ.get(_SESSION_NAME_ENV)
    try:
        with EtwSession(aggregator.record, session_name=configured_name) as session:
            server = threading.Thread(target=_serve_once, args=(listener,), daemon=False)
            server.start()
            time.sleep(0.5)
            child = subprocess.Popen(
                [sys.executable, "-c", child_code, str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = child.communicate(timeout=15)
            if child.returncode != 0:
                raise RuntimeError(f"probe child failed: {stderr.strip()}")
            child_pid = int(stdout.strip().splitlines()[0])
            server.join(timeout=12)
            if server.is_alive():
                raise RuntimeError("probe TCP server did not finish")
            time.sleep(1.5)
    finally:
        listener.close()

    totals = aggregator.snapshot().get(child_pid)
    return {
        "provider_name": PROVIDER_NAME,
        "provider_guid": PROVIDER_GUID,
        "session_name": session.session_name,
        "test_pid": child_pid,
        "pid_matched": totals is not None,
        "send_events": totals.send_events if totals else 0,
        "receive_events": totals.receive_events if totals else 0,
        "bytes_sent": totals.bytes_sent if totals else 0,
        "bytes_received": totals.bytes_received if totals else 0,
    }


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["pid_matched"]:
        print("ETW probe did not observe the controlled child PID", file=sys.stderr)
        return 2
    if int(result["send_events"]) <= 0 or int(result["receive_events"]) <= 0:
        print("ETW probe did not observe both send and receive events", file=sys.stderr)
        return 3
    if int(result["bytes_sent"]) <= 0 or int(result["bytes_received"]) <= 0:
        print("ETW probe did not observe both send and receive bytes", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
