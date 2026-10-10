"""Read local executable icons into plain BGRA bytes, never Qt GUI objects."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import ntpath
import os

from net_monitor.ui.icon_cache import IconPixels


def read_local_icon(path: str) -> IconPixels | None:
    if os.name != "nt":
        return None
    drive, tail = ntpath.splitdrive(path)
    if len(drive) != 2 or drive[1] != ":" or not tail.startswith(("\\", "/")):
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    # Removable, fixed, CD-ROM and RAM disk only. Never query a network share.
    if kernel.GetDriveTypeW(drive + "\\") not in (2, 3, 5, 6):
        return None

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    handle = wintypes.HANDLE
    shell.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                    ctypes.POINTER(handle), ctypes.POINTER(handle), wintypes.UINT]
    shell.ExtractIconExW.restype = wintypes.UINT
    user.DestroyIcon.argtypes, user.DestroyIcon.restype = [handle], wintypes.BOOL
    user.DrawIconEx.argtypes = [handle, ctypes.c_int, ctypes.c_int, handle, ctypes.c_int,
                               ctypes.c_int, wintypes.UINT, handle, wintypes.UINT]
    user.DrawIconEx.restype = wintypes.BOOL
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [handle], handle
    gdi.DeleteDC.argtypes, gdi.DeleteDC.restype = [handle], wintypes.BOOL
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [handle, handle], handle
    gdi.DeleteObject.argtypes, gdi.DeleteObject.restype = [handle], wintypes.BOOL

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("xppm", wintypes.LONG), ("yppm", wintypes.LONG),
                    ("used", wintypes.DWORD), ("important", wintypes.DWORD)]

    class BitmapInfo(ctypes.Structure):
        _fields_ = [("header", BitmapInfoHeader), ("colors", wintypes.DWORD * 3)]

    gdi.CreateDIBSection.argtypes = [handle, ctypes.POINTER(BitmapInfo), wintypes.UINT,
                                    ctypes.POINTER(ctypes.c_void_p), handle, wintypes.DWORD]
    gdi.CreateDIBSection.restype = handle
    large, small = handle(), handle()
    dc = bitmap = previous = None
    size = 32
    try:
        if not shell.ExtractIconExW(path, 0, ctypes.byref(large), ctypes.byref(small), 1):
            return None
        icon = large.value or small.value
        if not icon:
            return None
        dc = gdi.CreateCompatibleDC(None)
        if not dc:
            return None
        info = BitmapInfo()
        info.header = BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader), size, -size,
                                       1, 32, 0, size * size * 4, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bitmap = gdi.CreateDIBSection(dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        if not bitmap or not bits.value:
            return None
        previous = gdi.SelectObject(dc, bitmap)
        if not previous or previous == ctypes.c_void_p(-1).value:
            previous = None
            return None
        # Opaque local fallback tile also handles legacy icons without alpha.
        background = bytes((43, 36, 32, 255)) * (size * size)
        ctypes.memmove(bits.value, background, len(background))
        if not user.DrawIconEx(dc, 0, 0, icon, size, size, 0, None, 3):
            return None
        pixels = bytearray(ctypes.string_at(bits.value, size * size * 4))
        pixels[3::4] = b"\xff" * (size * size)
        return IconPixels(size, size, bytes(pixels))
    finally:
        if dc and previous:
            gdi.SelectObject(dc, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if dc:
            gdi.DeleteDC(dc)
        for icon in {large.value, small.value} - {None, 0}:
            user.DestroyIcon(icon)
