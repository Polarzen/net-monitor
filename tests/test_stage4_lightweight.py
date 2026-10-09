"""Count display work, not wall-clock time; synthetic data is never ETW evidence."""
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QMenu

from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import ProcessNetworkState, ProcessNetworkStatus
from net_monitor.ui.micro_model import DisplayState, PresenceState
from net_monitor.ui.rate_history import RateSample
from net_monitor.ui.sparkline import Sparkline
from test_stage3c_ui import app, make_controller, snapshot, Service


def count_calls(monkeypatch, instance, name):
    calls = []
    original = getattr(instance, name)
    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(instance, name, counted)
    return calls


def test_micro_has_no_curve_or_layout_slot_and_card_keeps_history(make_controller):
    c = make_controller()
    c.show_primary(activate=False)
    c._on_snapshot(snapshot())
    c.projection.clock.now = .5
    c._on_snapshot(snapshot())
    assert (c.micro_window.width(), c.micro_window.height()) == (220, 112)
    assert not c.micro_window.findChildren(Sparkline)
    assert not hasattr(c.micro_window, '_sparkline')
    assert c.micro_window.layout().count() == 4  # Header, download, upload, status.
    c.show_card()
    key = c.projection.frame().selected.key
    expected = c._rate_history.get_series(key)
    assert len(expected) == 2
    assert c.card._sparkline._upload == [s.upload_bytes_per_second for s in expected]
    assert c.card._sparkline._download == [s.download_bytes_per_second for s in expected]
    assert c.card._sparkline.isVisible()


def test_all_hidden_keep_data_without_any_display_work(make_controller, monkeypatch):
    c = make_controller()
    detail = c.show_details()
    detail.close()
    calls = [count_calls(monkeypatch, view, method) for view, method in (
        (c.micro_window, 'apply_frame'), (c.card, 'apply_frame'),
        (c.compact_window, 'apply_snapshot'), (detail, 'apply_snapshot'),
        (detail, '_sync_tree'), (detail.session_view, '_flush'),
        (c.projection, 'frame'), (c._rate_history, 'get_series'), (c._icons, 'request'))]
    data = snapshot()
    for i in range(4):
        c.projection.clock.now = i * .5
        c._on_snapshot(replace(data))
        c._heartbeat_refresh()
    c._on_sampling_failed('hidden failure')
    assert not any(calls)
    assert c.service.closed == 0
    assert len(c._rate_history._series[application_key(data.processes[0])]) == 4
    assert c.projection._accounts == {a.key: a for a in data.application_session}
    assert c._published_state is DisplayState.FAILED


def test_worker_continues_sampling_while_every_window_is_hidden(make_controller, app):
    import time
    from PySide6.QtTest import QTest
    service = Service()
    c = make_controller(service=service, start_worker=True, sampling_interval_ms=50)
    c.tray.available = True
    c.show_primary(activate=False)
    c.show_details().close()
    c._close_primary()
    deadline = time.monotonic() + 3
    while len(service.thread_ids) < 4 and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    app.processEvents()
    assert len(service.thread_ids) >= 4
    assert all(len(series) >= 3 for series in c._rate_history._series.values())
    assert c._rate_history.tracked_keys()
    assert not any(w.isVisible() for w in (c.micro_window, c.compact_window, c.card, c.detail_window))
    assert service.closed == 0
    c.shutdown()
    assert service.closed == 1 and not c._thread.isRunning()


def test_failure_before_first_snapshot_restores_and_updates_message(make_controller):
    c = make_controller()
    c._on_sampling_failed('initial')
    c.show_compact()
    detail = c.show_details()
    for label in (c.compact_window._status_label, detail._network_status_label):
        assert label.text() == '采样失败'
        assert 'initial' in label.toolTip()
    c._on_sampling_failed('second')
    assert 'second' in detail._network_status_label.toolTip()
    assert c.compact_window._upload_value.text() == '—'


def test_topmost_restore_invalidates_presence_and_applies_staleness(make_controller):
    calls = []
    c = make_controller(foreground_pid_reader=lambda: calls.append(1) or 100)
    c._on_snapshot(snapshot())
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    assert c.micro_window.badge_label.text() == '前台'
    c.projection.clock.now = 4
    c.set_always_on_top(True)
    assert c.micro_window.upload_label.text() == '↑ 上传 —'
    assert c.micro_window._frame.presence is PresenceState.UNKNOWN
    assert calls == [1]


