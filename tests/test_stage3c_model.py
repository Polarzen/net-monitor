from dataclasses import replace
import math

import pytest

from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import (
    ApplicationSessionStats, MonitorSnapshot, ProcessInfo, ProcessNetworkState,
    ProcessNetworkStats, ProcessNetworkStatus, SystemNetworkStats,
)
from net_monitor.core.process_visibility import ProcessClassifier
from net_monitor.ui.micro_model import DisplayState, MicroProjection, format_bytes, format_rate


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now
    def advance(self, amount):
        self.now += amount


def snapshot(rates=(("A", 10.0, 20.0),), *, accounts=(), status=ProcessNetworkStatus.AVAILABLE):
    processes = tuple(ProcessInfo(100 + i, name, fr"D:\Apps\{name}.exe", create_time=float(i + 1))
                      for i, (name, _, _) in enumerate(rates))
    rows = tuple(ProcessNetworkStats(p.pid, p.name, 123, 456, up, down)
                 for p, (_, up, down) in zip(processes, rates, strict=True))
    return MonitorSnapshot(SystemNetworkStats(1, 2, 100000, 200000), processes, rows,
                           ProcessNetworkState(status), accounts)


def projection():
    clock = Clock()
    return MicroProjection(clock=clock, classifier=ProcessClassifier(windows_directory=r"C:\Windows")), clock


def account_for(snap, index=0, *, upload=123, download=456, active=1):
    p = snap.processes[index]
    return ApplicationSessionStats(application_key(p), p.name, p.executable, upload, download, active)


def test_starting_and_no_first_update_timeout():
    model, clock = projection()
    assert model.frame().state is DisplayState.STARTING
    assert model.frame().upload is None
    clock.advance(4)
    assert model.frame().state is DisplayState.STALE


@pytest.mark.parametrize("value,expected", [(None, "—"), (0, "0 B/s"), (0.001, "<0.1 B/s"),
    (0.1, "0.1 B/s"), (1024, "1 KiB/s"), (1024**4, "1 TiB/s"), (float('nan'), "—"),
    (float('inf'), "—"), (-1, "—")])
def test_rate_units_and_unknown(value, expected):
    assert format_rate(value) == expected


def test_bytes_keep_exact_large_integer():
    value = 2**80 + 17
    assert format_bytes(value) == f"{value:,} B"
    assert format_bytes(None) == "—"


@pytest.mark.parametrize("status,state", [
    (ProcessNetworkStatus.STARTING, DisplayState.STARTING),
    (ProcessNetworkStatus.PERMISSION_DENIED, DisplayState.PERMISSION),
    (ProcessNetworkStatus.UNAVAILABLE, DisplayState.UNAVAILABLE),
    (ProcessNetworkStatus.STOPPED, DisplayState.UNAVAILABLE),
])
def test_source_states_never_show_old_positive_rate(status, state):
    model, _ = projection()
    model.receive(snapshot(status=status))
    assert model.frame().state is state
    assert model.frame().upload is None
    assert not model.frame().top
    displayed = model.display_snapshot()
    assert displayed.process_network[0].upload_bytes_per_second is None


def test_zero_is_idle_not_exit_and_none_is_unknown():
    model, _ = projection()
    model.receive(snapshot((("A", 0, 0),)))
    assert model.frame().state is DisplayState.IDLE
    model.receive(snapshot((("A", None, 0),)))
    assert model.frame().state is DisplayState.UNKNOWN
    assert model.frame().upload is None


def test_partial_unknown_does_not_claim_all_apps_idle():
    model, _ = projection()
    model.receive(snapshot((("A", 0, 0), ("B", None, None))))
    assert model.frame().partial_unknown
    assert "不能判断全部空闲" in model.frame().message


def test_empty_available_is_not_a_claim_about_whole_machine():
    model, _ = projection()
    model.receive(snapshot(()))
    assert model.frame().state is DisplayState.EMPTY
    assert model.frame().upload is None


