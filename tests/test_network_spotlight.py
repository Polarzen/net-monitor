"""Tests for Network Spotlight pure logic."""
from __future__ import annotations

from dataclasses import dataclass
import pytest

from net_monitor.ui.network_spotlight import (
    SpotlightApplication,
    SpotlightFrame,
    compute_network_spotlight,
)


@dataclass
class FakeProcess:
    pid: int
    create_time: float | None


@dataclass
class FakeGroup:
    key: str
    name: str
    executable: str | None
    processes: tuple[FakeProcess, ...]
    upload_bytes_per_second: float | None
    download_bytes_per_second: float | None


def make_group(key, name, upload, download, pids_with_ctime):
    processes = tuple(FakeProcess(pid, ctime) for pid, ctime in pids_with_ctime)
    return FakeGroup(key, name, "C:\\" + name, processes, upload, download)


def test_foreground_pid_matches_trusted_member():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.foreground is not None
    assert result.foreground.key == "exe:chrome"
    assert result.foreground.upload_bps == 100.0
    assert result.foreground.download_bps == 200.0


def test_foreground_pid_no_match():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=999, source_usable=True)
    assert result.foreground is None


def test_foreground_pid_incomplete_identity():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, None)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.foreground is None


def test_background_total_correct():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
        "exe:discord": make_group("exe:discord", "Discord.exe", 30.0, 70.0, [(300, 3.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.background_upload_bps == 80.0
    assert result.background_download_bps == 870.0
    assert result.background_total_bps == 950.0


def test_dominant_background_correct():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
        "exe:discord": make_group("exe:discord", "Discord.exe", 30.0, 70.0, [(300, 3.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.dominant_background is not None
    assert result.dominant_background.key == "exe:steam"
    assert result.dominant_background.total_bps == 850.0


def test_upload_download_raw_numeric():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.foreground.total_bps == 300.0
    assert result.background_total_bps == 850.0


def test_tiebreak_deterministic():
    groups = {
        "exe:aaa": make_group("exe:aaa", "AAA.exe", 100.0, 100.0, [(100, 1.0)]),
        "exe:bbb": make_group("exe:bbb", "BBB.exe", 100.0, 100.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=None, source_usable=True)
    assert result.dominant_background is not None
    assert result.dominant_background.key == "exe:aaa"


def test_foreground_only_traffic():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.background_total_bps == 0.0
    assert result.background_upload_bps == 0.0
    assert result.background_download_bps == 0.0
    assert result.dominant_background is None


def test_background_only_traffic():
    groups = {
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.foreground is None
    assert result.background_total_bps == 850.0
    assert result.dominant_background is not None
    assert result.dominant_background.key == "exe:steam"


def test_none_not_zero():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", None, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.foreground is not None
    assert result.foreground.upload_bps is None
    assert result.foreground.total_bps is None
    assert result.background_share is None
    assert result.share_reliable is False


def test_unknown_does_not_create_false_ratio():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", None, None, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.background_share is None
    assert result.share_reliable is False


def test_stale_unavailable_no_false_ratio():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=False)
    assert result.source_usable is False
    assert result.background_share is None
    assert result.share_reliable is False


def test_background_share_correct():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.background_share is not None
    assert abs(result.background_share - 850.0 / 1150.0) < 0.001
    assert result.share_reliable is True


def test_empty_groups():
    result = compute_network_spotlight({}, foreground_pid=100, source_usable=True)
    assert result.foreground is None
    assert result.background_total_bps == 0.0
    assert result.dominant_background is None
    assert result.background_share is None


def test_no_foreground_pid():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=None, source_usable=True)
    assert result.foreground is None
    assert result.background_total_bps == 300.0
    assert result.dominant_background is not None
    assert result.dominant_background.key == "exe:chrome"


def test_multiple_pids_same_group():
    groups = {
        "exe:chrome": make_group(
            "exe:chrome", "Chrome.exe", 100.0, 200.0,
            [(100, 1.0), (101, 1.1), (102, 1.2)]
        ),
    }
    result = compute_network_spotlight(groups, foreground_pid=101, source_usable=True)
    assert result.foreground is not None
    assert result.foreground.key == "exe:chrome"


def test_zero_traffic_all_apps():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 0.0, 0.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 0.0, 0.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    assert result.background_total_bps == 0.0
    assert result.background_share is None


def test_background_share_percent():
    groups = {
        "exe:chrome": make_group("exe:chrome", "Chrome.exe", 100.0, 200.0, [(100, 1.0)]),
        "exe:steam": make_group("exe:steam", "Steam.exe", 50.0, 800.0, [(200, 2.0)]),
    }
    result = compute_network_spotlight(groups, foreground_pid=100, source_usable=True)
    percent = result.background_share_percent
    assert percent is not None
    assert percent == 74
