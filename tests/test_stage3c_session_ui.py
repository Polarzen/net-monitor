from dataclasses import replace

import pytest
from PySide6.QtCore import Qt

from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import ApplicationSessionStats, ProcessNetworkState, ProcessNetworkStatus
from net_monitor.ui.micro_model import DisplayState, format_bytes
from net_monitor.ui.theme import DARK_STYLESHEET
from test_stage3c_ui import app, make_controller, snapshot


def show_sessions(controller, app):
    detail = controller.show_details()
    detail.tabs.setCurrentWidget(detail.session_view)
    app.processEvents()
    return detail, detail.session_view


def test_detail_wraps_existing_live_page_without_replacing_tree(make_controller, app):
    c = make_controller()
    c._on_snapshot(snapshot())
    detail = c.show_details()
    tree = detail._tree
    page = detail.live_page
    assert detail.tabs.widget(0) is page
    assert detail.tabs.count() == 2
    detail.tabs.setCurrentWidget(detail.session_view)
    detail.tabs.setCurrentWidget(page)
    assert detail._tree is tree
    assert detail._sampling_worker is None
    assert detail._service is c.service


def test_card_uses_exact_session_account_and_distinguishes_missing_from_zero(make_controller):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    c.show_card()
    account = data.application_session[0]
    assert format_bytes(account.upload_bytes) in c.card.session_totals.values.text()
    c._on_snapshot(replace(data, application_session=()))
    assert c.card.session_totals.values.text() == "无可信累计"
    zero = replace(account, upload_bytes=0, download_bytes=0)
    c._on_snapshot(replace(data, application_session=(zero,)))
    assert c.card.session_totals.values.text().count("0 B") == 2


def test_card_does_not_guess_account_by_name_or_pid(make_controller):
    c = make_controller()
    data = snapshot()
    wrong = replace(data.application_session[0], key="process:100:1.0", executable=None)
    c._on_snapshot(replace(data, application_session=(wrong,)))
    c.show_card()
    assert c.projection.frame().account is None
    assert c.card.session_totals.values.text() == "无可信累计"


def test_exited_accounts_survive_live_filters_and_keep_exact_key(make_controller, app):
    c = make_controller()
    data = snapshot()
    old = ApplicationSessionStats("process:77:1.0", "退出的应用.exe", None, 2**80+17, 8, 0)
    c._on_snapshot(replace(data, application_session=data.application_session + (old,)))
    detail, view = show_sessions(c, app)
    assert len(view._items) == 5
    detail._show_system_processes.setChecked(True)
    detail._network_activity_only.setChecked(False)
    item = view._items[old.key]
    assert item.text(2) == format_bytes(old.upload_bytes)
    assert item.text(4) == "未运行"
    assert item.text(5) == old.key
    assert len(view._items) == 5


def test_sorting_uses_python_raw_bytes_beyond_qvariant_integer_range(make_controller, app):
    c = make_controller()
    data = snapshot()
    a = replace(data.application_session[0], download_bytes=900*1024)
    b = replace(data.application_session[1], download_bytes=1024**2)
    huge = replace(data.application_session[2], download_bytes=2**80+17)
    c._on_snapshot(replace(data, application_session=(a, huge, b)))
    _, view = show_sessions(c, app)
    view.tree.sortItems(1, Qt.SortOrder.DescendingOrder)
    assert [view.tree.topLevelItem(i).key for i in range(3)] == [huge.key, b.key, a.key]
    assert view._items[huge.key].sort_values[1] == 2**80+17


def test_updates_reuse_rows_and_metadata_never_adds_balance(make_controller, app):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    _, view = show_sessions(c, app)
    key = data.application_session[0].key
    item = view._items[key]
    item.setSelected(True)
    for _ in range(20):
        c._on_snapshot(data)
    assert view._items[key] is item and item.isSelected()
    renamed = replace(data.application_session[0], name="新名称.exe", executable=None)
    c._on_snapshot(replace(data, application_session=(renamed, *data.application_session[1:])))
    assert view._items[key] is item
    assert item.text(0) == "新名称.exe" and item.text(2) == format_bytes(renamed.upload_bytes)
    assert len(view._items) == 4


