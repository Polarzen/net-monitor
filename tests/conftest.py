"""Load the verified CI font without adding a Qt dependency to ETW-only jobs."""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def ci_font_environment():
    if not os.environ.get("NET_MONITOR_LAYOUT_FONT"):
        yield
        return
    from PySide6.QtWidgets import QApplication
    from tools.layout_fonts import configure_application
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    yield
