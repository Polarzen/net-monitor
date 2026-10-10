"""Session totals for the card and a read-only, incremental account tab."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from net_monitor.core.models import MonitorSnapshot
from net_monitor.ui.micro_model import SESSION_CAPTION, SESSION_EXPLANATION, WidgetFrame, format_bytes
from net_monitor.ui.session_model import SessionRow, session_rows
from net_monitor.ui.session_export import save_csv, session_csv


def label(text: str = "") -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    return result


def set_text(widget: QLabel, text: str) -> None:
    if widget.text() != text:
        widget.setText(text)


class SessionTotals(QWidget):
    """Render exactly the projection's account, including retained stale totals."""

    def __init__(self) -> None:
        super().__init__()
        self.caption = label(SESSION_CAPTION)
        self.values = label("无可信累计")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)
        layout.addWidget(self.caption)
        layout.addWidget(self.values)
        self.setToolTip(SESSION_EXPLANATION)

    def apply_frame(self, frame: WidgetFrame) -> None:
        account = frame.account
        if account is None or frame.selected is None or account.key != frame.selected.key:
            text = "无可信累计"
        else:
            text = f"↓ 下载 {format_bytes(account.download_bytes)}\n↑ 上传 {format_bytes(account.upload_bytes)}"
        set_text(self.values, text)
        self.values.setToolTip(text)
        self.caption.setToolTip(SESSION_EXPLANATION + ("" if frame.source_usable
                                 else "\n保留已确认累计；当前采集数据不可用。"))


class SessionItem(QTreeWidgetItem):
    """Keep Python integers for sorting; QVariant must not truncate huge bytes."""

    def __init__(self, row: SessionRow) -> None:
        super().__init__()
        self.key = row.account.key
        self.sort_values: tuple = ()
        self.update_row(row)

    def update_row(self, row: SessionRow) -> None:
        account = row.account
        self.sort_values = (account.name.casefold(), account.download_bytes,
                            account.upload_bytes, row.process_count, row.presence,
                            account.executable or account.key)
        texts = (account.name, format_bytes(account.download_bytes), format_bytes(account.upload_bytes),
                 "—" if row.process_count is None else str(row.process_count), row.presence,
                 account.executable or account.key)
        for column, text in enumerate(texts):
            if self.text(column) != text:
                self.setText(column, text)
            tooltip = f"{text}\n账户 key: {account.key}"
            if self.toolTip(column) != tooltip:
                self.setToolTip(column, tooltip)
        self.setData(0, Qt.ItemDataRole.UserRole, account.key)

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        if not isinstance(other, SessionItem):
            return self.text(0).casefold() < other.text(0).casefold()
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        left, right = self.sort_values[column], other.sort_values[column]
        if left is None or right is None:
            if left is None and right is None:
                return self.key < other.key
            return left is not None
        return self.key < other.key if left == right else left < right


