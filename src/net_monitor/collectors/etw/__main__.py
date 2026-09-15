from __future__ import annotations

import signal
import threading

from net_monitor.collectors.etw.constants import PROVIDER_GUID, PROVIDER_NAME
from net_monitor.collectors.etw.network import NetworkAggregator
from net_monitor.collectors.etw.session import EtwSession


def main() -> int:
    aggregator = NetworkAggregator()
    stop_event = threading.Event()

    def request_stop(*_: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    print("Net Monitor ETW PoC")
    print(f"Provider: {PROVIDER_NAME}")
    print(f"Provider GUID: {PROVIDER_GUID}")
    print("Press Ctrl+C to stop.")

    with EtwSession(aggregator.record) as session:
        print(f"Session: {session.session_name}")
        while not stop_event.wait(1.0):
            snapshot = aggregator.snapshot()
            active = [item for item in snapshot.values() if item.bytes_sent or item.bytes_received]
            active.sort(key=lambda item: item.bytes_sent + item.bytes_received, reverse=True)
            for totals in active[:20]:
                print(
                    f"PID {totals.pid:<7} "
                    f"SEND {totals.bytes_sent:<12} "
                    f"RECEIVE {totals.bytes_received:<12}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
