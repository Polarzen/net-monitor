"""Exercise the actual renderer, including Windows redirected console encoding."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_fake_renderer_handles_cp1252_stdout_and_keeps_utf8_manifest(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="1",
                       PYTHONIOENCODING="cp1252:strict")
    result = subprocess.run(
        [sys.executable, str(root / "tools/render_stage3c.py"),
         "--output", str(tmp_path), "--platform", "encoding-regression"],
        cwd=root, env=environment, capture_output=True, timeout=45,
    )
    assert result.returncode == 0, result.stderr.decode("ascii", errors="backslashreplace")
    console = json.loads(result.stdout.decode("ascii"))
    path = tmp_path / "encoding-regression-fake-scale-1" / "fake-layout-manifest.json"
    raw = path.read_text(encoding="utf-8")
    manifest = json.loads(raw)
    assert "中文" in raw
    assert console == manifest
    assert manifest["fake_snapshot"] is True
    assert manifest["physical_desktop"] is False
    assert manifest["real_etw"] is False
    assert manifest["sha"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert len(manifest["renders"]) >= 9
    assert all((path.parent / entry["file"]).is_file() for entry in manifest["renders"])
    assert manifest["cleanup"] == {
        "fake_service_close_count": 1, "icon_worker_stopped": True,
        "sampling_worker_started": False, "etw_started": False,
    }
