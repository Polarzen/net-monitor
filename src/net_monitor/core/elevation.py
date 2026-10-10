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

    frozen = bool(getattr(sys, "frozen", False))
    executable = str(Path(sys.executable).resolve()) if frozen else gui_python_executable()
    parameters = "" if frozen else subprocess.list2cmdline(["-m", "net_monitor"])
    directory = str(Path(executable).parent) if frozen else os.getcwd()
    # PyInstaller >= 6.9 requires a fresh bootloader environment for an independent
    # restart. ShellExecute has no environment argument; scope this to the launch
    # and restore it even when Windows rejects or cancels the request.
    previous_reset = os.environ.get("PYINSTALLER_RESET_ENVIRONMENT")
    try:
        if frozen:
            os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        result = shell_execute(None, "runas", executable, parameters, directory, 1)
    except OSError:
        return False
    finally:
        if frozen:
            if previous_reset is None:
                os.environ.pop("PYINSTALLER_RESET_ENVIRONMENT", None)
            else:
                os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = previous_reset
    return bool(result) and int(result) > 32
