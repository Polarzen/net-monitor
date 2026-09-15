from __future__ import annotations

import time

from PySide6.QtCore import QMetaObject, QThread, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from net_monitor.core.application_aggregation import (
    ApplicationNetworkGroup,
    aggregate_application_network,
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

_GROUP_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_PID_ROLE = int(Qt.ItemDataRole.UserRole) + 2
_CREATE_TIME_ROLE = int(Qt.ItemDataRole.UserRole) + 3


class NumericTreeWidgetItem(QTreeWidgetItem):
    """Tree item that displays formatted text but sorts by raw numeric values."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        left = self.data(column, Qt.ItemDataRole.UserRole)
        right = other.data(column, Qt.ItemDataRole.UserRole)

        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left < right
        if left is None and right is not None:
            return False
        if left is not None and right is None:
            return True

        # Do not call super().__lt__() here. PySide6 routes that virtual call
        # back through this Python override and can recurse until stack overflow.
        return self.text(column).casefold() < other.text(column).casefold()


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
        self.resize(1040, 640)

        self._upload_label = QLabel("第三方应用总上传速度: —")
        self._download_label = QLabel("第三方应用总下载速度: —")
        self._process_count_label = QLabel("当前显示应用数: 0")
        self._network_status_label = QLabel("进程网络监控：正在启动")
        self._network_activity_only = QCheckBox("仅显示有网络活动的应用")
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

        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(
            ["应用 / 进程", "进程数 / PID", "下载速度", "上传速度", "下载总量", "上传总量"]
        )
        self._tree.setSortingEnabled(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setToolTip("展开应用行可查看各 PID 的网络使用明细")

        layout = QVBoxLayout()
        layout.addLayout(summary)
        layout.addLayout(network_controls)
        layout.addWidget(self._tree)
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
        network_rows = {item.pid: item for item in snapshot.process_network}

        third_party_processes = visible_processes(
            snapshot.processes,
            show_system=False,
            classifier=self._classifier,
        )
        third_party_groups = aggregate_application_network(
            third_party_processes,
            snapshot.process_network,
        )
        groups = list(
            aggregate_application_network(
                visible_processes(
                    snapshot.processes,
                    show_system=self._show_system_processes.isChecked(),
                    classifier=self._classifier,
                ),
                snapshot.process_network,
            )
        )

        upload_rate, download_rate = self._third_party_rates(
            snapshot.process_network_state,
            third_party_groups,
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
            groups = [group for group in groups if self._group_has_network_activity(group)]

        self._sync_tree(groups, network_rows)
        self._process_count_label.setText(f"当前显示应用数: {len(groups)}")
        self._last_visible_rows = len(groups)
        self._last_apply_seconds = time.perf_counter() - started

    def _sync_tree(
        self,
        groups: list[ApplicationNetworkGroup],
        network_rows: dict[int, ProcessNetworkStats],
    ) -> None:
        header = self._tree.header()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorting_enabled = self._tree.isSortingEnabled()
        self._tree.setSortingEnabled(False)

        desired_keys = {group.key for group in groups}
        for index in range(self._tree.topLevelItemCount() - 1, -1, -1):
            item = self._tree.topLevelItem(index)
            if self._group_key(item) not in desired_keys:
                self._tree.takeTopLevelItem(index)

        item_by_key = {
            self._group_key(self._tree.topLevelItem(index)): self._tree.topLevelItem(index)
            for index in range(self._tree.topLevelItemCount())
        }

        for group in groups:
            item = item_by_key.get(group.key)
            if item is None:
                item = NumericTreeWidgetItem()
                item.setData(0, _GROUP_KEY_ROLE, group.key)
                self._tree.addTopLevelItem(item)
                item_by_key[group.key] = item
            self._update_group_item(item, group)
            self._sync_process_children(item, group.processes, network_rows)

        if sorting_enabled:
            self._tree.setSortingEnabled(True)
            if sort_column >= 0:
                self._tree.sortItems(sort_column, sort_order)

    @staticmethod
    def _group_key(item: QTreeWidgetItem) -> str:
        value = item.data(0, _GROUP_KEY_ROLE)
        return str(value) if value is not None else ""

    def _update_group_item(
        self,
        item: QTreeWidgetItem,
        group: ApplicationNetworkGroup,
    ) -> None:
        if item.text(0) != group.name:
            item.setText(0, group.name)
        item.setData(0, _GROUP_KEY_ROLE, group.key)
        item.setToolTip(0, group.executable or "无法读取可执行文件路径")
        self._set_numeric_cell(item, 1, str(group.process_count), group.process_count)
        self._set_rate_cell(item, 2, group.download_bytes_per_second)
        self._set_rate_cell(item, 3, group.upload_bytes_per_second)
        self._set_bytes_cell(item, 4, group.download_bytes)
        self._set_bytes_cell(item, 5, group.upload_bytes)

    def _sync_process_children(
        self,
        parent: QTreeWidgetItem,
        processes: tuple[ProcessInfo, ...],
        network_rows: dict[int, ProcessNetworkStats],
    ) -> None:
        desired = {process.identity: process for process in processes}
        for index in range(parent.childCount() - 1, -1, -1):
            child = parent.child(index)
            if self._process_identity(child) not in desired:
                parent.takeChild(index)

        child_by_identity = {
            self._process_identity(parent.child(index)): parent.child(index)
            for index in range(parent.childCount())
        }

        for process in processes:
            child = child_by_identity.get(process.identity)
            if child is None:
                child = NumericTreeWidgetItem(parent)
                child_by_identity[process.identity] = child
            self._update_process_item(child, process, network_rows.get(process.pid))

    @staticmethod
    def _process_identity(item: QTreeWidgetItem) -> tuple[int, float | None]:
        pid = item.data(0, _PID_ROLE)
        create_time = item.data(0, _CREATE_TIME_ROLE)
        return int(pid) if pid is not None else -1, (
            float(create_time) if create_time is not None else None
        )

    def _update_process_item(
        self,
        item: QTreeWidgetItem,
        process: ProcessInfo,
        network: ProcessNetworkStats | None,
    ) -> None:
        label = process.name
        if item.text(0) != label:
            item.setText(0, label)
        item.setData(0, _PID_ROLE, process.pid)
        item.setData(0, _CREATE_TIME_ROLE, process.create_time)
        item.setToolTip(0, process.executable or "无法读取可执行文件路径")
        self._set_numeric_cell(item, 1, str(process.pid), process.pid)
        self._set_rate_cell(item, 2, None if network is None else network.download_bytes_per_second)
        self._set_rate_cell(item, 3, None if network is None else network.upload_bytes_per_second)
        self._set_bytes_cell(item, 4, None if network is None else network.download_bytes)
        self._set_bytes_cell(item, 5, None if network is None else network.upload_bytes)

    def _set_rate_cell(self, item: QTreeWidgetItem, column: int, value: float | None) -> None:
        text = "—" if value is None else format_bytes_per_second(value)
        self._set_numeric_cell(item, column, text, value)

    def _set_bytes_cell(self, item: QTreeWidgetItem, column: int, value: int | None) -> None:
        text = "—" if value is None else f"{value:,} B"
        self._set_numeric_cell(item, column, text, value)

    @staticmethod
    def _set_numeric_cell(
        item: QTreeWidgetItem,
        column: int,
        text: str,
        value: int | float | None,
    ) -> None:
        if item.text(column) != text:
            item.setText(column, text)
        if item.data(column, Qt.ItemDataRole.UserRole) != value:
            item.setData(column, Qt.ItemDataRole.UserRole, value)

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
    def _group_has_network_activity(group: ApplicationNetworkGroup) -> bool:
        return (group.upload_bytes or 0) > 0 or (group.download_bytes or 0) > 0
