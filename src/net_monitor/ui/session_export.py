"""Serialize a user-selected session snapshot, never infer or accumulate bytes."""
from __future__ import annotations

import csv
import io

from PySide6.QtCore import QIODevice, QSaveFile

from net_monitor.ui.session_model import SessionRow


def spreadsheet_text(value: str) -> str:
    """Keep untrusted application metadata from becoming a spreadsheet formula."""
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def session_csv(rows: tuple[SessionRow, ...], *, exported_at: str,
                source_status: str, include_identity: bool = False) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    header = ["application", "download_bytes", "upload_bytes", "process_count",
              "process_state", "source_status", "exported_at_utc"]
    if include_identity:
        header += ["executable", "account_key"]
    writer.writerow(header)
    for row in rows:
        account = row.account
        values = [spreadsheet_text(account.name), account.download_bytes, account.upload_bytes,
                  "" if row.process_count is None else row.process_count, row.presence,
                  source_status, exported_at]
        if include_identity:
            values += [spreadsheet_text(account.executable or ""), spreadsheet_text(account.key)]
        writer.writerow(values)
    # BOM lets common Windows spreadsheet tools recognize Chinese names.
    return output.getvalue().encode("utf-8-sig")


def save_csv(path: str, payload: bytes) -> None:
    """Commit a complete file atomically; a failed write preserves an old file."""
    target = QSaveFile(path)
    target.setDirectWriteFallback(False)
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(target.errorString())
    try:
        if target.write(payload) != len(payload):
            raise OSError(target.errorString())
        if not target.commit():
            raise OSError(target.errorString())
    finally:
        if target.isOpen():
            target.cancelWriting()