class SessionView(QWidget):
    """All tracker accounts, not a second traversal of live processes."""

    def __init__(self) -> None:
        super().__init__()
        self.summary = label("暂无可信累计账户")
        self.source_label = label("启动中")
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索累计账户：应用名称、路径或账户标识")
        self.search.setAccessibleName("搜索累计账户")
        self.search.setClearButtonEnabled(True)
        self.include_identity = QCheckBox("导出包含路径和账户标识")
        self.include_identity.setToolTip("默认不导出这些字段。勾选后可能包含用户名等私人信息，分享前请检查。")
        self.export_button = QPushButton("导出 CSV…")
        self.export_button.setEnabled(False)
        self.export_button.setToolTip("保存点击时当前搜索结果的已确认累计；不会清零，也不会自动上传。")
        self.export_status = label()
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["应用 / 账户", "本次下载 (B)", "本次上传 (B)",
                                   "最近关联进程数", "进程状态", "路径 / 原始 key"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortItems(1, Qt.SortOrder.DescendingOrder)
        for column, width in enumerate((180, 170, 170, 140, 160, 280)):
            self.tree.setColumnWidth(column, width)
        self.tree.headerItem().setToolTip(3, "active_process_count：最近枚举关联的进程数，不是当前联网进程数。未知或过期时显示 —。")
        note = label(SESSION_EXPLANATION + "\n保留所有账户，包括已退出账户；累计账户未保存历史分类，不能猜测为系统或第三方。实时页筛选不影响本页。")
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.source_label)
        controls = QHBoxLayout()
        controls.addWidget(self.search, 1)
        controls.addWidget(self.include_identity)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.export_status)
        layout.addWidget(note)
        self._snapshot: MonitorSnapshot | None = None
        self._items: dict[str, SessionItem] = {}
        self._rendered: tuple | None = None
        self._rows: tuple[SessionRow, ...] = ()
        self.search.textChanged.connect(self._filter_rows)
        self.export_button.clicked.connect(self._export_csv)

    def _filter_rows(self) -> None:
        query = self.search.text().strip().casefold()
        visible = 0
        for row in self._rows:
            account = row.account
            matches = not query or any(query in text.casefold() for text in
                                       (account.name, account.executable or "", account.key))
            self._items[account.key].setHidden(not matches)
            visible += matches
        total = len(self._rows)
        set_text(self.summary, (f"显示 {visible} / {total} 个有流量累计账户（含已退出账户）"
                               if total else "本次监控尚无已确认流量"))
        self.export_button.setEnabled(visible > 0)

    def _export_csv(self) -> None:
        if self._snapshot is None:
            return
        self._flush()
        by_key = {row.account.key: row for row in self._rows}
        rows = tuple(by_key[item.key] for index in range(self.tree.topLevelItemCount())
                     if not (item := self.tree.topLevelItem(index)).isHidden())
        if not rows:
            return
        # Freeze data, options and time before entering the native dialog's event loop.
        payload = session_csv(rows, exported_at=datetime.now(timezone.utc).isoformat(),
                              source_status=self._snapshot.process_network_state.status.value,
                              include_identity=self.include_identity.isChecked())
        path, _ = QFileDialog.getSaveFileName(self, "导出本次监控累计", "NetMonitor-session.csv",
                                             "CSV 文件 (*.csv)")
        if not path:
            set_text(self.export_status, "已取消导出；累计数据未改变。")
            return
        try:
            save_csv(path, payload)
        except OSError as exc:
            set_text(self.export_status, "导出失败；累计数据未改变。")
            QMessageBox.warning(self, "导出失败", f"无法保存 CSV，请检查目标位置。\n{exc}")
            return
        set_text(self.export_status, f"已导出 {len(rows)} 个账户（点击导出时的快照）。")

    def apply_snapshot(self, snapshot: MonitorSnapshot) -> None:
        self._snapshot = snapshot
        if self.isVisible():
            self._flush()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._flush()

    def _flush(self) -> None:
        if self._snapshot is None:
            return
        snapshot = self._snapshot
        rows = session_rows(snapshot)
        token = (rows, snapshot.process_network_state)
        if token == self._rendered:
            return
        set_text(self.source_label, "进程状态来自最近一次枚举；累计大于 0 不代表当前联网。"
                 if snapshot.process_network_state.available else
                 (snapshot.process_network_state.message or "当前采集数据不可用；保留已确认累计，进程状态未知。"))
        column = self.tree.sortColumn()
        order = self.tree.header().sortIndicatorOrder()
        sorting = self.tree.isSortingEnabled()
        self.tree.setUpdatesEnabled(False)
        self.tree.setSortingEnabled(False)
        try:
            desired = {row.account.key for row in rows}
            for key in tuple(self._items):
                if key not in desired:
                    item = self._items.pop(key)
                    self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
            for row in rows:
                item = self._items.get(row.account.key)
                if item is None:
                    item = SessionItem(row)
                    self._items[row.account.key] = item
                    self.tree.addTopLevelItem(item)
                else:
                    item.update_row(row)
            self._rendered = token
            self._rows = rows
            self._filter_rows()
        finally:
            self.tree.setSortingEnabled(sorting)
            if sorting:
                self.tree.sortItems(column, order)
            self.tree.setUpdatesEnabled(True)
