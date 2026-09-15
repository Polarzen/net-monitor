from __future__ import annotations

import ctypes
import threading
import uuid
from collections.abc import Callable

from net_monitor.collectors.etw.api import (
    CONTROLTRACE_ID,
    EVENT_RECORD,
    EVENT_RECORD_CALLBACK,
    ETW_OPEN_TRACE_OPTIONS,
    EtwApi,
    EtwError,
    GUID,
    PROCESSTRACE_HANDLE,
    TRACEHANDLE,
    allocate_trace_properties,
    raise_for_status,
)
from net_monitor.collectors.etw.constants import (
    ERROR_CANCELLED,
    ERROR_SUCCESS,
    EVENT_CONTROL_CODE_DISABLE_PROVIDER,
    EVENT_CONTROL_CODE_ENABLE_PROVIDER,
    EVENT_TRACE_CONTROL_STOP,
    EVENT_TRACE_REAL_TIME_MODE,
    KERNEL_NETWORK_KEYWORDS,
    PROVIDER_GUID,
    TRACE_LEVEL_INFORMATION,
    WNODE_FLAG_TRACED_GUID,
)
from net_monitor.collectors.etw.events import NetworkEvent
from net_monitor.collectors.etw.parser import EventIdentity, parse_network_event

_FILETIME_UNIX_EPOCH_OFFSET = 116_444_736_000_000_000
_FILETIME_TICKS_PER_SECOND = 10_000_000


def _filetime_to_unix_seconds(value: int) -> float:
    return (value - _FILETIME_UNIX_EPOCH_OFFSET) / _FILETIME_TICKS_PER_SECOND


class EtwSession:
    """Owns a real-time Microsoft-Windows-Kernel-Network ETW session."""

    def __init__(
        self,
        on_event: Callable[[NetworkEvent], None],
        *,
        api: EtwApi | None = None,
        session_name: str | None = None,
    ) -> None:
        self._api = api or EtwApi()
        self._on_event = on_event
        self.session_name = session_name or f"NetMonitor-ProcessNetwork-PoC-{uuid.uuid4()}"
        self._provider_guid = GUID.from_string(PROVIDER_GUID)
        self._session_handle = TRACEHANDLE()
        self._consumer_handle: PROCESSTRACE_HANDLE | None = None
        self._properties_storage = None
        self._properties = None
        self._thread: threading.Thread | None = None
        self._callback: EVENT_RECORD_CALLBACK | None = None
        self._thread_error: Exception | None = None
        self._started = False
        self._lock = threading.Lock()

    def __enter__(self) -> "EtwSession":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("ETW session is already started")

            storage, properties = allocate_trace_properties(
                self.session_name,
                real_time_mode=EVENT_TRACE_REAL_TIME_MODE,
                wnode_flag=WNODE_FLAG_TRACED_GUID,
            )
            self._properties_storage = storage
            self._properties = properties

            status = self._api.StartTraceW(ctypes.byref(self._session_handle), self.session_name, properties)
            raise_for_status("StartTraceW", int(status), self.session_name)

            try:
                status = self._api.EnableTraceEx2(
                    CONTROLTRACE_ID(self._session_handle.value),
                    ctypes.byref(self._provider_guid),
                    EVENT_CONTROL_CODE_ENABLE_PROVIDER,
                    TRACE_LEVEL_INFORMATION,
                    KERNEL_NETWORK_KEYWORDS,
                    0,
                    0,
                    None,
                )
                raise_for_status("EnableTraceEx2", int(status), PROVIDER_GUID)
                self._open_consumer()
            except Exception:
                self._stop_controller(ignore_errors=True)
                raise

            self._started = True
            self._thread = threading.Thread(target=self._consume, name="NetMonitor-ETW-Consumer", daemon=False)
            self._thread.start()

    def _open_consumer(self) -> None:
        self._callback = EVENT_RECORD_CALLBACK(self._handle_record)
        options = ETW_OPEN_TRACE_OPTIONS()
        options.ProcessTraceModes = 0
        options.EventCallback = self._callback
        options.EventCallbackContext = None
        options.BufferCallback = None
        options.BufferCallbackContext = None

        handle = self._api.OpenTraceFromRealTimeLogger(self.session_name, ctypes.byref(options), None)
        invalid_handle = ctypes.c_uint64(-1).value
        if int(handle) == invalid_handle:
            error = ctypes.get_last_error()
            raise EtwError("OpenTraceFromRealTimeLogger", error, self.session_name)
        self._consumer_handle = PROCESSTRACE_HANDLE(handle)

    def _consume(self) -> None:
        assert self._consumer_handle is not None
        handles = (PROCESSTRACE_HANDLE * 1)(self._consumer_handle.value)
        status = int(self._api.ProcessTrace(handles, 1, None, None))
        if status not in (ERROR_SUCCESS, ERROR_CANCELLED):
            self._thread_error = EtwError("ProcessTrace", status, self.session_name)

    def _handle_record(self, record: ctypes.POINTER(EVENT_RECORD)) -> None:
        try:
            header = record.contents.EventHeader
            provider_guid = "{" + str(header.ProviderId.as_uuid()).upper() + "}"
            identity = EventIdentity(
                provider_guid=provider_guid,
                event_id=int(header.EventDescriptor.Id),
                version=int(header.EventDescriptor.Version),
                task=int(header.EventDescriptor.Task),
                opcode=int(header.EventDescriptor.Opcode),
                timestamp=_filetime_to_unix_seconds(int(header.TimeStamp)),
            )
            event = parse_network_event(identity, lambda name: self._api.read_uint32_property(record, name))
            if event is not None:
                self._on_event(event)
        except Exception:
            # Unknown/malformed events must not terminate ProcessTrace.
            return

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._started:
                return
            self._started = False

            try:
                self._api.EnableTraceEx2(
                    CONTROLTRACE_ID(self._session_handle.value),
                    ctypes.byref(self._provider_guid),
                    EVENT_CONTROL_CODE_DISABLE_PROVIDER,
                    0,
                    0,
                    0,
                    0,
                    None,
                )
            finally:
                self._stop_controller(ignore_errors=False)

        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                self._close_consumer(ignore_errors=True)
                thread.join(timeout)
            if thread.is_alive():
                raise EtwError("ProcessTrace", -1, "consumer thread did not stop")

        self._close_consumer(ignore_errors=False)
        if self._thread_error is not None:
            error = self._thread_error
            self._thread_error = None
            raise error

    def _stop_controller(self, *, ignore_errors: bool) -> None:
        if self._properties is None:
            return
        status = int(
            self._api.ControlTraceW(
                CONTROLTRACE_ID(self._session_handle.value),
                self.session_name,
                self._properties,
                EVENT_TRACE_CONTROL_STOP,
            )
        )
        if not ignore_errors and status != ERROR_SUCCESS:
            raise_for_status("ControlTraceW", status, self.session_name)

    def _close_consumer(self, *, ignore_errors: bool) -> None:
        if self._consumer_handle is None:
            return
        handle = self._consumer_handle
        self._consumer_handle = None
        status = int(self._api.CloseTrace(handle))
        if not ignore_errors and status not in (ERROR_SUCCESS, ERROR_CANCELLED):
            raise_for_status("CloseTrace", status, self.session_name)

    @property
    def started(self) -> bool:
        return self._started