def test_raw_ranking_and_stable_ties():
    model, _ = projection()
    model.receive(snapshot((("Z", 900*1024, 0), ("B", 1024*1024, 0), ("A", 1024*1024, 0))))
    assert [app.choice.name for app in model.frame().top] == ["A.exe", "B.exe", "Z.exe"]
    assert model.frame().selected.name == "A.exe"
    model.receive(snapshot((("A", 1024*1024, 0), ("Z", 900*1024, 0), ("B", 1024*1024, 0))))
    assert model.frame().selected.name == "A.exe"


def test_challenger_needs_continuous_received_evidence_not_timer_ticks():
    model, clock = projection()
    model.receive(snapshot((("A", 10, 0), ("B", 5, 0))))
    clock.advance(.5)
    model.receive(snapshot((("A", 10, 0), ("B", 20, 0))))
    assert model.frame().selected.name == "A.exe"
    assert model.frame().top[0].choice.name == "B.exe"
    clock.advance(1.99)
    model.receive(snapshot((("A", 10, 0), ("B", 20, 0))))
    assert model.frame().selected.name == "A.exe"
    clock.advance(.01)
    assert model.frame().selected.name == "A.exe"  # viewing is not a new sample
    model.receive(snapshot((("A", 10, 0), ("B", 20, 0))))
    assert model.frame().selected.name == "B.exe"


def test_challenger_interruption_resets_debounce():
    model, clock = projection()
    model.receive(snapshot((("A", 20, 0), ("B", 10, 0))))
    clock.advance(.5)
    model.receive(snapshot((("A", 20, 0), ("B", 30, 0))))
    clock.advance(1)
    model.receive(snapshot((("A", 40, 0), ("B", 30, 0))))
    clock.advance(1)
    model.receive(snapshot((("A", 20, 0), ("B", 30, 0))))
    assert model.frame().selected.name == "A.exe"


def test_current_zero_switches_immediately_and_never_extends_positive_rate():
    model, _ = projection()
    model.receive(snapshot((("A", 20, 0), ("B", 10, 0))))
    model.receive(snapshot((("A", 0, 0), ("B", 10, 0))))
    assert model.frame().selected.name == "B.exe"
    assert model.frame().upload == 10
    model.receive(snapshot((("A", 0, 0), ("B", 0, 0))))
    assert model.frame().upload == 0


def test_staleness_masks_rates_without_mutating_snapshot_or_totals():
    model, clock = projection()
    original = snapshot()
    account = account_for(original)
    original = replace(original, application_session=(account,))
    model.receive(original)
    assert model.display_snapshot() is original
    clock.advance(4)
    assert model.frame().state is DisplayState.STALE
    assert model.frame().account is account
    masked = model.display_snapshot()
    assert masked is not original
    assert masked.application_session is original.application_session
    assert masked.process_network[0].upload_bytes_per_second is None
    assert original.process_network[0].upload_bytes_per_second == 10
    model.receive(original)
    assert model.frame().state is DisplayState.ACTIVE


def test_failed_sample_does_not_infer_exit_or_reset_confirmed_total():
    model, _ = projection()
    original = snapshot()
    account = account_for(original)
    model.receive(replace(original, application_session=(account,)))
    assert model.follow(account.key)
    model.fail("test failure")
    assert model.frame().state is DisplayState.FAILED
    assert model.frame().account is account
    assert model.frame().upload is None


def test_follow_does_not_get_stolen_and_unfollow_returns_to_auto():
    model, _ = projection()
    original = snapshot((("A", 20, 0), ("B", 10, 0)))
    model.receive(original)
    key = application_key(original.processes[1])
    assert model.follow(key)
    model.receive(snapshot((("B", 0, 0), ("A", 999, 0))))
    assert model.frame().selected.key == key
    assert model.frame().state is DisplayState.IDLE
    model.unfollow()
    assert model.frame().selected.name == "A.exe"
    assert not model.frame().focused


