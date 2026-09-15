from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from net_monitor.core.application_aggregation import ApplicationNetworkGroup, aggregate_application_network
from net_monitor.core.elevation import restart_as_administrator
from net_monitor.core.formatting import format_bytes_per_second
from net_monitor.core.models import MonitorSnapshot, ProcessNetworkState, ProcessNetworkStatus
from net_monitor.core.process_visibility import ProcessClassifier, visible_processes


class CompactAppRow(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("appRow")
        self._name = QLabel("—")
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._download = QLabel("↓ —")
        self._upload = QLabel("↑ —")
        self._download.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._upload.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.setSpacing(8)
        layout.addWidget(self._name, 1)
        layout.addWidget(self._download)
        layout.addWidget(self._upload)

    def update_group(self, group: ApplicationNetworkGroup) -> None:
        self._name.setText(group.name)
        self._name.setToolTip(group.executable or group.name)
        self._download.setText("↓ " + self._format_rate(group.download_bytes_per_second))
        self._upload.setText("↑ " + self._format_rate(group.upload_bytes_per_second))
        self.setVisible(True)

    def clear_row(self) -> None:
        self.setVisible(False)

    @staticmethod
    def _format_rate(value: float | None) -> str:
        return "—" if value is None else format_bytes_per_second(value)


class CompactWindow(QMainWindow):
    details_requested = Signal()
    visibility_close_requested = Signal()
    always_on_top_changed = Signal(bool)

    def __init__(
        self,
        *,
        classifier: ProcessClassifier | None = None,
        elevation_launcher: Callable[[], bool] | None = None,
        top_count: int = 5,
    ) -> None:
        super().__init__()
        self._classifier = classifier or ProcessClassifier()
        self._elevation_launcher = elevation_launcher or restart_as_administrator
        self._top_count = max(3, min(8, top_count))
        self._tray_available = False
        self._shutdown_in_progress = False
        self._latest_snapshot: MonitorSnapshot | None = None
        self._always_on_top = False

        self.setWindowTitle("Net Monitor")
        self.resize(380, 360)
        self.setMinimumWidth(340)

        title = QLabel("Net Monitor")
        title.setObjectName("titleLabel")
        self._status_label = QLabel("启动中")
        self._status_label.setObjectName("statusIdle")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._status_label)

        self._download_value = QLabel("—")
        self._download_value.setObjectName("metricValue")
        self._upload_value = QLabel("—")
        self._upload_value.setObjectName("metricValue")
        download_caption = QLabel("下载")
        download_caption.setObjectName("metricCaption")
        upload_caption = QLabel("上传")
        upload_caption.setObjectName("metricCaption")

        download_card = QFrame()
        download_card.setObjectName("metricCard")
        download_layout = QVBoxLayout(download_card)
        download_layout.setContentsMargins(10, 8, 10, 8)
        download_layout.addWidget(download_caption)
        download_layout.addWidget(self._download_value)

        upload_card = QFrame()
        upload_card.setObjectName("metricCard")
        upload_layout = QVBoxLayout(upload_card)
        upload_layout.setContentsMargins(10, 8, 10, 8)
        upload_layout.addWidget(upload_caption)
        upload_layout.addWidget(self._upload_value)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(8)
        metrics.addWidget(download_card, 0, 0)
        metrics.addWidget(upload_card, 0, 1)

        self._active_count = QLabel("0 个应用正在联网")
        self._active_count.setObjectName("secondaryLabel")

        self._permission_frame = QFrame()
        self._permission_frame.setObjectName("emptyCard")
        permission_layout = QHBoxLayout(self._permission_frame)
        permission_layout.setContentsMargins(10, 8, 10, 8)
        self._permission_text = QLabel("需要管理员权限才能读取按进程网络流量")
        self._restart_button = QPushButton("以管理员身份重启")
        self._restart_button.setObjectName("accentButton")
        self._restart_button.clicked.connect(self._restart_with_elevation)
        permission_layout.addWidget(self._permission_text, 1)
        permission_layout.addWidget(self._restart_button)
        self._permission_frame.setVisible(False)

        self._empty_frame = QFrame()
        self._empty_frame.setObjectName("emptyCard")
        empty_layout = QVBoxLayout(self._empty_frame)
        empty_layout.setContentsMargins(10, 9, 10, 9)
        self._empty_label = QLabel("当前没有第三方应用正在使用网络")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("secondaryLabel")
        empty_layout.addWidget(self._empty_label)

        self._rows = [CompactAppRow() for _ in range(self._top_count)]
        rows_layout = QVBoxLayout()
        rows_layout.setSpacing(5)
        for row in self._rows:
            rows_layout.addWidget(row)
            row.clear_row()

        self._details_button = QPushButton("详细信息")
        self._details_button.setObjectName("accentButton")
        self._details_button.clicked.connect(self.details_requested.emit)
        self._pin_button = QPushButton("总在最前：关")
        self._pin_button.setCheckable(True)
        self._pin_button.toggled.connect(self._toggle_always_on_top)

        footer = QHBoxLayout()
        footer.addWidget(self._details_button)
        footer.addStretch()
        footer.addWidget(self._pin_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addLayout(metrics)
        layout.addWidget(self._active_count)
        layout.addWidget(self._permission_frame)
        layout.addWidget(self._empty_frame)
        layout.addLayout(rows_layout)
        layout.addLayout(footer)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    @property
    def latest_snapshot(self) -> MonitorSnapshot | None:
        return self._latest_snapshot

    @property
    def always_on_top(self) -> bool:
        return self._always_on_top

    def set_tray_available(self, available: bool) -> None:
        self._tray_available = available

    def set_shutdown_in_progress(self, shutting_down: bool) -> None:
        self._shutdown_in_progress = shutting_down

    def apply_snapshot(self, snapshot: MonitorSnapshot) -> None:
        self._latest_snapshot = snapshot
        state = snapshot.process_network_state
        groups = aggregate_application_network(
            visible_processes(snapshot.processes, show_system=False, classifier=self._classifier),
            snapshot.process_network,
        )
        upload_rate, download_rate = self._third_party_rates(state, groups)
        self._upload_value.setText("—" if upload_rate is None else format_bytes_per_second(upload_rate))
        self._download_value.setText("—" if download_rate is None else format_bytes_per_second(download_rate))
        self._apply_state(state)

        active = [] if not state.available else [group for group in groups if self._is_active(group)]
        active.sort(key=self._activity_score, reverse=True)
        self._active_count.setText(f"{len(active)} 个应用正在联网")
        self._empty_frame.setVisible(state.available and not active)

        for index, row in enumerate(self._rows):
            if index < len(active):
                row.update_group(active[index])
            else:
                row.clear_row()

    def set_always_on_top(self, enabled: bool) -> None:
        if self._pin_button.isChecked() != enabled:
            self._pin_button.blockSignals(True)
            self._pin_button.setChecked(enabled)
            self._pin_button.blockSignals(False)
        self._apply_always_on_top(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._tray_available and not self._shutdown_in_progress:
            event.ignore()
            self.hide()
            self.visibility_close_requested.emit()
            return
        super().closeEvent(event)

    def _apply_state(self, state: ProcessNetworkState) -> None:
        permission_denied = state.status is ProcessNetworkStatus.PERMISSION_DENIED
        self._permission_frame.setVisible(permission_denied)
        self._restart_button.setVisible(permission_denied)
        self._status_label.setText(self._status_text(state))
        self._status_label.setObjectName(self._status_object_name(state))
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._status_label.setToolTip(state.message or "")

    def _restart_with_elevation(self) -> None:
        self._restart_button.setEnabled(False)
        self._restart_button.setText("正在请求…")
        try:
            started = self._elevation_launcher()
        except Exception as exc:  # pragma: no cover - defensive OS boundary
            started = False
            self._restart_button.setToolTip(str(exc))
        if started:
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
            return
        self._restart_button.setText("以管理员身份重启")
        self._restart_button.setEnabled(True)

    def _toggle_always_on_top(self, enabled: bool) -> None:
        self._apply_always_on_top(enabled)
        self.always_on_top_changed.emit(enabled)

    def _apply_always_on_top(self, enabled: bool) -> None:
        was_visible = self.isVisible()
        self._always_on_top = enabled
        self._pin_button.setText("总在最前：开" if enabled else "总在最前：关")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if was_visible:
            self.show()

    @staticmethod
    def _activity_score(group: ApplicationNetworkGroup) -> float:
        download = group.download_bytes_per_second
        upload = group.upload_bytes_per_second
        if download is None or upload is None:
            return float("-inf")
        return float(download) + float(upload)

    @staticmethod
    def _is_active(group: ApplicationNetworkGroup) -> bool:
        if group.download_bytes_per_second is None or group.upload_bytes_per_second is None:
            return False
        return group.download_bytes_per_second > 0 or group.upload_bytes_per_second > 0

    @staticmethod
    def _third_party_rates(
        state: ProcessNetworkState,
        groups: tuple[ApplicationNetworkGroup, ...],
    ) -> tuple[float | None, float | None]:
        if not state.available:
            return None, None
        upload = 0.0
        download = 0.0
        for group in groups:
            if group.upload_bytes_per_second is None or group.download_bytes_per_second is None:
                return None, None
            upload += group.upload_bytes_per_second
            download += group.download_bytes_per_second
        return upload, download

    @staticmethod
    def _status_text(state: ProcessNetworkState) -> str:
        if state.status is ProcessNetworkStatus.AVAILABLE:
            return "运行中"
        if state.status is ProcessNetworkStatus.PERMISSION_DENIED:
            return "需要管理员权限"
        if state.status is ProcessNetworkStatus.UNAVAILABLE:
            return "采集不可用"
        if state.status is ProcessNetworkStatus.STOPPED:
            return "已停止"
        return "启动中"

    @staticmethod
    def _status_object_name(state: ProcessNetworkState) -> str:
        if state.status is ProcessNetworkStatus.AVAILABLE:
            return "statusAvailable"
        if state.status is ProcessNetworkStatus.PERMISSION_DENIED:
            return "statusWarning"
        if state.status is ProcessNetworkStatus.UNAVAILABLE:
            return "statusError"
        return "statusIdle"
