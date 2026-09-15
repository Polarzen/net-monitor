from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes


def restart_as_administrator() -> bool:
    """Ask Windows to relaunch Net Monitor with elevation.

    Elevation is always initiated by an explicit user action. The current
    process is not terminated here; the caller decides what to do after a
    successful ShellExecuteW request.
    """

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
        sys.executable,
        parameters,
        os.getcwd(),
        1,
    )
    return bool(result) and int(result) > 32
