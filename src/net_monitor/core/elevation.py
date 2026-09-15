from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path


def gui_python_executable() -> str:
    """Return a no-console Python executable when the current venv provides one."""
    executable = Path(sys.executable)
    if os.name != "nt":
        return str(executable)
    if executable.name.casefold() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(executable)


def restart_as_administrator() -> bool:
    """Ask Windows to relaunch Net Monitor with elevation after explicit user action."""
    if os.name != "nt":
        return False

    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    shell_execute.restype = wintypes.HINSTANCE

    parameters = subprocess.list2cmdline(["-m", "net_monitor"])
    result = shell_execute(
        None,
        "runas",
        gui_python_executable(),
        parameters,
        os.getcwd(),
        1,
    )
    return bool(result) and int(result) > 32
