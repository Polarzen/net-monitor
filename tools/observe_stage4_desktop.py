"""Manual/Computer Use acceptance observer for the real desktop application.

No fake snapshots, input injection, added timer, or added thread. Observation
uses the controller's existing heartbeat for changed UI state and optional
one-second samples. measure_stage4_live.py separately measures this real GUI;
its report must disclose the small acceptance-logging overhead.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import psutil
from PySide6.QtWidgets import QApplication

import net_monitor
from net_monitor.core.application_aggregation import application_key
from net_monitor.ui.controller import UiController
from net_monitor.ui.preferences import PreferencesStore
from net_monitor.ui.theme import DARK_STYLESHEET


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--view", choices=("compact", "micro", "detail", "hidden"), default="compact")
    parser.add_argument("--seconds", type=float, default=0, help="Bounded run; exits via normal controller shutdown")
    parser.add_argument("--load-pid", type=int)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to replace evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Net Monitor")
    app.setStyleSheet(DARK_STYLESHEET)
    with tempfile.TemporaryDirectory(prefix="net-monitor-acceptance-") as temporary:
        controller = UiController(preferences_store=PreferencesStore(Path(temporary) / "ui.json"))
        controller.compact_window.setWindowTitle("Net Monitor - Desktop Acceptance")
        if args.view == "compact":
            controller.show_compact()
        elif args.view == "detail":
            controller.show_details()
        else:
            controller.show_primary(activate=False)
            if args.view == "hidden":
                if not controller.tray.available:
                    raise RuntimeError("Real tray is required for the hidden scene")
                controller._close_primary()
        previous = None
        started = time.monotonic()
        last_sample = 0.0
        snapshot_count = 0
        load_key = None
        with output.open("x", encoding="utf-8", buffering=1) as stream:
            def write(kind: str, **data) -> None:
                stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                                         "kind": kind, **data}, ensure_ascii=False) + "\n")

            write("identity", pid=os.getpid(), create_time=psutil.Process().create_time(),
                  python=sys.executable, source=net_monitor.__file__,
                  elevated=bool(ctypes.windll.shell32.IsUserAnAdmin()),
                  qt_platform=app.platformName(),
                  source_sha256={str(p.relative_to(root)).replace("\\", "/"):
                                 hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((root / "src").rglob("*.py"))},
                  instrumentation="existing heartbeat observer; temporary preferences; Compact title only")

            def count_snapshot(*_args) -> None:
                nonlocal snapshot_count
                snapshot_count += 1

            controller.snapshot_ready.connect(count_snapshot)

            def observe() -> None:
                nonlocal previous, last_sample, load_key
                detail = controller.detail_window
                latest = controller.latest_snapshot
                current = {
                    "mode": controller.mode,
                    "compact_visible": controller.compact_window.isVisible(),
                    "micro_visible": controller.micro_window.isVisible(),
                    "card_visible": controller.card.isVisible(),
                    "detail_instance": id(detail) if detail is not None else None,
                    "detail_visible": detail.isVisible() if detail is not None else False,
                    "micro_size": [controller.micro_window.width(), controller.micro_window.height()],
                    "device_pixel_ratio": controller.primary_window.devicePixelRatioF(),
                    "tray_available": controller.tray.available,
                    "network_status": latest.process_network_state.status.value if latest else None,
                }
                if current != previous:
                    write("ui_state", **current)
                    previous = current
                now = time.monotonic()
                if args.load_pid and latest and now - last_sample >= 1:
                    last_sample = now
                    process = next((p for p in latest.processes if p.pid == args.load_pid), None)
                    if process is not None and process.create_time is not None:
                        load_key = application_key(process)
                    network = next((n for n in latest.process_network if n.pid == args.load_pid), None)
                    account = next((a for a in latest.application_session if a.key == load_key), None)
                    collector = controller.service._process_network_collector
                    session = getattr(collector, "_session", None)
                    write("sample", elapsed=now-started, **current,
                          snapshot_count=snapshot_count, processes=len(latest.processes),
                          accounts=len(latest.application_session), load_pid=args.load_pid,
                          load_create_time=process.create_time if process else None,
                          load_network=({k: v for k, v in asdict(network).items() if k != "name"}
                                        if network else None),
                          load_account=({k: getattr(account, k) for k in
                                         ("upload_bytes", "download_bytes", "active_process_count")}
                                        if account else None),
                          load_key_sha256=hashlib.sha256(load_key.encode()).hexdigest() if load_key else None,
                          etw_session=session.session_name if session else None)
                if args.seconds > 0 and now - started >= args.seconds:
                    controller.exit_application()

            controller._heartbeat.timeout.connect(observe)
            observe()
            app.aboutToQuit.connect(lambda: write("about_to_quit"))
            result = app.exec()
            controller.shutdown()
            write("event_loop_exited", exit_code=result,
                  shutdown_complete=controller._shutdown_complete,
                  worker_running=bool(controller._thread and controller._thread.isRunning()))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
