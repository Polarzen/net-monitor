from __future__ import annotations

from net_monitor.core.models import ProcessInfo
from net_monitor.core.process_visibility import is_windows_system_process, third_party_processes


def test_core_windows_processes_are_hidden() -> None:
    assert is_windows_system_process(ProcessInfo(4, "System"), windows_directory=r"C:\Windows")
    assert is_windows_system_process(ProcessInfo(100, "svchost.exe"), windows_directory=r"C:\Windows")
    assert is_windows_system_process(
        ProcessInfo(200, "SearchHost.exe", executable=r"C:\Windows\SystemApps\SearchHost.exe"),
        windows_directory=r"C:\Windows",
    )


def test_user_facing_apps_remain_visible() -> None:
    assert not is_windows_system_process(
        ProcessInfo(300, "chrome.exe", executable=r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        windows_directory=r"C:\Windows",
    )
    assert not is_windows_system_process(
        ProcessInfo(400, "msedge.exe", executable=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        windows_directory=r"C:\Windows",
    )
    assert not is_windows_system_process(
        ProcessInfo(500, "OneDrive.exe", executable=r"C:\Users\User\AppData\Local\Microsoft\OneDrive\OneDrive.exe"),
        windows_directory=r"C:\Windows",
    )


def test_unknown_process_without_executable_is_kept_unless_known_system_name() -> None:
    assert not is_windows_system_process(ProcessInfo(600, "vendor-agent.exe"), windows_directory=r"C:\Windows")
    assert is_windows_system_process(ProcessInfo(700, "Registry"), windows_directory=r"C:\Windows")


def test_third_party_processes_preserve_only_non_system_entries() -> None:
    processes = (
        ProcessInfo(4, "System"),
        ProcessInfo(101, "svchost.exe", executable=r"C:\Windows\System32\svchost.exe"),
        ProcessInfo(202, "steam.exe", executable=r"D:\Steam\steam.exe"),
    )
    assert third_party_processes(processes) == (processes[2],)
