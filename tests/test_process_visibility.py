from __future__ import annotations

from net_monitor.core.models import ProcessCategory, ProcessInfo
from net_monitor.core.process_visibility import (
    ProcessClassifier,
    is_windows_system_process,
    third_party_processes,
    visible_processes,
)


def classifier() -> ProcessClassifier:
    return ProcessClassifier(windows_directory=r"C:\Windows")


def test_core_windows_processes_are_system() -> None:
    classify = classifier().classify
    assert classify(ProcessInfo(0, "System Idle Process")) is ProcessCategory.SYSTEM
    assert classify(ProcessInfo(4, "System")) is ProcessCategory.SYSTEM
    assert classify(ProcessInfo(100, "svchost.exe")) is ProcessCategory.SYSTEM
    assert classify(
        ProcessInfo(200, "SearchHost.exe", executable=r"C:\Windows\SystemApps\SearchHost.exe")
    ) is ProcessCategory.SYSTEM
    assert classify(
        ProcessInfo(201, "legacy.exe", executable=r"C:\WINDOWS\SysWOW64\legacy.exe")
    ) is ProcessCategory.SYSTEM
    assert classify(
        ProcessInfo(202, "component.exe", executable=r"C:\Windows\WinSxS\component.exe")
    ) is ProcessCategory.SYSTEM


def test_user_facing_apps_are_application() -> None:
    classify = classifier().classify
    assert classify(
        ProcessInfo(300, "chrome.exe", executable=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    ) is ProcessCategory.APPLICATION
    assert classify(
        ProcessInfo(400, "steam.exe", executable=r"C:\Program Files (x86)\Steam\steam.exe")
    ) is ProcessCategory.APPLICATION
    assert classify(
        ProcessInfo(500, "OneDrive.exe", executable=r"C:\Users\User\AppData\Local\Microsoft\OneDrive\OneDrive.exe")
    ) is ProcessCategory.APPLICATION
    assert classify(
        ProcessInfo(600, "game.exe", executable=r"D:\Games\Example\game.exe")
    ) is ProcessCategory.APPLICATION


def test_unknown_entries_remain_visible() -> None:
    classify = classifier().classify
    unknown_no_exe = ProcessInfo(700, "vendor-agent.exe")
    unknown_windows_app = ProcessInfo(
        701,
        "store-app.exe",
        executable=r"C:\Program Files\WindowsApps\Vendor.App_1.0\store-app.exe",
    )
    assert classify(unknown_no_exe) is ProcessCategory.UNKNOWN
    assert classify(unknown_windows_app) is ProcessCategory.UNKNOWN
    assert visible_processes((unknown_no_exe, unknown_windows_app), classifier=classifier()) == (
        unknown_no_exe,
        unknown_windows_app,
    )


def test_windows_prefix_lookalike_is_not_hidden() -> None:
    process = ProcessInfo(800, "app.exe", executable=r"C:\WindowsSomething\app.exe")
    assert classifier().classify(process) is ProcessCategory.APPLICATION
    assert not is_windows_system_process(process, windows_directory=r"C:\Windows")


def test_system_visibility_toggle_preserves_unknown_and_application() -> None:
    processes = (
        ProcessInfo(4, "System"),
        ProcessInfo(101, "svchost.exe", executable=r"C:\Windows\System32\svchost.exe"),
        ProcessInfo(202, "steam.exe", executable=r"D:\Steam\steam.exe"),
        ProcessInfo(303, "mystery.exe"),
    )
    assert third_party_processes(processes) == (processes[2], processes[3])
    assert visible_processes(processes, classifier=classifier()) == (processes[2], processes[3])
    assert visible_processes(processes, show_system=True, classifier=classifier()) == processes
