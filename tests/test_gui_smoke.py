from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from net_monitor.core.models import MonitorSnapshot, ProcessInfo, ProcessNetworkStats, SystemNetworkStats
from net_monitor.ui.main_window import MainWindow


class FakeService:
    def snapshot(self) -> MonitorSnapshot:
        process = ProcessInfo(pid=1, name="demo.exe")
        return MonitorSnapshot(
            system=SystemNetworkStats(100, 200, 10.0, 20.0),
            processes=(process,),
            process_network=(ProcessNetworkStats(pid=1, name="demo.exe"),),
        )


def test_main_window_can_be_created() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(service=FakeService())
    assert window.windowTitle() == "Net Monitor"
    assert window.centralWidget() is not None
    window.close()
    app.processEvents()
