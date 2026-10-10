"""Small, lazy Win32 foreground-window boundary for the UI projection."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


def read_foreground_pid() -> int | None:
    """Return the current foreground PID, or ``None`` on any query failure.

    The wrapper deliberately asks Win32 only for the foreground HWND and its
    owning PID. It does not enumerate windows/processes or retain a handle.
    Loading the user32 entry point inside the call keeps this boundary lazy and
    makes the default dependency straightforward to replace in tests.
    """

    if os.name != "nt":
        return None
    try:
        user32 = ctypes.windll.user32
        get_foreground_window = user32.GetForegroundWindow
        get_window_thread_process_id = user32.GetWindowThreadProcessId
        # ctypes defaults are unsafe for HWND-sized values. Real WinDLL
        # functions expose these attributes; test doubles may be bound
        # methods, so keep their behavior while tolerating immutable callables.
        try:
            get_foreground_window.restype = wintypes.HWND
            get_window_thread_process_id.argtypes = (
                wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
            get_window_thread_process_id.restype = wintypes.DWORD
        except (AttributeError, TypeError):
            pass
        hwnd = get_foreground_window()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        if not get_window_thread_process_id(hwnd, ctypes.byref(pid)):
            return None
        value = int(pid.value)
        return value if value > 0 else None
    except Exception:
        return None


# A callable alias makes the injection point self-documenting without adding
# another object, thread, timer, or service.
ForegroundPidReader = read_foreground_pid