def test_hidden_session_tab_defers_widget_updates(make_controller, app, monkeypatch):
    c = make_controller()
    detail = c.show_details()
    calls = []
    original = detail.session_view._flush
    monkeypatch.setattr(detail.session_view, "_flush", lambda: calls.append(True) or original())
    c._on_snapshot(snapshot())
    assert calls == []
    detail.tabs.setCurrentWidget(detail.session_view)
    app.processEvents()
    assert calls == [True]
    assert len(detail.session_view._items) == 4


@pytest.mark.parametrize("failed", [False, True])
def test_stale_or_failed_views_retain_totals_but_not_old_presence(make_controller, app, failed):
    c = make_controller()
    data = snapshot()
    account = replace(data.application_session[0], active_process_count=0)
    c._on_snapshot(replace(data, processes=(), process_network=(), application_session=(account,)))
    c.follow(account.key)
    c.show_card()
    _, view = show_sessions(c, app)
    if failed:
        c.sampling_failed.emit("test failure")
    else:
        c.projection.clock.now = 4.0
        c._refresh_views()
    item = view._items[account.key]
    assert item.text(3) == "—" and item.text(4) == "进程状态未知"
    assert item.text(2) == format_bytes(account.upload_bytes)
    assert format_bytes(account.upload_bytes) in c.card.session_totals.values.text()
    assert c.projection.frame().upload is None


def test_focus_exit_is_not_inferred_from_unknown_identity(make_controller):
    c = make_controller()
    data = snapshot()
    account = data.application_session[0]
    c._on_snapshot(data)
    c.follow(account.key)
    unknown = replace(data.processes[0], executable=None, create_time=None)
    c._on_snapshot(replace(data, processes=(unknown,), process_network=(),
                           application_session=(replace(account, active_process_count=0),)))
    assert c.projection.frame().state is DisplayState.UNKNOWN
    assert c.projection.frame().upload is None


def test_card_and_tab_do_not_reset_accounts_across_modes(make_controller, app):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    detail, view = show_sessions(c, app)
    key = data.application_session[0].key
    for mode in ("compact", "micro", "compact", "micro"):
        c.set_mode(mode)
        c.follow(key)
        c.show_card()
        detail.close()
        c.show_details()
        assert view._snapshot.application_session is data.application_session
        assert c.projection.frame().account is data.application_session[0]
    assert c.service.closed == 0


def test_compact_partial_unknown_and_unavailable_are_not_all_idle(make_controller):
    c = make_controller()
    data = snapshot(idle=True)
    rows = (replace(data.process_network[0], upload_bytes_per_second=None), *data.process_network[1:])
    c._on_snapshot(replace(data, process_network=rows))
    assert "未知" in c.compact_window._empty_label.text()
    c._on_snapshot(replace(data, process_network_state=ProcessNetworkState(ProcessNetworkStatus.UNAVAILABLE)))
    assert "未知" in c.compact_window._active_count.text()


@pytest.mark.parametrize("rate", [0.0, 0.05, 1023.0, 1024.0, 1024**3, 1e100, None])
def test_themed_micro_rate_glyphs_and_fixed_layout(make_controller, app, rate):
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLESHEET)
    try:
        c = make_controller()
        data = snapshot()
        rows = (replace(data.process_network[0], upload_bytes_per_second=rate, download_bytes_per_second=rate),
                *data.process_network[1:])
        c._on_snapshot(replace(data, process_network=rows))
        c.follow(application_key(data.processes[0]))
        c.show_primary(activate=False)
        app.processEvents()
        assert (c.micro_window.width(), c.micro_window.height()) == (112, 72)
        for widget in (c.micro_window.upload_label, c.micro_window.download_label):
            assert widget.fontMetrics().horizontalAdvance(widget.text()) <= widget.contentsRect().width()
            assert widget.fontMetrics().height() <= widget.contentsRect().height()
    finally:
        app.setStyleSheet(previous)


def test_permission_warning_is_visible_even_while_focused(make_controller):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    c.follow(data.application_session[0].key)
    c._on_snapshot(replace(data, process_network_state=ProcessNetworkState(ProcessNetworkStatus.PERMISSION_DENIED)))
    assert c.micro_window.badge_label.text() == "!"
    assert c.projection.frame().focused
    c.show_card()
    assert c.card.restart_button.isVisible()
