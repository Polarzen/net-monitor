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
    ERROR_CTX_CLOSE_PENDING,
    ERROR_SUCCESS,
    EVENT_CONTROL_CODE_DISABLE_PROVIDER,
    EVENT_CONTROL_CODE_ENABLE_PROVIDER,
    EVENT_TRACE_CONTROL_STOP,
    EVENT_TRACE_INDEPENDENT_SESSION_MODE,
    EVENT_TRACE_REAL_TIME_MODE,
    KERNEL_NETWORK_KEYWORDS,
    PROVIDER_GUID,
    TRACE_LEVEL_INFORMATION,
    WNODE_FLAG_TRACED_GUID,
    ERROR_WMI_INSTANCE_NOT_FOUND,
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
        self._stop_requested = False
        self._controller_active = False
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
            if self._thread is not None or self._consumer_handle is not None or self._properties is not None:
                raise RuntimeError("ETW session resources are still being cleaned up")

            self._thread_error = None
            self._stop_requested = False
            self._thread = None
            storage, properties = allocate_trace_properties(
                self.session_name,
                real_time_mode=EVENT_TRACE_REAL_TIME_MODE | EVENT_TRACE_INDEPENDENT_SESSION_MODE,
                wnode_flag=WNODE_FLAG_TRACED_GUID,
            )
            self._properties_storage = storage
            self._properties = properties

            trace_started = False
            try:
                status = self._api.StartTraceW(ctypes.byref(self._session_handle), self.session_name, properties)
                raise_for_status("StartTraceW", int(status), self.session_name)
                trace_started = self._controller_active = True

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
                self._started = True
                self._thread = threading.Thread(target=self._consume, name="NetMonitor-ETW-Consumer", daemon=False)
                self._thread.start()
            except BaseException:
                self._started = False
                self._stop_requested = True
                self._cleanup_after_start_failure(trace_started)
                raise

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
        error: Exception | None = None
        try:
            handle = self._consumer_handle
            if handle is None:
                error = RuntimeError("ETW consumer started without a ProcessTrace handle")
            else:
                handles = (PROCESSTRACE_HANDLE * 1)(handle.value)
                status = int(self._api.ProcessTrace(handles, 1, None, None))
                stopping = self._stop_requested
                if status == ERROR_SUCCESS:
                    if not stopping:
                        error = RuntimeError(
                            f"ProcessTrace exited before ETW session {self.session_name!r} was stopped"
                        )
                elif status == ERROR_CANCELLED and stopping:
                    pass
                else:
                    error = EtwError("ProcessTrace", status, self.session_name)
        except Exception as exc:
            error = exc
        finally:
            if error is not None:
                self._thread_error = error

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
            if (
                self._thread is None
                and self._consumer_handle is None
                and self._properties is None
                and not self._controller_active
            ):
                return
            was_started = self._started
            self._started = False
            self._stop_requested = True
            cleanup_errors: list[Exception] = []

            if was_started:
                try:
                    status = int(self._api.EnableTraceEx2(
                        CONTROLTRACE_ID(self._session_handle.value),
                        ctypes.byref(self._provider_guid),
                        EVENT_CONTROL_CODE_DISABLE_PROVIDER,
                        0,
                        0,
                        0,
                        0,
                        None,
                    ))
                    raise_for_status("EnableTraceEx2", status, PROVIDER_GUID)
                except Exception as exc:
                    cleanup_errors.append(exc)

            if self._controller_active:
                try:
                    self._stop_controller(ignore_errors=False)
                except Exception as exc:
                    cleanup_errors.append(exc)

            thread = self._thread

            # Keep the lifecycle lock through joins so a concurrent start/stop
            # cannot release or replace handles while ProcessTrace is unwinding.
            if thread is not None and thread.ident is not None:
                thread.join(timeout)
                if thread.is_alive():
                    self._close_consumer(ignore_errors=True)
                    thread.join(timeout)
                if thread.is_alive():
                    cleanup_errors.append(EtwError("ProcessTrace", -1, "consumer thread did not stop"))

            try:
                self._close_consumer(ignore_errors=False)
            except Exception as exc:
                cleanup_errors.append(exc)

            if thread is None or not thread.is_alive():
                self._thread = None
                if self._consumer_handle is None:
                    self._callback = None
                if not self._controller_active:
                    self._properties = None
                    self._properties_storage = None
                    self._session_handle = TRACEHANDLE()
                if self._consumer_handle is None and not self._controller_active:
                    self._stop_requested = False

            if self._thread_error is not None:
                raise self._thread_error
            if cleanup_errors:
                raise cleanup_errors[0]

    def _cleanup_after_start_failure(self, trace_started: bool) -> None:
        """Best-effort rollback used while start still owns the session resources."""

        if trace_started:
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
            except Exception:
                pass
            try:
                self._stop_controller(ignore_errors=True)
            except Exception:
                pass

        thread = self._thread
        self._close_consumer(ignore_errors=True)
        if thread is not None and thread.ident is not None:
            thread.join(5.0)
            if thread.is_alive():
                self._close_consumer(ignore_errors=True)
                thread.join(5.0)
        if thread is None or not thread.is_alive():
            self._thread = None
            if self._consumer_handle is None:
                self._callback = None
            if not self._controller_active:
                self._properties = None
                self._properties_storage = None
                self._session_handle = TRACEHANDLE()
            if self._consumer_handle is None and not self._controller_active:
                self._stop_requested = False

    def _stop_controller(self, *, ignore_errors: bool) -> None:
        if self._properties is None:
            return
        try:
            status = int(
                self._api.ControlTraceW(
                    CONTROLTRACE_ID(self._session_handle.value),
                    self.session_name,
                    self._properties,
                    EVENT_TRACE_CONTROL_STOP,
                )
            )
            if status in (ERROR_SUCCESS, ERROR_WMI_INSTANCE_NOT_FOUND):
                self._controller_active = False
            elif not ignore_errors:
                raise_for_status("ControlTraceW", status, self.session_name)
        except Exception:
            if not ignore_errors:
                raise

    def _close_consumer(self, *, ignore_errors: bool) -> None:
        if self._consumer_handle is None:
            return
        handle = self._consumer_handle
        try:
            status = int(self._api.CloseTrace(handle))
            if status == ERROR_CTX_CLOSE_PENDING:
                # The OS owns the pending close; the ProcessTrace callback must
                # remain strongly referenced until its thread has returned.
                self._consumer_handle = None
                return
            if status not in (ERROR_SUCCESS, ERROR_CANCELLED):
                if ignore_errors:
                    self._consumer_handle = handle
                    return
                raise_for_status("CloseTrace", status, self.session_name)
        except Exception:
            if not ignore_errors:
                raise
            self._consumer_handle = handle
            return
        self._consumer_handle = None

    def raise_if_failed(self) -> None:
        """Raise an asynchronous consumer failure, if one has been observed."""

        if self._thread_error is None and self._started and self._thread is not None and not self._thread.is_alive():
            self._thread_error = RuntimeError(
                f"ETW consumer thread for {self.session_name!r} exited without a result"
            )
        if self._thread_error is not None:
            raise self._thread_error

    @property
    def started(self) -> bool:
        return self._started