@pytest.mark.parametrize('mode', ['micro', 'compact'])
def test_only_visible_primary_receives_updates(make_controller, monkeypatch, mode):
    c = make_controller()
    c.set_mode(mode)
    micro = count_calls(monkeypatch, c.micro_window, 'apply_frame')
    compact = count_calls(monkeypatch, c.compact_window, 'apply_snapshot')
    card = count_calls(monkeypatch, c.card, 'apply_frame')
    history = count_calls(monkeypatch, c._rate_history, 'get_series')
    c._on_snapshot(snapshot())
    c._heartbeat_refresh()
    assert bool(micro) == (mode == 'micro')
    assert bool(compact) == (mode == 'compact')
    assert not card and not history


@pytest.mark.parametrize('view', ['micro', 'compact', 'detail', 'card'])
@pytest.mark.parametrize('state', ['fresh', 'stale', 'failed'])
def test_restore_immediately_uses_effective_snapshot(make_controller, view, state):
    calls = []
    c = make_controller(foreground_pid_reader=lambda: calls.append(1) or 100)
    c._on_snapshot(snapshot())
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    c.show_card()
    detail = c.show_details()
    c.tray.available = True
    c._close_primary()
    detail.close()
    data = snapshot()
    c._on_snapshot(data)
    if state == 'stale':
        c.projection.clock.now += 4
    elif state == 'failed':
        c._on_sampling_failed('hidden')
    before_queries = len(calls)
    before_points = sum(len(s) for s in c._rate_history._series.values())
    if view == 'micro':
        c.show_primary(activate=False)
        text = c.micro_window.upload_label.text()
    elif view == 'compact':
        c.show_compact()
        text = c.compact_window._upload_value.text()
    elif view == 'detail':
        assert c.show_details() is detail
        text = detail._upload_label.text()
    else:
        c.show_card()
        text = c.card.rates_label.text()
    assert ('—' in text) == (state != 'fresh')
    assert len(calls) == before_queries
    assert c.projection.frame().presence is PresenceState.UNKNOWN
    assert c.projection.frame().spotlight.foreground is None
    assert sum(len(s) for s in c._rate_history._series.values()) == before_points
    assert c.latest_snapshot is data
    assert data.process_network[0].upload_bytes_per_second > 0


def test_same_snapshot_deduplicates_trees_but_time_still_expires(make_controller, monkeypatch):
    c = make_controller()
    c.show_compact()
    detail = c.show_details()
    detail.tabs.setCurrentWidget(detail.session_view)
    compact = count_calls(monkeypatch, c.compact_window, 'apply_snapshot')
    tree = count_calls(monkeypatch, detail, '_sync_tree')
    session = count_calls(monkeypatch, detail.session_view, '_flush')
    data = snapshot()
    c._on_snapshot(data)
    counts = (len(compact), len(tree), len(session))
    for _ in range(8):
        c._refresh_views()
        c._on_snapshot(data)
        c.show_details()
    assert (len(compact), len(tree), len(session)) == counts
    c.projection.clock.now = 4
    c._heartbeat_refresh()
    assert len(compact) == counts[0] + 1
    assert len(tree) == counts[1] + 1
    assert c.compact_window._upload_value.text() == '—'
    assert detail._upload_label.text().endswith('—')
    assert all(item.text(3) == '—' for item in detail.session_view._items.values())
    assert len(c._rate_history._series[application_key(data.processes[0])]) == 1


def test_menu_frames_and_window_changes_do_not_record_history_or_query(make_controller, monkeypatch):
    queries = []
    c = make_controller(foreground_pid_reader=lambda: queries.append(1) or 100)
    c._on_snapshot(snapshot())
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    points = sum(len(s) for s in c._rate_history._series.values())
    import net_monitor.ui.controller as controller_module
    class NonblockingMenu(QMenu):
        def exec(self, *_):
            return None
    monkeypatch.setattr(controller_module, 'QMenu', NonblockingMenu)
    timers = tuple(c.findChildren(QTimer))
    for _ in range(3):
        c.projection.frame()
        c.show_menu(QPoint())
        c.show_card()
        c.show_compact()
        c.show_details().close()
        c.show_micro()
    assert queries == [1]
    assert sum(len(s) for s in c._rate_history._series.values()) == points
    assert tuple(c.findChildren(QTimer)) == timers
    assert len(timers) == 3


