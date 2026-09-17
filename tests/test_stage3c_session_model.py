from dataclasses import replace

import pytest

from net_monitor.core.models import (
    ApplicationSessionStats, MonitorSnapshot, ProcessInfo, ProcessNetworkState,
    ProcessNetworkStatus, SystemNetworkStats,
)
from net_monitor.ui.session_model import observed_process_count, session_rows


def account(key="exe:d:\\apps\\a.exe", *, name="A.exe", active=1, upload=7, download=11):
    return ApplicationSessionStats(key, name, None, upload, download, active)


def snapshot(accounts=(), *, status=ProcessNetworkStatus.AVAILABLE, processes=()):
    return MonitorSnapshot(SystemNetworkStats(0, 0, 0, 0), processes, (),
                           ProcessNetworkState(status), accounts)


def test_rows_consume_exact_accounts_without_live_process_traversal():
    old = account(active=0, upload=2**80 + 17)
    rows = session_rows(snapshot((old,)))
    assert len(rows) == 1 and rows[0].account is old
    assert rows[0].account.upload_bytes == 2**80 + 17
    assert rows[0].presence == "未运行"


def test_repeated_snapshot_does_not_integrate_or_increment_totals():
    item = account()
    data = snapshot((item,))
    for _ in range(200):
        rows = session_rows(data)
        assert rows[0].account is item
        assert rows[0].account.upload_bytes == 7


def test_metadata_replacement_keeps_one_account_and_original_raw_bytes():
    first = account()
    later = replace(first, name="renamed.exe", executable=r"D:\Recovered\renamed.exe")
    assert session_rows(snapshot((first,)))[0].account.upload_bytes == 7
    rows = session_rows(snapshot((later,)))
    assert len(rows) == 1 and rows[0].account is later
    assert rows[0].account.key == first.key


def test_identical_names_do_not_merge_distinct_keys():
    a = account("process:100:1.0", name="same.exe", active=0)
    b = account("process:100:2.0", name="same.exe", active=1)
    rows = session_rows(snapshot((b, a)))
    assert [row.account.key for row in rows] == [a.key, b.key]


def test_duplicate_account_projection_does_not_double_count():
    item = account()
    rows = session_rows(snapshot((item, item)))
    assert len(rows) == 1 and rows[0].account.upload_bytes == 7


@pytest.mark.parametrize("status", [ProcessNetworkStatus.STARTING, ProcessNetworkStatus.PERMISSION_DENIED,
                                    ProcessNetworkStatus.UNAVAILABLE, ProcessNetworkStatus.STOPPED])
def test_unusable_source_never_certifies_account_exit(status):
    item = account(active=0)
    row = session_rows(snapshot((item,), status=status))[0]
    assert row.process_count is None
    assert row.presence == "进程状态未知"
    assert row.account is item


def test_zero_count_with_missing_identity_remains_inconclusive():
    item = account(active=0)
    unknown = ProcessInfo(400, "unknown.exe", create_time=None)
    data = snapshot((item,), processes=(unknown,))
    assert observed_process_count(item, data) is None
    assert session_rows(data)[0].presence == "进程状态未知"


def test_process_count_is_not_current_network_activity():
    item = account(active=3, upload=0, download=0)
    row = session_rows(snapshot((item,)))[0]
    assert row.process_count == 3
    assert row.presence == "最近枚举有进程"
    assert "联网" not in row.presence
    assert row.account.upload_bytes == row.account.download_bytes == 0


def test_unknown_historical_category_account_is_preserved():
    item = account("process:700:4.0", name="unknown.exe", active=0)
    row = session_rows(snapshot((item,)))[0]
    assert row.account is item and row.account.executable is None
    assert not hasattr(row, "category")


def test_no_account_is_not_a_zero_balance():
    assert session_rows(snapshot()) == ()


def test_starting_snapshot_ages_when_updates_stop():
    from test_stage3c_model import projection, snapshot
    from net_monitor.ui.micro_model import DisplayState
    model, clock = projection()
    model.receive(snapshot(status=ProcessNetworkStatus.STARTING))
    clock.advance(3.99)
    assert model.frame().state is DisplayState.STARTING
    clock.advance(.01)
    assert model.frame().state is DisplayState.STALE
    assert model.frame().upload is None
    model.receive(snapshot(status=ProcessNetworkStatus.STARTING))
    assert model.frame().state is DisplayState.STARTING


def test_zero_account_with_unknown_process_identity_cannot_certify_exit():
    from test_stage3c_model import projection, snapshot, account_for
    from net_monitor.ui.micro_model import DisplayState
    model, _ = projection()
    data = snapshot()
    account = account_for(data)
    model.receive(replace(data, application_session=(account,)))
    assert model.follow(account.key)
    unknown = replace(data.processes[0], executable=None, create_time=None)
    model.receive(replace(data, processes=(unknown,), process_network=(),
                          application_session=(replace(account, active_process_count=0),)))
    assert model.frame().state is DisplayState.UNKNOWN
    assert model.frame().account.upload_bytes == account.upload_bytes
    assert model.frame().upload is None
