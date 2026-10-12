from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from net_monitor import app
from net_monitor.ui.tray import TrayController


def test_startup_window_and_tray_share_readable_icon_from_any_cwd(monkeypatch, tmp_path):
    application = QApplication.instance() or QApplication([])
    previous_icon = QIcon(application.windowIcon())
    previous_name = application.applicationName()
    previous_version = application.applicationVersion()
    previous_style = application.styleSheet()
    windows, trays = [], []

    class Controller:
        def __init__(self):
            windows.append(QWidget())
            trays.append(TrayController(show_compact=lambda: None, show_details=lambda: None,
                set_always_on_top=lambda value: None, request_exit=lambda: None))

        def show_primary(self, **kwargs):
            pass

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "UiController", Controller)
    monkeypatch.setattr(application, "exec", lambda: 0)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    try:
        assert app.main() == 0
        icon = application.windowIcon()
        assert not icon.isNull()
        assert windows[0].windowIcon().cacheKey() == icon.cacheKey()
        assert trays[0]._tray.icon().cacheKey() == icon.cacheKey()
        for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
            assert QSize(size, size) in icon.availableSizes()
            image = icon.pixmap(size, size).toImage()
            assert image.size() == QSize(size, size)
            assert image.pixelColor(0, 0).alpha() == 0
            assert image.pixelColor(size // 2, size // 2).alpha() >= 240
    finally:
        application.setWindowIcon(previous_icon)
        application.setApplicationName(previous_name)
        application.setApplicationVersion(previous_version)
        application.setStyleSheet(previous_style)
        for tray in trays:
            tray.hide()
        for window in windows:
            window.close()
