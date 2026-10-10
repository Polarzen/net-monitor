"""Opt-in desktop acceptance: bounded real ETW probes, never imported by the app.

Run with the existing venv. Elevation, when needed, is a native user decision.
Only disposable 127.0.0.1 payloads from the existing probes are transferred.
This is collector evidence, not GUI acceptance or a product performance test.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import psutil


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to replace evidence: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).with_name("python.exe")
    run_id = uuid.uuid4().hex[:12]
    record = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "observer_pid": os.getpid(),
        "observer_create_time": psutil.Process().create_time(),
        "python": str(python),
        "elevated": bool(ctypes.windll.shell32.IsUserAnAdmin()),
        "scope": "real Windows ETW; loopback only; no GUI/performance claim",
        "payload_per_transfer_per_direction": 512 * 1024,
        "maximum_transfers": 4,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_sha256": {
            str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "src").rglob("*.py"))
        },
        "results": [],
    }

    def save() -> None:
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def run(command: list[str], timeout: int) -> dict:
        started = time.monotonic()
        child = subprocess.Popen(
            command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
        )
        result = {"command": command, "pid": child.pid,
                  "create_time": psutil.Process(child.pid).create_time()}
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Limit cleanup to the exact probe process tree we created.
            process = psutil.Process(child.pid)
            descendants = process.children(recursive=True)
            for item in reversed(descendants):
                try:
                    item.kill()
                except psutil.NoSuchProcess:
                    pass
            child.kill()
            stdout, stderr = child.communicate(timeout=5)
            result["timed_out"] = True
        # Keep command paths needed for reproducibility; redact the base Python
        # user profile in diagnostic payloads before publishing evidence.
        profile = str(Path.home())
        def redact(value: str) -> str:
            return value.replace(profile.replace("\\", "\\\\"), "%USERPROFILE%").replace(profile, "%USERPROFILE%")

        result.update(exit_code=child.returncode, stdout=redact(stdout),
                      stderr=redact(stderr),
                      elapsed_seconds=time.monotonic() - started)
        try:
            result["data"] = json.loads(result["stdout"])
        except ValueError:
            pass
        return result

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    save()
    if not record["elevated"]:
        record["status"] = "blocked: administrator token required"
        save()
        return 2
    try:
        permission = run([str(python), "-m", "net_monitor.collectors.etw.permission_probe"], 45)
        record["results"].append({"kind": "permission", **permission})
        save()
        if permission.get("data", {}).get("success") is not True:
            record["status"] = "blocked: ETW enablement failed"
            return 3
        for kind, module in (("raw", "probe"), ("production", "collector_probe")):
            session_name = f"NetMonitor-Stage4-Acceptance-{run_id}-{kind}"
            env["NET_MONITOR_ETW_SESSION_NAME"] = session_name
            for iteration in (1, 2):
                result = run([str(python), "-m", f"net_monitor.collectors.etw.{module}"], 45)
                cleanup = run(["logman", "query", session_name, "-ets"], 10)
                record["results"].append({
                    "kind": kind, "iteration": iteration, "session_name": session_name,
                    **result, "post_exit_session_query": cleanup,
                })
                save()
                if result["exit_code"] != 0:
                    record["status"] = "failed: probe (inspect data and stderr)"
                    return 4
        record["status"] = "probes completed; inspect semantic results and session query codes"
        return 0
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    raise SystemExit(main())
