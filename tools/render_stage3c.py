"""Render real widgets using FAKE snapshots. Not a physical desktop/ETW probe."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import PySide6
from PySide6.QtWidgets import QApplication, QLabel

import net_monitor.ui.controller as controller_module
from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import (
    ApplicationSessionStats, MonitorSnapshot, ProcessInfo, ProcessNetworkState,
    ProcessNetworkStats, ProcessNetworkStatus, SystemNetworkStats,
)
from net_monitor.ui.controller import UiController
from net_monitor.ui.preferences import PreferencesStore
from net_monitor.ui.theme import DARK_STYLESHEET


class FakeService:
    def __init__(self):
        self.closed = 0
    def close(self):
        self.closed += 1


def fake_snapshot():
    names = ("中文应用名称很长需要省略.exe", "Browser.exe", "下载器.exe", "Idle.exe")
    processes = tuple(ProcessInfo(100 + i, name, rf"D:\FakeApps\{name}", create_time=float(i + 1))
                      for i, name in enumerate(names))
    rows = tuple(ProcessNetworkStats(p.pid, p.name, 10000 + i, 1000000 + i,
                                    (4096.0, 0.05, 900.0, 0.0)[i],
                                    (2.5 * 1024**2, 900 * 1024.0, 0.0, 0.0)[i])
                 for i, p in enumerate(processes))
    accounts = tuple(ApplicationSessionStats(application_key(p), p.name, p.executable,
                                            10000 + i, 1000000 + i, 1) for i, p in enumerate(processes))
    return MonitorSnapshot(SystemNetworkStats(0, 0, 0, 0), processes, rows,
                           ProcessNetworkState(ProcessNetworkStatus.AVAILABLE), accounts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", default=platform.system())
    args = parser.parse_args()
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    output = args.output / f"{args.platform}-fake-scale-{scale}"
    output.mkdir(parents=True, exist_ok=True)
    expected = Path(__file__).resolve().parents[1] / "src/net_monitor/ui/controller.py"
    assert Path(controller_module.__file__).resolve() == expected, "Wrong editable install/source loaded"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(DARK_STYLESHEET)
    metadata = {"fake_snapshot": True, "physical_desktop": False, "real_etw": False,
                "sha": head, "controller_path": str(expected), "platform": platform.platform(),
                "python": platform.python_version(), "pyside": PySide6.__version__,
                "qt_scale_factor": scale, "renders": []}
    clock_value = [0.0]
    service = FakeService()
    with tempfile.TemporaryDirectory(prefix="net-monitor-fake-layout-") as temporary:
        c = UiController(service=service, start_worker=False, clock=lambda: clock_value[0],
                         preferences_store=PreferencesStore(Path(temporary) / "ui.json"),
                         icon_reader=lambda path: None)
        def capture(widget, name):
            app.processEvents()
            path = output / f"fake-{name}.png"
            assert widget.grab().save(str(path)), f"Could not save {path}"
            metadata["renders"].append({"file": path.name, "width": widget.width(),
                                        "height": widget.height(), "device_pixel_ratio": widget.devicePixelRatioF()})
        try:
            c.show_primary(activate=False)
            data = fake_snapshot()
            c._on_snapshot(data)
            app.processEvents()
            assert (c.micro_window.width(), c.micro_window.height()) == (112, 72)
            for label in (c.micro_window.name_label, c.micro_window.upload_label, c.micro_window.download_label):
                assert c.micro_window.rect().contains(label.geometry()), f"Label outside micro: {label.text()}"
                if label is not c.micro_window.name_label:
                    assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width(), f"Rate clipped: {label.text()}"
            capture(c.micro_window, "micro-active")
            c.show_card(interactive=False)
            capture(c.card, "card-active")
            detail = c.show_details()
            capture(detail, "detail-live")
            c.follow(application_key(data.processes[3]))
            capture(c.micro_window, "micro-focused-idle")
            capture(c.card, "card-focused-idle")
            c._on_snapshot(replace(data, process_network_state=ProcessNetworkState(ProcessNetworkStatus.PERMISSION_DENIED)))
            capture(c.micro_window, "micro-permission")
            capture(c.card, "card-permission")
            c._on_snapshot(data)
            clock_value[0] = 5.0
            c._refresh_views()
            capture(c.micro_window, "micro-stale")
            capture(c.card, "card-stale")
        finally:
            c.shutdown()
            app.processEvents()
            metadata["cleanup"] = {"fake_service_close_count": service.closed,
                                   "icon_worker_stopped": c.icon_worker_stopped,
                                   "sampling_worker_started": c._worker is not None,
                                   "etw_started": False}
            (output / "fake-layout-manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        assert service.closed == 1 and c.icon_worker_stopped
        assert c._worker is None
    print(json.dumps(metadata, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
