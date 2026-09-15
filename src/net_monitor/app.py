from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from net_monitor.ui.main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    return app.exec()