def test_chooser_includes_idle_app_outside_top3_and_actions_bind_keys():
    model, _ = projection()
    original = snapshot(tuple((name, value, 0) for name, value in zip("ABCD", (40, 30, 20, 0))))
    model.receive(original)
    idle_key = application_key(original.processes[3])
    assert len(model.frame().top) == 3
    assert any(c.key == idle_key for c in model.choices())
    model.receive(snapshot((("D", 0, 0), ("C", 20, 0), ("B", 30, 0), ("A", 40, 0))))
    assert model.follow(idle_key)
    assert model.frame().selected.name == "D.exe"
    assert not model.follow("missing-key")


def test_not_running_requires_fresh_account_zero_not_just_missing_row():
    model, _ = projection()
    original = snapshot()
    account = account_for(original)
    model.receive(replace(original, application_session=(account,)))
    assert model.follow(account.key)
    model.receive(snapshot(()))
    assert model.frame().state is DisplayState.UNKNOWN
    model.receive(snapshot((), accounts=(replace(account, active_process_count=0),)))
    assert model.frame().state is DisplayState.NOT_RUNNING
    assert model.frame().account.upload_bytes == 123
    model.receive(snapshot((), accounts=(replace(account, active_process_count=0),),
                           status=ProcessNetworkStatus.UNAVAILABLE))
    assert model.frame().state is DisplayState.UNAVAILABLE


def test_untrusted_pid_only_key_cannot_be_followed_or_linked_to_totals():
    model, _ = projection()
    original = snapshot()
    process = replace(original.processes[0], executable=None, create_time=None)
    original = replace(original, processes=(process,))
    model.receive(original)
    assert not model.follow(application_key(process))
    assert model.frame().account is None
    assert model.frame().state is DisplayState.UNKNOWN


def test_no_name_or_pid_guess_when_path_recovers_or_process_restarts():
    model, _ = projection()
    original = snapshot()
    process = replace(original.processes[0], executable=None)
    old_account = ApplicationSessionStats(application_key(process), process.name, None, 100, 200, 1)
    model.receive(replace(original, processes=(process,), application_session=(old_account,)))
    assert model.follow(old_account.key)
    model.receive(replace(original, application_session=(old_account,)))
    assert model.frame().state is DisplayState.UNKNOWN
    assert model.frame().account is old_account
    model.unfollow()
    assert model.frame().account is None  # exe key does not match the locked process key
    changed = replace(process, create_time=999)
    model.receive(replace(original, processes=(changed,), application_session=(old_account,)))
    assert model.frame().account is None


def test_repeating_snapshot_or_metadata_changes_never_add_bytes_in_ui():
    model, _ = projection()
    original = snapshot()
    account = account_for(original, upload=2**64+1)
    original = replace(original, application_session=(account,))
    for _ in range(100):
        model.receive(original)
        model.frame()
    assert model.frame().account is account
    assert model.frame().account.upload_bytes == 2**64+1


def test_system_hidden_unknown_visible_without_using_system_total():
    model, _ = projection()
    original = snapshot((("system", 99999, 0), ("user", 5, 6), ("unknown", 4, 5)))
    processes = (replace(original.processes[0], executable=r"C:\Windows\System32\svchost.exe"),
                 original.processes[1], replace(original.processes[2], executable=None))
    model.receive(replace(original, processes=processes))
    assert len(model.frame().top) == 2
    assert model.frame().upload == 5
    assert model.frame().download == 6


def test_retired_unknown_category_account_remains_selectable():
    model, _ = projection()
    account = ApplicationSessionStats("process:99:1.0", "unknown.exe", None, 9, 10, 0)
    model.receive(snapshot((), accounts=(account,)))
    assert model.follow(account.key)
    assert model.frame().account is account
    assert model.frame().state is DisplayState.NOT_RUNNING
