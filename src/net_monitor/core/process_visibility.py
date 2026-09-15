from __future__ import annotations

import ntpath
import os

from net_monitor.core.models import ProcessInfo

_SYSTEM_PIDS = {0, 4}
_SYSTEM_PROCESS_NAMES = {
    "system idle process",
    "system",
    "registry",
    "memory compression",
    "secure system",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "sihost.exe",
    "taskhostw.exe",
}


def _is_within_windows_directory(executable: str, windows_directory: str) -> bool:
    executable_path = ntpath.normcase(ntpath.normpath(executable))
    windows_path = ntpath.normcase(ntpath.normpath(windows_directory))
    prefix = windows_path.rstrip("\\/") + "\\"
    return executable_path == windows_path or executable_path.startswith(prefix)


def is_windows_system_process(
    process: ProcessInfo,
    *,
    windows_directory: str | None = None,
) -> bool:
    """Return True for Windows OS processes that should stay out of the app view.

    The monitor still collects all process/network data. This predicate is only a
    presentation policy: user-facing apps such as Edge or OneDrive remain visible
    because they do not execute from the Windows OS directory.
    """

    if process.pid in _SYSTEM_PIDS:
        return True

    if process.name.casefold() in _SYSTEM_PROCESS_NAMES:
        return True

    executable = process.executable
    if not executable:
        return False

    system_root = windows_directory or os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if system_root and _is_within_windows_directory(executable, system_root):
        return True

    return False


def third_party_processes(processes: tuple[ProcessInfo, ...]) -> tuple[ProcessInfo, ...]:
    """Return the user-facing, non-Windows-system process view."""

    return tuple(process for process in processes if not is_windows_system_process(process))
