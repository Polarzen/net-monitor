"""Opt-in external measurement of real desktop UiController/Worker/ETW processes.

Each scene has its own GUI PID, 30s warmup, and 120 one-second CPU intervals.
The observer and bounded loopback load are separate from the measured GUI.
No synthetic MonitorSnapshot or fake service/tray is used.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import socket
import statistics
import subprocess
import sys
import threading
import time

import psutil


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            # A concurrent writer may not yet have finished the last line.
            if line != lines[-1]:
                raise
    return result


def receive_exact(connection: socket.socket, size: int) -> bool:
    while size:
        data = connection.recv(min(size, 65536))
        if not data:
            return False
        size -= len(data)
    return True


def client(port: int) -> int:
    print(json.dumps({"pid": os.getpid(), "create_time": psutil.Process().create_time()}), flush=True)
    if sys.stdin.readline().strip() != "start":
        return 2
    started = time.monotonic()
    sent = received = 0
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.settimeout(5)
        for index in range(160):
            delay = started + index - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            connection.sendall(b"S" * 65536)
            sent += 65536
            if not receive_exact(connection, 131072):
                raise RuntimeError("Short loopback response")
            received += 131072
    print(json.dumps({"sent": sent, "received": received,
                      "seconds": time.monotonic() - started}), flush=True)
    return 0


def query_session(name: str) -> int:
    from net_monitor.collectors.etw.api import EtwApi, CONTROLTRACE_ID, allocate_trace_properties
    storage, properties = allocate_trace_properties(name, real_time_mode=0, wnode_flag=0)
    return int(EtwApi().ControlTraceW(CONTROLTRACE_ID(0), name, properties, 0))


def measure_scene(root: Path, output: Path, scene: str) -> dict:
    events_path = output / f"{scene}-gui.jsonl"
    python = Path(sys.executable).with_name("python.exe")
    pythonw = python.with_name("pythonw.exe")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(30)
    server_errors = []

    def serve() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(6)
                for _ in range(160):
                    if not receive_exact(connection, 65536):
                        break
                    connection.sendall(b"R" * 131072)
        except Exception as error:
            server_errors.append(repr(error))

    env = os.environ.copy()
    original_qt = {k: v for k, v in env.items() if k.startswith(("QT_", "QML_", "PYSIDE_"))}
    # Limit overrides to these acceptance child processes, retaining the originals.
    for key in ("QT_QPA_PLATFORM", "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    load = subprocess.Popen([str(python), str(Path(__file__).resolve()), "--client",
                             str(listener.getsockname()[1])], cwd=root, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    handshake: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: handshake.put(load.stdout.readline()), daemon=True).start()
    try:
        load_identity = json.loads(handshake.get(timeout=10))
    except Exception:
        for descendant in reversed(psutil.Process(load.pid).children(recursive=True)):
            descendant.terminate()
        load.terminate()
        listener.close()
        raise
    gui = None
    server = threading.Thread(target=serve, name="Acceptance-Loopback", daemon=True)
    result = {"scene": scene, "started_at": utc(), "original_qt_overrides": original_qt,
              "load_identity": load_identity, "load": "160 x 64KiB upload / 128KiB download at 1Hz; 127.0.0.1",
              "cpu_convention": "100% = one logical processor; machine percent = CPU / logical_processors",
              "logical_processors": psutil.cpu_count(), "observer_pid": os.getpid(),
              "warmup_seconds": 30, "samples": []}
    try:
        with (output / f"{scene}-gui-output.txt").open("w", encoding="utf-8") as errors:
            gui = subprocess.Popen([str(pythonw), str(root / "tools/observe_stage4_desktop.py"),
                                    "--output", str(events_path), "--view", scene,
                                    "--seconds", "190", "--load-pid", str(load_identity["pid"])],
                                   cwd=root, env=env, stdout=errors, stderr=errors,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 20
            while True:
                events = read_events(events_path)
                ready = next((e for e in events if e["kind"] == "sample" and e["network_status"] == "available"), None)
                if ready:
                    break
                if gui.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("GUI did not report real ETW AVAILABLE within 20s")
                time.sleep(0.5)
            identity = next(e for e in events if e["kind"] == "identity")
            process = psutil.Process(identity["pid"])
            if process.create_time() != identity["create_time"]:
                raise RuntimeError("Measured GUI identity mismatch")
            result["gui_identity"] = identity
            result["etw_session"] = ready["etw_session"]
            server.start()
            load.stdin.write("start\n")
            load.stdin.flush()
            result["load_started_at"] = utc()
            warmup = time.monotonic()
            time.sleep(30)
            result["actual_warmup_seconds"] = time.monotonic() - warmup
            process.cpu_percent()
            started = time.monotonic()
            result["measurement_started_at"] = utc()
            for _ in range(120):
                cpu = process.cpu_percent(interval=1)
                if process.create_time() != identity["create_time"]:
                    raise RuntimeError("Measured process changed")
                memory = process.memory_info()
                events = read_events(events_path)
                current = next(e for e in reversed(events) if e["kind"] == "sample")
                result["samples"].append({
                    "at": utc(), "elapsed": time.monotonic() - started,
                    "cpu_one_core_percent": cpu, "cpu_machine_percent": cpu / psutil.cpu_count(),
                    "working_set_bytes": memory.rss, "private_bytes": memory.private,
                    "threads": process.num_threads(), "handles": process.num_handles(),
                    "processes": current["processes"], "accounts": current["accounts"],
                    "snapshot_count": current["snapshot_count"], "network_status": current["network_status"],
                    "last_gui_sample_at": current["at"],
                    "load_network": current["load_network"], "load_account": current["load_account"],
                })
                (output / f"{scene}-resources.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            result["observed_seconds"] = time.monotonic() - started
            result["measurement_finished_at"] = utc()
            load.stdin.close()
            load.stdin = None
            stdout, stderr = load.communicate(timeout=20)
            result["load_result"] = {"exit_code": load.returncode, "stdout": stdout, "stderr": stderr}
            server.join(timeout=8)
            result["server_errors"] = server_errors
            result["gui_exit_code"] = gui.wait(timeout=35)
            result["session_query_after_exit"] = query_session(result["etw_session"])
            events = read_events(events_path)
            result["last_gui_samples"] = [e for e in events if e["kind"] == "sample"][-5:]
            result["gui_exit_record"] = events[-1]
            result["summary"] = {}
            for key in ("cpu_one_core_percent", "cpu_machine_percent", "working_set_bytes",
                        "private_bytes", "threads", "handles", "processes", "accounts"):
                values = sorted(s[key] for s in result["samples"])
                result["summary"][key] = {"mean": statistics.mean(values),
                    "p95": values[math.ceil(len(values) * .95)-1], "min": values[0], "max": values[-1]}
            result["qualified"] = (load.returncode == 0 and not server_errors
                and result["gui_exit_code"] == 0 and result["session_query_after_exit"] == 4201
                and identity["elevated"] and identity["qt_platform"] == "windows"
                and all(s["network_status"] == "available" and s["load_network"]
                        and (s["load_network"]["upload_bytes"] or 0) > 0
                        and (s["load_network"]["download_bytes"] or 0) > 0 for s in result["samples"]))
    except Exception as error:
        result["error"] = repr(error)
        result["qualified"] = False
    finally:
        listener.close()
        for child in (load, gui):
            if child is not None and child.poll() is None:
                # Exact child tree only. A forced cleanup is never a passing exit result.
                result["forced_cleanup"] = True
                for descendant in reversed(psutil.Process(child.pid).children(recursive=True)):
                    try:
                        descendant.terminate()
                    except psutil.NoSuchProcess:
                        pass
                child.terminate()
                child.wait(timeout=5)
        result["finished_at"] = utc()
        (output / f"{scene}-resources.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--client", type=int)
    args = parser.parse_args()
    if args.client is not None:
        return client(args.client)
    if not args.output_dir:
        parser.error("--output-dir is required")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("A user-approved administrator token is required")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    results = [measure_scene(root, output, scene) for scene in ("micro", "detail", "hidden")]
    return 0 if all(r.get("qualified") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
