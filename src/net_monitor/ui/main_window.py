from __future__ import annotations

import time

from PySide6.QtCore import QMetaObject, QThread, Qt
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
    MonitorSnapshot,
    ProcessInfo,
    ProcessNetworkState,
    ProcessNetworkStats,
    ProcessNetworkStatus,
)
from net_monitor.core.process_visibility import ProcessClassifier, visible_processes
from net_monitor.services.monitor_service import MonitorService
from net_monitor.ui.sampling_worker import SamplingWorker

_PID_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_CREATE_TIME_ROLE = int(Qt.ItemDataRole.UserRole) + 2


class NumericTableWidgetItem(QTableWidgetItem):
    """Table item that displays formatted text but sorts by its raw numeric value."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left < right
        return super().__lt__(other)


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: MonitorService | None = None,
        *,
        start_worker: bool = True,
        sampling_interval_ms: int = 500,
        classifier: ProcessClassifier | None = None,
    ) -> None:
        super().__init__()
        self._service = service or MonitorService()
        self._classifier = classifier or ProcessClassifier()
        self._latest_snapshot: MonitorSnapshot | None = None
        self._sampling_thread: QThread | None = None
        self._sampling_worker: SamplingWorker | None = None
        self._shutdown_complete = False
        self._last_apply_seconds = 0.0
        self._last_visible_rows = 0

        self.setWindowTitle("Net Monitor")
        self.resize(980, 620)

        self._upload_label = QLabel("第三方应用总上传速度: —")
        self._download_label = QLabel("第三方应用总下载速度: —")
        self._process_count_label = QLabel("当前显示进程数: 0")
        self._network_status_label = QLabel("进程网络监控：正在启动")
        self._network_activity_only = QCheckBox("仅显示有网络活动的进程")
        self._network_activity_only.setChecked(False)
        self._show_system_processes = QCheckBox("显示 Windows 系统进程")
        self._show_system_processes.setChecked(False)
        self._network_activity_only.toggled.connect(self._apply_latest_snapshot)
        self._show_system_processes.toggled.connect(self._apply_latest_snapshot)

        summary = QHBoxLayout()
        summary.addWidget(self._upload_label)
        summary.addWidget(self._download_label)
        summary.addWidget(self._process_count_label)
        summary.addStretch()

        network_controls = QHBoxLayout()
        network_controls.addWidget(self._network_status_label)
        network_controls.addStretch()
        network_controls.addWidget(self._show_system_processes)
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

        if start_worker:
            self._start_sampling_worker(sampling_interval_ms)

    @property
    def last_apply_seconds(self) -> float:
        return self._last_apply_seconds

    @property
    def last_visible_rows(self) -> int:
        return self._last_visible_rows

    def _start_sampling_worker(self, interval_ms: int) -> None:
        thread = QThread(self)
        worker = SamplingWorker(self._service, interval_ms=interval_ms)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.snapshot_ready.connect(self._on_snapshot)
        worker.sampling_failed.connect(self._on_sampling_failed)
        self._sampling_thread = thread
        self._sampling_worker = worker
        thread.start()

    def _on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        self._latest_snapshot = snapshot
        self._apply_snapshot(snapshot)

    def _on_sampling_failed(self, message: str) -> None:
        self._network_status_label.setText("进程网络监控：采样失败")
        self._network_status_label.setToolTip(message)

    def _apply_latest_snapshot(self) -> None:
        if self._latest_snapshot is not None:
            self._apply_snapshot(self._latest_snapshot)

    def _apply_snapshot(self, snapshot: MonitorSnapshot) -> None:
        started = time.perf_counter()
        rows = {item.pid: item for item in snapshot.process_network}
        app_processes = visible_processes(
            snapshot.processes,
            show_system=False,
            classifier=self._classifier,
        )
        app_pids = {process.pid for process in app_processes}
        processes = list(
            visible_processes(
                snapshot.processes,
                show_system=self._show_system_processes.isChecked(),
                classifier=self._classifier,
            )
        )

        upload_rate, download_rate = self._third_party_rates(
            snapshot.process_network_state,
            snapshot.process_network,
            app_pids,
        )
        self._upload_label.setText(
            "第三方应用总上传速度: "
            + ("—" if upload_rate is None else format_bytes_per_second(upload_rate))
        )
        self._download_label.setText(
            "第三方应用总下载速度: "
            + ("—" if download_rate is None else format_bytes_per_second(download_rate))
        )
        self._network_status_label.setText(self._status_text(snapshot.process_network_state))
        self._network_status_label.setToolTip(snapshot.process_network_state.message or "")

        if self._network_activity_only.isChecked():
            processes = [
                process
                for process in processes
                if self._has_network_activity(rows.get(process.pid))
            ]

        self._sync_table(processes, rows)
        self._process_count_label.setText(f"当前显示进程数: {len(processes)}")
        self._last_visible_rows = len(processes)
        self._last_apply_seconds = time.perf_counter() - started

    def _sync_table(
        self,
        processes: list[ProcessInfo],
        network_rows: dict[int, ProcessNetworkStats],
    ) -> None:
        header = self._table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorting_enabled = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)

        desired = {process.identity: process for process in processes}
        for row in range(self._table.rowCount() - 1, -1, -1):
            if self._row_identity(row) not in desired:
                self._table.removeRow(row)

        row_by_identity = {
            self._row_identity(row): row
            for row in range(self._table.rowCount())
        }

        for process in processes:
            identity = process.identity
            row = row_by_identity.get(identity)
            if row is None:
                row = self._table.rowCount()
                self._table.insertRow(row)
                row_by_identity[identity] = row

            network = network_rows.get(process.pid)
            self._update_process_row(row, process, network)

        if sorting_enabled:
            self._table.setSortingEnabled(True)
            if sort_column >= 0:
                self._table.sortItems(sort_column, sort_order)

    def _row_identity(self, row: int) -> tuple[int, float | None]:
        item = self._table.item(row, 0)
        if item is None:
            return -1, None
        pid = item.data(_PID_ROLE)
        create_time = item.data(_CREATE_TIME_ROLE)
        return int(pid) if pid is not None else -1, (
            float(create_time) if create_time is not None else None
        )

    def _update_process_row(
        self,
        row: int,
        process: ProcessInfo,
        network: ProcessNetworkStats | None,
    ) -> None:
        name_item = self._table.item(row, 0)
        if name_item is None:
            name_item = QTableWidgetItem(process.name)
            self._table.setItem(row, 0, name_item)
        elif name_item.text() != process.name:
            name_item.setText(process.name)
        name_item.setData(_PID_ROLE, process.pid)
        name_item.setData(_CREATE_TIME_ROLE, process.create_time)

        self._set_numeric_cell(row, 1, str(process.pid), process.pid)
        self._set_rate_cell(row, 2, None if network is None else network.download_bytes_per_second)
        self._set_rate_cell(row, 3, None if network is None else network.upload_bytes_per_second)
        self._set_bytes_cell(row, 4, None if network is None else network.download_bytes)
        self._set_bytes_cell(row, 5, None if network is None else network.upload_bytes)

    def _set_rate_cell(self, row: int, column: int, value: float | None) -> None:
        text = "—" if value is None else format_bytes_per_second(value)
        self._set_numeric_cell(row, column, text, value)

    def _set_bytes_cell(self, row: int, column: int, value: int | None) -> None:
        text = "—" if value is None else f"{value:,} B"
        self._set_numeric_cell(row, column, text, value)

    def _set_numeric_cell(
        self,
        row: int,
        column: int,
        text: str,
        value: int | float | None,
    ) -> None:
        item = self._table.item(row, column)
        if not isinstance(item, NumericTableWidgetItem):
            item = NumericTableWidgetItem(text)
            self._table.setItem(row, column, item)
        elif item.text() != text:
            item.setText(text)
        if item.data(Qt.ItemDataRole.UserRole) != value:
            item.setData(Qt.ItemDataRole.UserRole, value)

    def shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self._shutdown_complete = True

        thread = self._sampling_thread
        worker = self._sampling_worker
        if thread is not None and worker is not None and thread.isRunning():
            QMetaObject.invokeMethod(
                worker,
                "stop",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
            thread.quit()
            thread.wait()
        else:
            self._service.close()

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
