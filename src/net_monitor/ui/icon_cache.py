"""Bounded local icon IO, independent of Qt; only the GUI consumes pixel bytes."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import ntpath
import queue
import threading
from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class IconPixels:
    width: int
    height: int
    bgra: bytes


class IconCache:
    """One lazy IO worker, bounded requests/results and positive/negative LRU.

    request() and poll() are GUI-thread methods. The worker never touches Qt.
    Results retain both the requesting application key and normalized path.
    Native calls are restricted to local volumes by the reader; shutdown never
    starts new IO and reports whether the current native call finished in time.
    """

    def __init__(self, reader: Callable[[str], IconPixels | None], *, capacity: int = 128) -> None:
        self.reader = reader
        self.capacity = max(1, capacity)
        self.cache: OrderedDict[str, IconPixels | None] = OrderedDict()
        self._requests: queue.Queue[tuple[str, str, str] | None] = queue.Queue(maxsize=2)
        self._results: queue.Queue[tuple[str, str, IconPixels | None]] = queue.Queue(maxsize=2)
        self._pending: set[str] = set()
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def trusted_path(key: str, path: str | None) -> str | None:
        if not path or path.startswith(("\\\\", "//")):
            return None
        drive, tail = ntpath.splitdrive(path)
        if len(drive) != 2 or drive[1] != ":" or not tail.startswith(("\\", "/")):
            return None
        normalized = ntpath.normcase(ntpath.normpath(path))
        return normalized if key == f"exe:{normalized}" else None

    def request(self, key: str, path: str | None) -> IconPixels | None:
        normalized = self.trusted_path(key, path)
        if normalized is None or self._closed.is_set():
            return None
        if normalized in self.cache:
            self.cache.move_to_end(normalized)
            return self.cache[normalized]
        if normalized in self._pending or len(self._pending) >= 2:
            return None
        self._pending.add(normalized)
        self._requests.put_nowait((key, normalized, str(path)))
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="NetMonitor-LocalIcon", daemon=True)
            self._thread.start()
        return None

    def poll(self) -> tuple[tuple[str, str, IconPixels | None], ...]:
        completed = []
        while True:
            try:
                key, normalized, pixels = self._results.get_nowait()
            except queue.Empty:
                break
            self._pending.discard(normalized)
            if self._closed.is_set():
                continue
            self.cache[normalized] = pixels
            self.cache.move_to_end(normalized)
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            completed.append((key, normalized, pixels))
        return tuple(completed)

    def _run(self) -> None:
        while not self._closed.is_set():
            request = self._requests.get()
            if request is None or self._closed.is_set():
                break
            key, normalized, path = request
            try:
                pixels = self.reader(path)
            except Exception:
                pixels = None  # Includes negative cache entries; never retry per refresh.
            if not self._closed.is_set():
                self._results.put_nowait((key, normalized, pixels))

    def close(self, timeout: float = 1.0) -> bool:
        self._closed.set()
        while True:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                break
        self._pending.clear()
        try:
            self._requests.put_nowait(None)
        except queue.Full:  # defensive; all producers are on the GUI thread
            pass
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))
        return self._thread is None or not self._thread.is_alive()
