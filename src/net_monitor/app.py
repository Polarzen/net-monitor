from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from net_monitor.ui.controller import UiController
from net_monitor.ui.theme import DARK_STYLESHEET


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Net Monitor")
    app.setStyleSheet(DARK_STYLESHEET)
    controller = UiController()
    app.aboutToQuit.connect(controller.shutdown)
    controller.show_compact()
    return app.exec()
