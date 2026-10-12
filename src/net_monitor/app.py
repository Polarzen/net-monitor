from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from net_monitor import __version__
from net_monitor.ui.controller import UiController
from net_monitor.ui.theme import DARK_STYLESHEET


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Net Monitor")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("assets") / "net-monitor.ico")))
    app.setStyleSheet(DARK_STYLESHEET)
    controller = UiController()
    controller.show_primary(activate=False)
    return app.exec()
