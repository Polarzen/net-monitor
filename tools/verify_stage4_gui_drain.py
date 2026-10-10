"""Bounded real GUI ETW check with an idle interval before the load exits.

This opt-in acceptance supervisor does not inject UI input or fake snapshots.
Elevation remains a native user decision. Only loopback test bytes are sent.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import psutil

from measure_stage4_live import query_session, read_events, receive_exact, utc


def client(port: int) -> int:
    print(json.dumps({"kind": "identity", "at": utc(), "pid": os.getpid(),
                      "create_time": psutil.Process().create_time()}), flush=True)
    if sys.stdin.readline().strip() != "start":
        return 2
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.settimeout(5)
        for index in range(8):
            connection.sendall(b"S" * 65536)
            if not receive_exact(connection, 131072):
                raise RuntimeError("Short test response")
            if index != 7:
                time.sleep(1)
    print(json.dumps({"kind": "traffic_finished", "at": utc(),
                      "sent": 8 * 65536, "received": 8 * 131072}), flush=True)
    time.sleep(8)
    print(json.dumps({"kind": "idle_finished", "at": utc()}), flush=True)
    return 0


def run(output: Path) -> int:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("A user-approved administrator token is required")
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    python = Path(sys.executable).with_name("python.exe")
    env = os.environ.copy()
    original_qt = {k: v for k, v in env.items() if k.startswith(("QT_", "QML_", "PYSIDE_"))}
    for key in ("QT_QPA_PLATFORM", "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(25)
    errors = []

    def serve() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(5)
                for _ in range(8):
                    if not receive_exact(connection, 65536):
                        raise RuntimeError("Short test upload")
                    connection.sendall(b"R" * 131072)
        except Exception as error:
            errors.append(repr(error))

    result = {"started_at": utc(), "observer_pid": os.getpid(),
              "observer_create_time": psutil.Process().create_time(),
              "original_qt_overrides": original_qt,
              "scope": "real Compact GUI rate-window drain; no CU interaction claim"}
    load = gui = None
    server = threading.Thread(target=serve, daemon=True)
    try:
        with (output / "load.jsonl").open("w", encoding="utf-8") as load_log, \
             (output / "errors.txt").open("w", encoding="utf-8") as error_log:
            load = subprocess.Popen([str(python), str(Path(__file__).resolve()), "--client",
                                     str(listener.getsockname()[1])], cwd=root, env=env,
                                    stdin=subprocess.PIPE, stdout=load_log, stderr=error_log,
                                    text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 10
            while not (events := read_events(output / "load.jsonl")):
                if load.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Load identity handshake failed")
                time.sleep(.1)
            identity = events[0]
            result["load_identity"] = identity
            gui = subprocess.Popen([str(python.with_name("pythonw.exe")),
                                    str(root / "tools/observe_stage4_desktop.py"), "--output",
                                    str(output / "gui.jsonl"), "--view", "compact", "--seconds",
                                    "80", "--load-pid", str(identity["pid"])], cwd=root, env=env,
                                   stdout=error_log, stderr=error_log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 20
            while True:
                events = read_events(output / "gui.jsonl")
                samples = [e for e in events if e["kind"] == "sample"]
                ready = samples[-2:]
                if len(ready) == 2 and all(e["network_status"] == "available"
                        and e["load_create_time"] == identity["create_time"]
                        and e["load_network"] and e["load_network"]["upload_bytes"] == 0
                        and e["load_network"]["download_bytes"] == 0 for e in ready):
                    break
                if gui.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("GUI did not establish a trustworthy zero baseline")
                time.sleep(.25)
            result["gui_identity"] = next(e for e in events if e["kind"] == "identity")
            observed_gui = psutil.Process(result["gui_identity"]["pid"])
            if observed_gui.create_time() != result["gui_identity"]["create_time"]:
                raise RuntimeError("Observed GUI identity changed")
            result["baseline_samples"] = ready
            server.start()
            result["load_started_at"] = utc()
            load.stdin.write("start\n")
            load.stdin.flush()
            load.stdin.close()
            result["load_exit_code"] = load.wait(timeout=25)
            server.join(timeout=5)
            result["server_errors"] = errors
            result["gui_exit_code"] = gui.wait(timeout=85)
            events = read_events(output / "gui.jsonl")
            samples = [e for e in events if e["kind"] == "sample"]
            phases = read_events(output / "load.jsonl")
            traffic = next(e for e in phases if e["kind"] == "traffic_finished")
            end_idle = next(e for e in phases if e["kind"] == "idle_finished")
            parse = datetime.fromisoformat
            idle = [e for e in samples if parse(traffic["at"]) < parse(e["at"]) < parse(end_idle["at"])
                    and e["load_create_time"] == identity["create_time"] and e["load_network"]]
            zeros = [e for e in idle if e["load_network"]["upload_bytes_per_second"] == 0
                     and e["load_network"]["download_bytes_per_second"] == 0]
            result["traffic"] = traffic
            result["idle_samples"] = idle
            result["first_zero_after_traffic_seconds"] = (
                (parse(zeros[0]["at"]) - parse(traffic["at"])).total_seconds() if zeros else None)
            result["final_sample"] = samples[-1]
            result["gui_exit_record"] = events[-1]
            result["session_query_after_exit"] = query_session(ready[-1]["etw_session"])
            network = [e["load_network"] for e in samples if e["load_network"]]
            tail = idle[-2:]
            account = samples[-1]["load_account"]
            checks = {
                "native_elevated_gui": result["gui_identity"]["elevated"]
                    and result["gui_identity"]["qt_platform"] == "windows",
                "gui_rate_window_2s": result["gui_identity"]["rate_window_seconds"] == 2.0,
                "available_throughout": all(e["network_status"] == "available" for e in samples),
                "positive_both_directions": any(n["upload_bytes_per_second"] > 0
                    and n["download_bytes_per_second"] > 0 for n in network),
                "monotonic_cumulative": all(b[k] >= a[k] for a, b in zip(network, network[1:])
                    for k in ("upload_bytes", "download_bytes")),
                "idle_tail_zero_and_stable": len(tail) == 2 and all(e in zeros for e in tail)
                    and all(tail[0]["load_network"][k] == tail[1]["load_network"][k] > 0
                            for k in ("upload_bytes", "download_bytes")),
                "retained_account": bool(account) and samples[-1]["load_network"] is None
                    and account["active_process_count"] == 0
                    and all(account[k] >= tail[-1]["load_network"][k] > 0
                            for k in ("upload_bytes", "download_bytes")),
                "normal_exits": result["load_exit_code"] == 0 and result["gui_exit_code"] == 0
                    and not errors and result["gui_exit_record"]["shutdown_complete"]
                    and not result["gui_exit_record"]["worker_running"],
                "own_session_absent": result["session_query_after_exit"] == 4201,
            }
            result["checks"] = checks
            result["qualified"] = all(checks.values())
    except Exception as error:
        result.update(error=repr(error), qualified=False)
    finally:
        listener.close()
        for child in (load, gui):
            if child is not None and child.poll() is None:
                result["forced_cleanup"] = True
                for descendant in reversed(psutil.Process(child.pid).children(recursive=True)):
                    try:
                        descendant.terminate()
                    except psutil.NoSuchProcess:
                        pass
                child.terminate()
                child.wait(timeout=5)
        result["finished_at"] = utc()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result.get("qualified") and not result.get("forced_cleanup") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--client", type=int)
    args = parser.parse_args()
    if args.client is not None:
        return client(args.client)
    if args.output_dir is None:
        parser.error("--output-dir is required")
    return run(args.output_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
