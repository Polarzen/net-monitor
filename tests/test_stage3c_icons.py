from __future__ import annotations

import threading
import time

from net_monitor.ui.icon_cache import IconCache, IconPixels
from net_monitor.ui.windows_icons import read_local_icon

PATH = r"D:\Apps\a.exe"
KEY = r"exe:d:\apps\a.exe"


def wait_results(cache):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        results = cache.poll()
        if results:
            return results
        time.sleep(0.001)
    raise AssertionError("icon worker did not complete")


def test_local_only_and_exact_key():
    for path in (None, r"\\server\share\a.exe", "https://example.test/icon", "a.exe", r"D:a.exe"):
        assert IconCache.trusted_path(KEY, path) is None
    assert IconCache.trusted_path("process:1:2.0", PATH) is None
    assert IconCache.trusted_path(KEY, PATH) == r"d:\apps\a.exe"


def test_icon_io_off_main_thread_cached_and_bound_to_original_key():
    calls = []
    pixels = IconPixels(1, 1, b"\0\0\0\xff")
    main_thread = threading.get_ident()
    def read(path):
        calls.append((path, threading.get_ident()))
        return pixels
    cache = IconCache(read)
    try:
        assert cache.request(KEY, PATH) is None
        completed = wait_results(cache)
        assert completed == ((KEY, r"d:\apps\a.exe", pixels),)
        for _ in range(20):
            assert cache.request(KEY, PATH) is pixels
        assert len(calls) == 1 and calls[0][1] != main_thread
    finally:
        assert cache.close()
    assert cache.close()


def test_failure_is_negative_cached_and_capacity_is_bounded():
    calls = []
    def fail(path):
        calls.append(path)
        raise OSError("unreadable")
    cache = IconCache(fail, capacity=2)
    try:
        for name in ("a", "b", "c"):
            path = rf"D:\Apps\{name}.exe"
            key = "exe:" + path.lower()
            cache.request(key, path)
            wait_results(cache)
            assert cache.request(key, path) is None
        assert len(calls) == 3
        assert len(cache.cache) == 2
    finally:
        assert cache.close()


def test_pending_work_and_close_are_bounded():
    release = threading.Event()
    began = threading.Event()
    def blocked(path):
        began.set()
        release.wait(2)
        return None
    cache = IconCache(blocked)
    cache.request(KEY, PATH)
    assert began.wait(1)
    for index in range(20):
        cache.request(rf"exe:d:\apps\{index}.exe", rf"D:\Apps\{index}.exe")
    assert len(cache._pending) <= 2
    assert not cache.close(timeout=0)
    release.set()
    assert cache.close(timeout=1)
    assert cache.request(KEY, PATH) is None
    assert not cache.poll()


def test_native_reader_rejects_remote_and_relative_paths():
    assert read_local_icon(r"\\server\share\app.exe") is None
    assert read_local_icon("relative.exe") is None
