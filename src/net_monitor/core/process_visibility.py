from __future__ import annotations

import ntpath
import os

from net_monitor.core.models import ProcessCategory, ProcessInfo

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


def _normalize(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path))


def _is_within_directory(executable: str, directory: str) -> bool:
    executable_path = _normalize(executable)
    directory_path = _normalize(directory).rstrip("\\/")
    return executable_path == directory_path or executable_path.startswith(directory_path + "\\")


def _looks_like_windows_apps(executable: str) -> bool:
    parts = [part.casefold() for part in _normalize(executable).split("\\") if part]
    return len(parts) >= 2 and any(
        parts[index] == "program files" and parts[index + 1] == "windowsapps"
        for index in range(len(parts) - 1)
    )


class ProcessClassifier:
    """Conservative Windows process classifier used only for presentation.

    A process is hidden only when it can be identified as a Windows OS component
    with high confidence. Uncertain entries remain UNKNOWN and stay visible.
    """

    def __init__(self, *, windows_directory: str | None = None) -> None:
        self._windows_directory = (
            windows_directory
            or os.environ.get("SystemRoot")
            or os.environ.get("WINDIR")
        )

    def classify(self, process: ProcessInfo) -> ProcessCategory:
        if process.pid in _SYSTEM_PIDS:
            return ProcessCategory.SYSTEM

        if process.name.casefold() in _SYSTEM_PROCESS_NAMES:
            return ProcessCategory.SYSTEM

        executable = process.executable
        if not executable:
            return ProcessCategory.UNKNOWN

        # WindowsApps contains both Microsoft and third-party packaged apps. Do not
        # hide it merely because it lives under Program Files.
        if _looks_like_windows_apps(executable):
            return ProcessCategory.UNKNOWN

        if self._windows_directory and _is_within_directory(executable, self._windows_directory):
            return ProcessCategory.SYSTEM

        return ProcessCategory.APPLICATION


def is_windows_system_process(
    process: ProcessInfo,
    *,
    windows_directory: str | None = None,
) -> bool:
    """Compatibility predicate for code that only needs a system/non-system answer."""

    return (
        ProcessClassifier(windows_directory=windows_directory).classify(process)
        is ProcessCategory.SYSTEM
    )


def visible_processes(
    processes: tuple[ProcessInfo, ...],
    *,
    show_system: bool = False,
    classifier: ProcessClassifier | None = None,
) -> tuple[ProcessInfo, ...]:
    classifier = classifier or ProcessClassifier()
    if show_system:
        return processes
    return tuple(
        process
        for process in processes
        if classifier.classify(process) is not ProcessCategory.SYSTEM
    )


def third_party_processes(processes: tuple[ProcessInfo, ...]) -> tuple[ProcessInfo, ...]:
    """Backward-compatible default application view (SYSTEM hidden, UNKNOWN shown)."""

    return visible_processes(processes)
