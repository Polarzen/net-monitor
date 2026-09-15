from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from net_monitor.core.formatting import format_bytes_per_second
from net_monitor.core.models import (
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
)
from net_monitor.core.process_visibility import third_party_processes
from net_monitor.services.monitor_service import MonitorService


class NumericTableWidgetItem(QTableWidgetItem):
    """Table item that displays formatted text but sorts by its raw numeric value."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left < right
        return super().__lt__(other)


class MainWindow(QMainWindow):
    def __init__(self, service: MonitorService | None = None) -> None:
        super().__init__()
        self._service = service or MonitorService()
        self.setWindowTitle("Net Monitor")
        self.resize(980, 620)

        self._upload_label = QLabel("第三方应用总上传速度: —")
        self._download_label = QLabel("第三方应用总下载速度: —")
        self._process_count_label = QLabel("第三方进程数: 0")
        self._network_status_label = QLabel("进程网络监控：正在启动")
        self._network_activity_only = QCheckBox("仅显示有网络活动的进程")
        self._network_activity_only.setChecked(False)
        self._network_activity_only.toggled.connect(self.refresh)

        summary = QHBoxLayout()
        summary.addWidget(self._upload_label)
        summary.addWidget(self._download_label)
        summary.addWidget(self._process_count_label)
        summary.addStretch()

        network_controls = QHBoxLayout()
        network_controls.addWidget(self._network_status_label)
        network_controls.addStretch()
        network_controls.addWidget(self._network_activity_only)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["应用", "PID", "下载速度", "上传速度", "下载总量", "上传总量"]
        )
        self._table.setSortingEnabled(True)

        layout = QVBoxLayout()
        layout.addLayout(summary)
        layout.addLayout(network_controls)
        layout.addWidget(self._table)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        snapshot = self._service.snapshot()
        rows = {item.pid: item for item in snapshot.process_network}
        processes = list(third_party_processes(snapshot.processes))
        visible_pids = {process.pid for process in processes}

        upload_rate, download_rate = self._third_party_rates(
            snapshot.process_network_state,
            snapshot.process_network,
            visible_pids,
        )
        self._upload_label.setText(
            "第三方应用总上传速度: "
            + ("—" if upload_rate is None else format_bytes_per_second(upload_rate))
        )
        self._download_label.setText(
            "第三方应用总下载速度: "
            + ("—" if download_rate is None else format_bytes_per_second(download_rate))
        )
        self._process_count_label.setText(f"第三方进程数: {len(processes)}")
        self._network_status_label.setText(self._status_text(snapshot.process_network_state))
        self._network_status_label.setToolTip(snapshot.process_network_state.message or "")

        if self._network_activity_only.isChecked():
            processes = [
                process
                for process in processes
                if self._has_network_activity(rows.get(process.pid))
            ]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(processes))
        for row, process in enumerate(processes):
            network = rows.get(process.pid)
            self._table.setItem(row, 0, QTableWidgetItem(process.name))
            self._table.setItem(row, 1, self._numeric_item(str(process.pid), process.pid))
            self._table.setItem(
                row,
                2,
                self._rate_item(None if network is None else network.download_bytes_per_second),
            )
            self._table.setItem(
                row,
                3,
                self._rate_item(None if network is None else network.upload_bytes_per_second),
            )
            self._table.setItem(
                row,
                4,
                self._bytes_item(None if network is None else network.download_bytes),
            )
            self._table.setItem(
                row,
                5,
                self._bytes_item(None if network is None else network.upload_bytes),
            )
        self._table.setSortingEnabled(True)

    def shutdown(self) -> None:
        self._timer.stop()
        close = getattr(self._service, "close", None)
        if callable(close):
            close()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)

    @staticmethod
    def _status_text(state: ProcessNetworkState) -> str:
        if state.status is ProcessNetworkStatus.AVAILABLE:
            return "进程网络监控：运行中"
        if state.status is ProcessNetworkStatus.PERMISSION_DENIED:
            return "进程网络监控：不可用（需要管理员权限）"
        if state.status is ProcessNetworkStatus.UNAVAILABLE:
            return "进程网络监控：不可用"
        if state.status is ProcessNetworkStatus.STOPPED:
            return "进程网络监控：已停止"
        return "进程网络监控：正在启动"

    @staticmethod
    def _third_party_rates(
        state: ProcessNetworkState,
        network_rows: tuple[ProcessNetworkStats, ...],
        visible_pids: set[int],
    ) -> tuple[float | None, float | None]:
        if not state.available:
            return None, None
        upload = sum(
            row.upload_bytes_per_second or 0.0
            for row in network_rows
            if row.pid in visible_pids
        )
        download = sum(
            row.download_bytes_per_second or 0.0
            for row in network_rows
            if row.pid in visible_pids
        )
        return upload, download

    @staticmethod
    def _has_network_activity(network: ProcessNetworkStats | None) -> bool:
        if network is None:
            return False
        return (network.upload_bytes or 0) > 0 or (network.download_bytes or 0) > 0

    @staticmethod
    def _numeric_item(text: str, value: int | float | None) -> NumericTableWidgetItem:
        item = NumericTableWidgetItem(text)
        if value is not None:
            item.setData(Qt.ItemDataRole.UserRole, value)
        return item

    @classmethod
    def _rate_item(cls, value: float | None) -> NumericTableWidgetItem:
        if value is None:
            return cls._numeric_item("—", None)
        return cls._numeric_item(format_bytes_per_second(value), value)

    @classmethod
    def _bytes_item(cls, value: int | None) -> NumericTableWidgetItem:
        if value is None:
            return cls._numeric_item("—", None)
        return cls._numeric_item(f"{value:,} B", value)
