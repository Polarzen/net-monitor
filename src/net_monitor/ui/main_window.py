from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from net_monitor.core.formatting import format_bytes_per_second
from net_monitor.core.models import ProcessNetworkStats
from net_monitor.services.monitor_service import MonitorService


class MainWindow(QMainWindow):
    def __init__(self, service: MonitorService | None = None) -> None:
        super().__init__()
        self._service = service or MonitorService()
        self.setWindowTitle("Net Monitor")
        self.resize(900, 600)

        self._upload_label = QLabel("总上传速度: 0 B/s")
        self._download_label = QLabel("总下载速度: 0 B/s")
        self._process_count_label = QLabel("当前进程数: 0")

        summary = QHBoxLayout()
        summary.addWidget(self._upload_label)
        summary.addWidget(self._download_label)
        summary.addWidget(self._process_count_label)
        summary.addStretch()

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["进程", "PID", "下载速度", "上传速度", "总流量"])
        self._table.setSortingEnabled(True)

        layout = QVBoxLayout()
        layout.addLayout(summary)
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
        self._upload_label.setText(
            f"总上传速度: {format_bytes_per_second(snapshot.system.upload_bytes_per_second)}"
        )
        self._download_label.setText(
            f"总下载速度: {format_bytes_per_second(snapshot.system.download_bytes_per_second)}"
        )
        self._process_count_label.setText(f"当前进程数: {len(snapshot.processes)}")

        rows = {item.pid: item for item in snapshot.process_network}
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(snapshot.processes))
        for row, process in enumerate(snapshot.processes):
            network = rows.get(process.pid)
            values = self._row_values(process.name, process.pid, network)
            for column, value in enumerate(values):
                self._table.setItem(row, column, QTableWidgetItem(value))
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
    def _row_values(name: str, pid: int, network: ProcessNetworkStats | None) -> tuple[str, ...]:
        if network is None or network.download_bytes_per_second is None:
            download = "—"
        else:
            download = format_bytes_per_second(network.download_bytes_per_second)
        if network is None or network.upload_bytes_per_second is None:
            upload = "—"
        else:
            upload = format_bytes_per_second(network.upload_bytes_per_second)
        if network is None or network.upload_bytes is None or network.download_bytes is None:
            total = "—"
        else:
            total = f"{network.upload_bytes + network.download_bytes:,} B"
        return name, str(pid), download, upload, total