def test_history_prunes_on_restore_without_fabricating_samples(make_controller):
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    key = application_key(data.processes[0])
    c.projection.clock.now = 61
    c.show_card()
    assert c.card._frame.rate_history == ()
    assert c._rate_history.get_series(key) == ()
    assert not c.card._sparkline.isVisible()
    c._on_snapshot(replace(data, process_network=tuple(
        replace(r, upload_bytes_per_second=None, download_bytes_per_second=None)
        for r in data.process_network)))
    history = c._rate_history.get_series(key)
    assert len(history) == 1 and history[0].timestamp == 61
    assert history[0].upload_bytes_per_second is None


def test_foreground_pid_reuse_invalidates_spotlight_independently_of_selection(make_controller):
    c = make_controller(foreground_pid_reader=lambda: 101)
    data = snapshot()
    c._on_snapshot(data)
    c.show_primary(activate=False)
    c._heartbeat_refresh()
    old = c.projection.frame()
    assert old.selected.key != old.spotlight.foreground.key
    changed = replace(data.processes[1], create_time=555)
    c._on_snapshot(replace(data, processes=(data.processes[0], changed, *data.processes[2:])))
    assert c.projection.frame().spotlight.foreground is None
    assert c.projection.frame().selected == old.selected
    c._heartbeat_refresh()
    assert c.projection.frame().spotlight.foreground is not None


def test_hidden_icon_result_is_cached_without_conversion_or_wrong_key(make_controller, monkeypatch):
    from net_monitor.ui.icon_cache import IconPixels
    c = make_controller()
    data = snapshot()
    c._on_snapshot(data)
    key = application_key(data.processes[0])
    normalized = c._icons.trusted_path(key, data.processes[0].executable)
    pixels = IconPixels(1, 1, bytes((0, 0, 255, 255)))
    c._icons._pending.add(normalized)
    c._icons._results.put_nowait((key, normalized, pixels))
    micro = count_calls(monkeypatch, c.micro_window, 'set_icon')
    card = count_calls(monkeypatch, c.card, 'set_icon')
    c._refresh_views()
    assert c._icons.cache[normalized] is pixels
    assert not micro and not card
    c.follow(application_key(data.processes[1]))
    c.show_primary(activate=False)
    assert c._icon_token[0] == application_key(data.processes[1])
    assert c._current_icon.cacheKey() == c._generic_icon.cacheKey()
    c.follow(key)
    assert c._icon_token == (key, id(pixels))
    assert c._current_icon.cacheKey() != c._generic_icon.cacheKey()
    assert not card  # Hidden card never receives an icon conversion.
    c.show_card()
    assert len(card) == 1
    c._refresh_views()
    assert len(card) == 1


def test_detail_reuses_groups_without_reaggregation_and_keeps_filters(make_controller, monkeypatch):
    import net_monitor.ui.main_window as main
    c = make_controller()
    c._on_snapshot(snapshot())
    aggregation = count_calls(monkeypatch, main, 'aggregate_application_network')
    detail = c.show_details()
    assert not aggregation
    detail._show_system_processes.setChecked(True)
    assert aggregation  # System visibility still uses its own correctly filtered set.


def test_sparkline_preserves_none_gaps_even_among_zero_rates(app, monkeypatch):
    import net_monitor.ui.sparkline as module
    lines = []
    class Painter:
        RenderHint = module.QPainter.RenderHint
        def __init__(self, *_): pass
        def setRenderHint(self, *_): pass
        def setPen(self, *_): pass
        def drawLine(self, *args): lines.append(args)
        def end(self): pass
    monkeypatch.setattr(module, 'QPainter', Painter)
    chart = Sparkline()
    chart.set_data(tuple(RateSample(i, v, None) for i, v in enumerate((0, 0, None, 0, 0))))
    chart.paintEvent(None)
    assert len(lines) == 2
    assert all(not (x1 < 30 < x2) for x1, y1, x2, y2 in lines)
    updates = count_calls(monkeypatch, chart, 'update')
    chart.set_data(chart._samples)
    assert not updates
    chart.close()
