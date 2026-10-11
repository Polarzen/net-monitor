import csv
from dataclasses import replace
import io

import pytest
from PySide6.QtCore import Qt

from net_monitor.core.models import ProcessNetworkState, ProcessNetworkStatus
from net_monitor.ui.session_export import save_csv, session_csv
from net_monitor.ui.session_model import session_rows
import net_monitor.ui.session_view as module
from test_stage3c_ui import app, make_controller, snapshot
from test_stage3c_session_ui import show_sessions


def read_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))


def test_csv_preserves_exact_bytes_unknown_presence_and_private_fields(tmp_path):
    data = snapshot(status=ProcessNetworkStatus.UNAVAILABLE)
    account = replace(data.application_session[0], name='中文,应用".exe',
                      download_bytes=2**80 + 17, active_process_count=0)
    data = replace(data, application_session=(account,))
    payload = session_csv(session_rows(data), exported_at='2026-10-11T00:00:00+00:00',
                          source_status='unavailable')
    row, = read_csv(payload)
    assert payload.startswith(b'\xef\xbb\xbf')
    assert row['application'] == account.name
    assert row['download_bytes'] == str(2**80 + 17)
    assert row['process_count'] == '' and row['process_state'] == '进程状态未知'
    assert row['source_status'] == 'unavailable'
    assert 'executable' not in row and 'account_key' not in row
    assert account.executable.encode() not in payload
    target = tmp_path / '中文 目录.csv'
    target.write_bytes(b'previous document')
    save_csv(str(target), payload)
    assert target.read_bytes() == payload
    assert set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize('name', ['=1+1', '+1', '-1', '@SUM(A1)', '  =1', '\ttext', '\rtext', '\ntext'])
def test_untrusted_text_is_not_a_spreadsheet_formula(name):
    data = snapshot()
    account = replace(data.application_session[0], name=name, executable=name, key=name)
    rows = session_rows(replace(data, application_session=(account,)))
    row, = read_csv(session_csv(rows, exported_at='now', source_status='available', include_identity=True))
    assert row['application'] == row['executable'] == row['account_key'] == "'" + name


def test_export_freezes_search_sort_options_and_snapshot_before_dialog(make_controller, app, monkeypatch, tmp_path):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    _, view = show_sessions(c, app)
    view.search.setText('B.EXE')
    assert view.export_button.isEnabled()
    target = tmp_path / 'result.csv'
    def dialog(*args):
        view.include_identity.setChecked(True)
        view.search.clear()
        c._on_snapshot(replace(data, application_session=()))
        return str(target), 'CSV'
    monkeypatch.setattr(module.QFileDialog, 'getSaveFileName', dialog)
    view.export_button.click()
    row, = read_csv(target.read_bytes())
    assert row['application'] == 'b.exe'
    assert row['download_bytes'] == str(data.application_session[1].download_bytes)
    assert 'account_key' not in row
    assert '1 个账户' in view.export_status.text()
    assert c.latest_snapshot.application_session == ()


def test_search_does_not_delete_accounts_or_change_live_filters(make_controller, app):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    detail, view = show_sessions(c, app)
    original = dict(view._items)
    view.search.setText('no-such-application')
    assert not view.export_button.isEnabled()
    assert all(item.isHidden() for item in view._items.values())
    assert view._items == original
    assert view._snapshot.application_session is data.application_session
    assert detail._network_activity_only.isChecked()
    view.search.clear()
    assert all(not item.isHidden() for item in view._items.values())
    assert view.export_button.isEnabled()


def test_cancel_and_write_failure_leave_totals_and_existing_file(make_controller, app, monkeypatch, tmp_path):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    _, view = show_sessions(c, app)
    monkeypatch.setattr(module.QFileDialog, 'getSaveFileName', lambda *args: ('', ''))
    view.export_button.click()
    assert '取消' in view.export_status.text()
    target = tmp_path / 'existing.csv'
    target.write_bytes(b'original')
    monkeypatch.setattr(module.QFileDialog, 'getSaveFileName', lambda *args: (str(target), ''))
    def fail(*args):
        raise OSError('read-only location')
    monkeypatch.setattr(module, 'save_csv', fail)
    warnings = []
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: warnings.append(args))
    view.export_button.click()
    assert len(warnings) == 1 and '失败' in view.export_status.text()
    assert target.read_bytes() == b'original'
    assert view._snapshot.application_session is data.application_session


def test_atomic_write_failure_never_commits(monkeypatch):
    import net_monitor.ui.session_export as exporter
    calls = []
    class ShortWrite:
        def __init__(self, path): pass
        def setDirectWriteFallback(self, enabled): assert enabled is False
        def open(self, mode): return True
        def write(self, payload): return len(payload) - 1
        def errorString(self): return 'disk full'
        def isOpen(self): return True
        def cancelWriting(self): calls.append('cancel')
        def commit(self): calls.append('commit'); return True
    monkeypatch.setattr(exporter, 'QSaveFile', ShortWrite)
    with pytest.raises(OSError, match='disk full'):
        exporter.save_csv('unused.csv', b'payload')
    assert calls == ['cancel']


def test_export_respects_display_order_and_explicit_identity_opt_in(make_controller, app, monkeypatch, tmp_path):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    _, view = show_sessions(c, app)
    view.tree.sortItems(2, Qt.SortOrder.DescendingOrder)
    view.include_identity.setChecked(True)
    target = tmp_path / 'sorted.csv'
    monkeypatch.setattr(module.QFileDialog, 'getSaveFileName', lambda *args: (str(target), ''))
    view.export_button.click()
    rows = read_csv(target.read_bytes())
    assert [row['account_key'] for row in rows] == [view.tree.topLevelItem(i).key for i in range(4)]
    assert [int(row['upload_bytes']) for row in rows] == sorted(
        [a.upload_bytes for a in data.application_session], reverse=True)
    assert all(row['executable'] for row in rows)


def test_failed_open_does_not_replace_destination(tmp_path):
    parent = tmp_path / 'not-a-directory'
    parent.write_bytes(b'keep')
    with pytest.raises(OSError):
        save_csv(str(parent / 'report.csv'), b'new')
    assert parent.read_bytes() == b'keep'


def test_hidden_live_tab_does_no_tree_work_and_restores_latest(make_controller, app, monkeypatch):
    c = make_controller()
    c._on_snapshot(snapshot())
    detail, view = show_sessions(c, app)
    calls = []
    original = detail._sync_tree
    monkeypatch.setattr(detail, '_sync_tree', lambda *args: calls.append(1) or original(*args))
    for i in range(20):
        c._on_snapshot(replace(snapshot(), process_network_state=ProcessNetworkState(ProcessNetworkStatus.UNAVAILABLE)))
    assert calls == []
    detail.tabs.setCurrentWidget(detail.live_page)
    assert calls == [1]
    assert detail._upload_label.text().endswith('—')
    assert all(view._items[key].text(3) == '—' for key in view._items)


def test_spotlight_recovers_same_frame_after_clear_and_uses_plain_text(make_controller):
    c = make_controller()
    c._on_snapshot(snapshot())
    detail = c.show_details()
    frame = c.projection.frame()
    detail.update_spotlight(frame)
    assert not detail._spotlight_label.isHidden()
    detail.update_spotlight(None)
    assert detail._spotlight_label.isHidden()
    detail.update_spotlight(frame)
    assert not detail._spotlight_label.isHidden()
    assert detail._spotlight_label.textFormat() is Qt.TextFormat.PlainText
