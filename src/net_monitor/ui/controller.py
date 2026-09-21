from __future__ import annotations

from collections.abc import Callable
import time

from PySide6.QtCore import QMetaObject, QObject, QPoint, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QStyle

from net_monitor.collectors.process import ProcessCollector
from net_monitor.collectors.windows_network import WindowsProcessNetworkCollector
from net_monitor.core.elevation import restart_as_administrator
from net_monitor.core.models import MonitorSnapshot
from net_monitor.services.monitor_service import MonitorService
from net_monitor.ui.compact_window import CompactWindow
from net_monitor.ui.detail_window import DetailWindow
from net_monitor.ui.icon_cache import IconCache
from net_monitor.ui.micro_model import (
    COLLAPSE_MS, HOVER_MS, UI_TICK_MS, DisplayState, MicroProjection,
    PresenceState, resolve_presence,
)
from net_monitor.ui.micro_window import ApplicationCard, MicroWindow
from net_monitor.ui.preferences import PreferencesStore, UiPreferences
from net_monitor.ui.sampling_worker import SamplingWorker
from net_monitor.ui.tray import TrayController
from net_monitor.ui.window_geometry import Rect, fit_rect, place_card
from net_monitor.ui.windows_icons import read_local_icon
from net_monitor.ui.windows_foreground import read_foreground_pid


class UiController(QObject):
    snapshot_ready = Signal(object)
    sampling_failed = Signal(str)

    def __init__(
        self, *, service: MonitorService | None = None, sampling_interval_ms: int = 500,
        elevation_launcher: Callable[[], bool] | None = None, start_worker: bool = True,
        clock: Callable[[], float] = time.monotonic,
        preferences_store: PreferencesStore | None = None,
        icon_reader: Callable | None = None,
        foreground_pid_reader: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__()
        self._app = QApplication.instance()
        if self._app is None:
            raise RuntimeError("Create QApplication before UiController")
        self._service = service or MonitorService(
            process_collector=ProcessCollector(include_status=False),
            process_network_collector=WindowsProcessNetworkCollector(rate_window_seconds=2.0),
        )
        self._sampling_interval_ms = sampling_interval_ms
        self._elevation_launcher = elevation_launcher or restart_as_administrator
        self._thread: QThread | None = None
        self._worker: SamplingWorker | None = None
        self._latest_snapshot: MonitorSnapshot | None = None
        self._published_snapshot: MonitorSnapshot | None = None
        self._published_state: DisplayState | None = None
        self._detail_window: DetailWindow | None = None
        self._shutdown_complete = False
        self._card_persistent = False
        self._main_menu_open = False
        self._screens: list = []
        self.projection = MicroProjection(clock=clock)
        self._foreground_pid_reader = foreground_pid_reader or read_foreground_pid
        self.preferences_store = preferences_store or PreferencesStore()
        preferences = self.preferences_store.load()
        self._last_saved = preferences
        self.mode = preferences.mode
        self._micro_on_top = preferences.micro_on_top
        self._icons = IconCache(icon_reader or read_local_icon)
        self.icon_worker_stopped = True
        self._icon_token = None
        self._current_icon = self._app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self._generic_icon = self._current_icon

        self.compact_window = CompactWindow(elevation_launcher=self._elevation_launcher)
        self.micro_window = MicroWindow()
        self.card = ApplicationCard()
        self.micro_window.set_icon(self._generic_icon)
        self.card.set_icon(self._generic_icon)
        self.compact_window.details_requested.connect(self.show_details)
        self.compact_window.exit_requested.connect(self.exit_application)
        self.compact_window.always_on_top_changed.connect(self.set_always_on_top)
        self.snapshot_ready.connect(self.compact_window.apply_snapshot)
        self.sampling_failed.connect(self._on_sampling_failed)
        self.compact_window.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.compact_window.customContextMenuRequested.connect(
            lambda point: self.show_menu(self.compact_window.mapToGlobal(point)))
        # An explicit menu-bar entry makes the Compact -> micro fallback discoverable.
        view_menu = self.compact_window.menuBar().addMenu("窗口")
        view_menu.addAction("微型模式", self.show_micro)
        view_menu.addAction("退出", self.exit_application)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(HOVER_MS)
        self._hover_timer.timeout.connect(self._hover_preview)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(COLLAPSE_MS)
        self._collapse_timer.timeout.connect(self._collapse_if_outside)
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(UI_TICK_MS)
        self._heartbeat.timeout.connect(self._heartbeat_refresh)
        self._heartbeat.start()

        self.micro_window.entered.connect(self._enter_micro)
        self.micro_window.left.connect(self._leave_region)
        self.micro_window.clicked.connect(lambda: self.show_card(interactive=True))
        self.micro_window.drag_started.connect(self.collapse_card)
        self.micro_window.drag_finished.connect(self._finish_drag)
        self.micro_window.moved.connect(self._position_card)
        self.micro_window.menu_requested.connect(self.show_menu)
        self.micro_window.close_requested.connect(self._close_primary)
        self.card.entered.connect(self._collapse_timer.stop)
        self.card.left.connect(self._leave_region)
        self.card.interacted.connect(self._keep_card)
        self.card.collapse_requested.connect(self.collapse_card)
        self.card.details_requested.connect(self.show_details)
        self.card.follow_requested.connect(self.follow)
        self.card.unfollow_requested.connect(self.unfollow)
        self.card.elevate_requested.connect(self._restart_with_elevation)
        self.card.menu_requested.connect(self.show_menu)

        # Keep TrayController's public callback contract, but restore the current mode.
        self.tray = TrayController(
            show_compact=self.show_primary, show_details=self.show_details,
            set_always_on_top=self.set_always_on_top, request_exit=self.exit_application,
        )
        self.compact_window.set_tray_available(self.tray.available)
        # Explicit primary-close/exit actions own shutdown even when no tray exists.
        # Closing a secondary card/detail must never terminate shared collection.
        self._app.setQuitOnLastWindowClosed(False)
        self._app.aboutToQuit.connect(self.shutdown)
        self._app.screenAdded.connect(self._on_screens_changed)
        self._app.screenRemoved.connect(self._on_screens_changed)
        self.micro_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._micro_on_top)
        self.tray.set_always_on_top_checked(self._micro_on_top if self.mode == "micro" else False)
        if preferences.micro_position is not None:
            self.micro_window.move(*preferences.micro_position)
        else:
            primary = self._app.primaryScreen()
            if primary is not None:
                area = primary.availableGeometry()
                self.micro_window.move(area.right() - self.micro_window.width() - 16, area.top() + 40)
        if preferences.compact_position is not None:
            self.compact_window.move(*preferences.compact_position)
        self._on_screens_changed()
        self._refresh_views()
        if start_worker:
            self.start()

    @property
    def service(self) -> MonitorService:
        return self._service

    @property
    def detail_window(self) -> DetailWindow | None:
        return self._detail_window

    @property
    def latest_snapshot(self) -> MonitorSnapshot | None:
        return self._latest_snapshot

    @property
    def primary_window(self):
        return self.micro_window if self.mode == "micro" else self.compact_window

    def start(self) -> None:
        if self._thread is not None or self._shutdown_complete:
            return
        thread = QThread(self)
        worker = SamplingWorker(self._service, interval_ms=self._sampling_interval_ms)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        thread.finished.connect(worker.deleteLater)
        worker.snapshot_ready.connect(self._on_snapshot)
        worker.sampling_failed.connect(self.sampling_failed.emit)
        self._thread, self._worker = thread, worker
        thread.start()

    def show_primary(self, *, activate: bool = True) -> None:
        if self._shutdown_complete:
            return
        self._recover_positions()
        window = self.primary_window
        window.show()
        if activate:
            window.raise_()
            window.activateWindow()
        self._refresh_views()

    def set_mode(self, mode: str) -> None:
        if mode not in ("micro", "compact"):
            raise ValueError("Unknown primary mode")
        self.collapse_card()
        self.mode = mode
        other = self.compact_window if mode == "micro" else self.micro_window
        other.hide()
        self.tray.set_always_on_top_checked(
            self._micro_on_top if mode == "micro" else self.compact_window.always_on_top)
        self.show_primary()
        self._save_preferences()

    def show_compact(self) -> None:
        self.set_mode("compact")

    def show_micro(self) -> None:
        self.set_mode("micro")

    def show_details(self) -> DetailWindow:
        if self._detail_window is None:
            detail = DetailWindow(service=self._service, elevation_launcher=self._elevation_launcher)
            detail.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            self.snapshot_ready.connect(detail.apply_snapshot)
            self._detail_window = detail
            snapshot = self.projection.display_snapshot()
            if snapshot is not None:
                detail.apply_snapshot(snapshot)
        self._detail_window.show()
        self._detail_window.raise_()
        self._detail_window.activateWindow()
        return self._detail_window

    def set_always_on_top(self, enabled: bool) -> None:
        if self.mode == "micro":
            self._micro_on_top = enabled
            was_visible = self.micro_window.isVisible()
            self.micro_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
            if was_visible:
                self.micro_window.show()  # WA_ShowWithoutActivating stays set.
            self._save_preferences()
        else:
            self.compact_window.set_always_on_top(enabled)
        # Fixed attention and topmost are different. Detail never inherits this flag.
        self.tray.set_always_on_top_checked(enabled)

    def _enter_micro(self) -> None:
        self._collapse_timer.stop()
        if not self.card.isVisible() and not self._main_menu_open:
            self._hover_timer.start()

    def _hover_preview(self) -> None:
        if self.micro_window.isVisible() and self.micro_window.underMouse():
            self.show_card(interactive=False)

    def _leave_region(self) -> None:
        self._hover_timer.stop()
        if not self._card_persistent:
            self._collapse_timer.start()

    def _keep_card(self) -> None:
        self._card_persistent = True
        self._collapse_timer.stop()

    def show_card(self, *, interactive: bool = False) -> ApplicationCard:
        if self.mode != "micro" or self._shutdown_complete:
            return self.card
        self._hover_timer.stop()
        self._collapse_timer.stop()
        self._card_persistent = self._card_persistent or interactive
        self.card.apply_frame(self.projection.frame())
        self.card.set_icon(self._current_icon)
        self._position_card(force=True)
        self.card.show()
        # Preview/automatic refresh never raises or activates a window.
        if interactive:
            self.card.raise_()
            self.card.activateWindow()
        return self.card

    def collapse_card(self) -> None:
        self._hover_timer.stop()
        self._collapse_timer.stop()
        self._card_persistent = False
        self.card.hide()

    def _collapse_if_outside(self) -> None:
        if self._card_persistent or self.card._menu_open or self._main_menu_open:
            return
        position = QCursor.pos()
        in_micro = self.micro_window.isVisible() and self.micro_window.frameGeometry().adjusted(-8, -8, 8, 8).contains(position)
        in_card = self.card.isVisible() and self.card.frameGeometry().adjusted(-8, -8, 8, 8).contains(position)
        if not in_micro and not in_card:
            self.collapse_card()

    def follow(self, key: str) -> None:
        self._keep_card()
        if self.projection.follow(key):
            self._refresh_views()

    def unfollow(self) -> None:
        self.projection.unfollow()
        self._refresh_views()

    def show_menu(self, point: QPoint) -> None:
        self._hover_timer.stop()
        self._collapse_timer.stop()
        menu = QMenu(self.primary_window)
        menu.addAction("微型模式", self.show_micro)
        menu.addAction("原 Compact 模式", self.show_compact)
        menu.addAction("详细信息", self.show_details)
        menu.addSeparator()
        top = menu.addAction("窗口置顶（不等于固定关注）")
        top.setCheckable(True)
        top.setChecked(self._micro_on_top if self.mode == "micro" else self.compact_window.always_on_top)
        top.toggled.connect(self.set_always_on_top)
        if self.projection.frame().focused:
            menu.addAction("取消固定关注", self.unfollow)
        if self.tray.available:
            menu.addAction("隐藏到托盘", self._close_primary)
        menu.addSeparator()
        menu.addAction("退出", self.exit_application)
        self._main_menu_open = True
        try:
            menu.exec(point)
        finally:
            self._main_menu_open = False
            menu.deleteLater()
            if not self._shutdown_complete:
                self._leave_region()

    def _close_primary(self) -> None:
        self.collapse_card()
        if self.tray.available:
            self.primary_window.hide()
        else:
            self.exit_application()

    def _restart_with_elevation(self) -> None:
        button = self.card.restart_button
        button.setEnabled(False)
        button.setText("正在请求管理员权限…")
        try:
            started = self._elevation_launcher()
        except Exception as exc:
            started = False
            button.setToolTip(f"管理员重启失败：{exc}")
        if started:
            self.exit_application()
        else:
            button.setEnabled(True)
            button.setText("以管理员身份重启")
            self.card.state_label.setText("管理员重启取消或失败；当前实例继续运行")

    @staticmethod
    def _rect(window) -> Rect:
        rect = window.frameGeometry()
        return Rect(rect.x(), rect.y(), rect.width(), rect.height())

    def _screen_rects(self) -> tuple[Rect, ...]:
        result = []
        for screen in self._app.screens():
            area = screen.availableGeometry()
            result.append(Rect(area.x(), area.y(), area.width(), area.height()))
        return tuple(result)

    def _on_screens_changed(self, *_args) -> None:
        screens = self._app.screens()
        for screen in self._screens:
            if screen not in screens:
                try:
                    screen.availableGeometryChanged.disconnect(self._recover_positions)
                except (RuntimeError, TypeError):
                    pass
        for screen in screens:
            if screen not in self._screens:
                screen.availableGeometryChanged.connect(self._recover_positions)
        self._screens = screens
        self._recover_positions()

    def _recover_positions(self, *_args) -> None:
        screens = self._screen_rects()
        if not screens or self._shutdown_complete:
            return
        for window in (self.micro_window, self.compact_window):
            rect = fit_rect(self._rect(window), screens)
            window.move(rect.x, rect.y)
        self._position_card()

    def _position_card(self, *, force: bool = False) -> None:
        screens = self._screen_rects()
        if screens and (force or self.card.isVisible()):
            rect = place_card(self._rect(self.micro_window), (372, 460), screens)
            self.card.setGeometry(rect.x, rect.y, rect.width, rect.height)

    def _finish_drag(self) -> None:
        screens = self._screen_rects()
        if screens:
            rect = fit_rect(self._rect(self.micro_window), screens, snap=12)
            self.micro_window.move(rect.x, rect.y)
        self._save_preferences()

    def _save_preferences(self) -> None:
        preferences = UiPreferences(self.mode, (self.micro_window.x(), self.micro_window.y()),
                                    (self.compact_window.x(), self.compact_window.y()), self._micro_on_top)
        if preferences != self._last_saved and self.preferences_store.save(preferences):
            self._last_saved = preferences

    def _on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        if self._shutdown_complete:
            return
        self._latest_snapshot = snapshot
        self.projection.receive(snapshot)
        self._publish_snapshot()
        self._refresh_views()

    def _on_sampling_failed(self, message: str) -> None:
        if not self._shutdown_complete:
            self.projection.fail(message)
            self._refresh_views()

    def _publish_snapshot(self) -> None:
        source = self.projection.source_state()
        snapshot = self.projection.display_snapshot()
        if snapshot is not None:
            self._published_snapshot = snapshot
            self.snapshot_ready.emit(snapshot)
        self._published_state = source
        if source in (DisplayState.STALE, DisplayState.FAILED):
            self.compact_window._status_label.setText(source.value)
            self.compact_window._status_label.setToolTip(self.projection.frame().message)
            if self._detail_window is not None:
                self._detail_window._network_status_label.setText(source.value)

    def _heartbeat_refresh(self) -> None:
        """Poll foreground once for this 500 ms UI tick, then repaint views."""

        self._refresh_views(poll_foreground=True)

    def _refresh_views(self, *, poll_foreground: bool = False) -> None:
        if self._shutdown_complete:
            return
        if self._published_state != self.projection.source_state():
            self._publish_snapshot()
        # Foreground is UI presence evidence, not collection data. Keep the
        # existing heartbeat as the only polling site. A
        # snapshot signal, menu, card repaint, or frame read reuses the last
        # poll only while its selected cached identity context is unchanged.
        if (poll_foreground and self.mode == "micro"
                and (self.micro_window.isVisible() or self.card.isVisible())):
            try:
                foreground_pid = self._foreground_pid_reader()
            except Exception:
                foreground_pid = None
            context = self.projection.presence_context()
            self.projection.set_presence_state(
                resolve_presence(context, foreground_pid), context)
        elif self.mode == "micro" and (self.micro_window.isVisible() or self.card.isVisible()):
            self.projection.set_presence_state(self.projection.cached_presence_state(),
                                               self.projection.presence_context())
        else:
            self.projection.set_presence_state(PresenceState.UNKNOWN, None)
        frame = self.projection.frame()
        # The tiny window is cheap; hidden cards receive no painting/text/icon work.
        self.micro_window.apply_frame(frame)
        if self.card.isVisible():
            self.card.apply_frame(frame)
        completed = self._icons.poll()
        for key, normalized, _pixels in completed:
            if frame.selected and frame.selected.key == key:
                self._icon_token = None  # Only the still-selected key may repaint.
        if (self.micro_window.isVisible() or self.card.isVisible()) and frame.selected:
            choice = frame.selected
            pixels = self._icons.request(choice.key, choice.executable)
            token = (choice.key, id(pixels))
            if token != self._icon_token:
                self._icon_token = token
                icon = self._generic_icon
                if pixels is not None:
                    image = QImage(pixels.bgra, pixels.width, pixels.height,
                                   pixels.width * 4, QImage.Format.Format_ARGB32).copy()
                    icon = QIcon(QPixmap.fromImage(image))
                self._current_icon = icon
                self.micro_window.set_icon(icon)
                if self.card.isVisible():
                    self.card.set_icon(icon)
        elif frame.selected is None and self._icon_token is not None:
            self._icon_token = None
            self._current_icon = self._generic_icon
            self.micro_window.set_icon(self._generic_icon)
            if self.card.isVisible():
                self.card.set_icon(self._generic_icon)

    def exit_application(self) -> None:
        self.shutdown()
        QApplication.quit()

    def shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        for timer in (self._heartbeat, self._hover_timer, self._collapse_timer):
            timer.stop()
        self._save_preferences()
        self.card.hide()
        self.compact_window.set_shutdown_in_progress(True)
        self.micro_window._shutdown = True
        self.tray.hide()
        if self._detail_window is not None:
            self._detail_window.set_shutdown_in_progress(True)
            self._detail_window.close()
        self.micro_window.close()
        self.compact_window.close()
        thread, worker = self._thread, self._worker
        if thread is not None and worker is not None and thread.isRunning():
            QMetaObject.invokeMethod(worker, "stop", Qt.ConnectionType.BlockingQueuedConnection)
            thread.quit()
            thread.wait()
        else:
            self._service.close()
        self.icon_worker_stopped = self._icons.close()
        for screen in self._screens:
            try:
                screen.availableGeometryChanged.disconnect(self._recover_positions)
            except (RuntimeError, TypeError):
                pass
        self._screens = []
        self._app.screenAdded.disconnect(self._on_screens_changed)
        self._app.screenRemoved.disconnect(self._on_screens_changed)
        self._app.aboutToQuit.disconnect(self.shutdown)
