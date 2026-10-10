from __future__ import annotations

import ctypes
import threading
import weakref

import pytest

from net_monitor.collectors.etw.api import ETW_OPEN_TRACE_OPTIONS, EtwError, EtwPermissionError, GUID, TRACEHANDLE
from net_monitor.collectors.etw.constants import (
    ERROR_CTX_CLOSE_PENDING,
    EVENT_CONTROL_CODE_DISABLE_PROVIDER,
    EVENT_CONTROL_CODE_ENABLE_PROVIDER,
    EVENT_TRACE_INDEPENDENT_SESSION_MODE,
    EVENT_TRACE_REAL_TIME_MODE,
    PROVIDER_GUID,
)
from net_monitor.collectors.etw.session import EtwSession


class FakeEtwApi:
    def __init__(
        self,
        *,
        fail_enable: bool = False,
        process_status: int = 0,
        process_error: Exception | None = None,
        process_wait: bool = True,
        process_release_on_control: bool = True,
        control_statuses: list[int] | None = None,
        close_statuses: list[int] | None = None,
    ) -> None:
        self.fail_enable = fail_enable
        self.process_status = process_status
        self.process_error = process_error
        self.process_wait = process_wait
        self.process_release_on_control = process_release_on_control
        self.control_statuses = list(control_statuses or [])
        self.close_statuses = list(close_statuses or [])
        self.process_started = threading.Event()
        self.process_release = threading.Event()
        self.calls: list[tuple[str, int | str | None]] = []
        self.options: ETW_OPEN_TRACE_OPTIONS | None = None
        self.log_file_mode: int | None = None

    def StartTraceW(self, handle_ptr: object, session_name: str, properties: object) -> int:
        self.log_file_mode = int(properties.contents.LogFileMode)  # type: ignore[attr-defined]
        ctypes.cast(handle_ptr, ctypes.POINTER(TRACEHANDLE)).contents.value = 101
        self.calls.append(("start", session_name))
        return 0

    def EnableTraceEx2(
        self,
        handle: object,
        provider: object,
        control_code: int,
        level: int,
        match_any_keyword: int,
        match_all_keyword: int,
        timeout: int,
        params: object,
    ) -> int:
        del handle, provider, level, match_any_keyword, match_all_keyword, timeout, params
        self.calls.append(("enable", control_code))
        if self.fail_enable and control_code == EVENT_CONTROL_CODE_ENABLE_PROVIDER:
            return 5
        return 0

    def OpenTraceFromRealTimeLogger(self, session_name: str, options: object, context: object) -> int:
        del context
        self.options = ETW_OPEN_TRACE_OPTIONS.from_buffer_copy(
            ctypes.string_at(options, ctypes.sizeof(ETW_OPEN_TRACE_OPTIONS))
        )
        self.calls.append(("open", session_name))
        return 202

    def ProcessTrace(self, handles: object, count: int, start: object, end: object) -> int:
        del handles, start, end
        self.calls.append(("process", count))
        self.process_started.set()
        if self.process_wait:
            self.process_release.wait()
        if self.process_error is not None:
            raise self.process_error
        return self.process_status

    def ControlTraceW(self, handle: object, session_name: str, properties: object, control_code: int) -> int:
        del handle, properties
        self.calls.append(("control", control_code))
        self.calls.append(("control_session", session_name))
        status = self.control_statuses.pop(0) if self.control_statuses else 0
        if status == 0 and self.process_release_on_control:
            self.process_release.set()
        return status

    def CloseTrace(self, handle: object) -> int:
        del handle
        self.calls.append(("close", None))
        return self.close_statuses.pop(0) if self.close_statuses else 0


def test_guid_round_trip() -> None:
    guid = GUID.from_string(PROVIDER_GUID)
    assert "{" + str(guid.as_uuid()).upper() + "}" == PROVIDER_GUID


def test_session_start_stop_and_repeated_stop_are_safe() -> None:
    api = FakeEtwApi()
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Session")  # type: ignore[arg-type]

    session.start()
    assert session.started is True
    assert api.log_file_mode == EVENT_TRACE_REAL_TIME_MODE | EVENT_TRACE_INDEPENDENT_SESSION_MODE
    session.stop()
    assert session.started is False

    first_stop_calls = list(api.calls)
    session.stop()
    assert api.calls == first_stop_calls
    assert ("enable", EVENT_CONTROL_CODE_ENABLE_PROVIDER) in api.calls
    assert ("enable", EVENT_CONTROL_CODE_DISABLE_PROVIDER) in api.calls
    assert ("close", None) in api.calls


def test_open_trace_uses_callback_mode_zero_and_keeps_callback_options() -> None:
    api = FakeEtwApi()
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Options")  # type: ignore[arg-type]

    session.start()
    try:
        assert api.options is not None
        assert api.options.ProcessTraceModes == 0
        assert api.options.EventCallback
        assert api.options.EventCallbackContext is None
        assert api.options.BufferCallback is None
        assert api.options.BufferCallbackContext is None
    finally:
        session.stop()


def test_callback_stays_alive_until_process_trace_returns() -> None:
    api = FakeEtwApi()
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Callback-Lifetime")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    callback = session._callback
    assert callback is not None
    callback_ref = weakref.ref(callback)
    session._close_consumer(ignore_errors=True)
    del callback
    assert callback_ref() is not None

    api.process_release.set()
    session.stop()
    assert callback_ref() is None


@pytest.mark.parametrize("status", [1, 55])
def test_process_trace_failure_is_reported_by_health_check(status: int) -> None:
    api = FakeEtwApi(process_status=status, process_wait=False)
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-ProcessTrace")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    assert session._thread is not None
    session._thread.join(1)
    with pytest.raises(EtwError, match="ProcessTrace"):
        session.raise_if_failed()
    with pytest.raises(EtwError, match="ProcessTrace"):
        session.stop()


def test_process_trace_exception_is_reported_by_health_check() -> None:
    api = FakeEtwApi(process_error=RuntimeError("consumer exploded"), process_wait=False)
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-ProcessTrace-Exception")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    assert session._thread is not None
    session._thread.join(1)
    with pytest.raises(RuntimeError, match="consumer exploded"):
        session.raise_if_failed()
    with pytest.raises(RuntimeError, match="consumer exploded"):
        session.stop()


def test_premature_success_exit_is_a_failure_but_orderly_success_is_not() -> None:
    premature_api = FakeEtwApi(process_wait=False)
    premature = EtwSession(lambda event: None, api=premature_api, session_name="NetMonitor-Test-Premature")  # type: ignore[arg-type]
    premature.start()
    assert premature_api.process_started.wait(1)
    assert premature._thread is not None
    premature._thread.join(1)
    with pytest.raises(RuntimeError, match="exited before"):
        premature.raise_if_failed()
    with pytest.raises(RuntimeError, match="exited before"):
        premature.stop()

    orderly_api = FakeEtwApi(process_status=1223)
    orderly = EtwSession(lambda event: None, api=orderly_api, session_name="NetMonitor-Test-Orderly")  # type: ignore[arg-type]
    orderly.start()
    orderly.stop()


def test_session_can_restart_after_successful_stop_and_health_resets() -> None:
    api = FakeEtwApi(process_status=77, process_wait=False)
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Restart")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    assert session._thread is not None
    session._thread.join(1)
    with pytest.raises(EtwError):
        session.stop()

    api.process_status = 0
    api.process_wait = True
    api.process_started.clear()
    api.process_release.clear()
    session.start()
    assert api.process_started.wait(1)
    session.stop()


def test_stop_retries_controller_stop_after_first_failure() -> None:
    api = FakeEtwApi(control_statuses=[5, 0])
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Control-Retry")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    with pytest.raises(EtwError, match="ControlTraceW"):
        session.stop(timeout=0.001)

    assert session._controller_active is True
    assert session._properties is not None
    session.stop(timeout=1)
    assert session._controller_active is False
    assert session._properties is None


def test_enable_failure_retains_controller_for_stop_retry() -> None:
    api = FakeEtwApi(fail_enable=True, control_statuses=[5, 0])
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Enable-Rollback")  # type: ignore[arg-type]

    with pytest.raises(EtwPermissionError):
        session.start()

    assert session._controller_active is True
    assert session._properties is not None
    session.stop()
    assert session._controller_active is False
    assert session._properties is None


def test_close_trace_pending_keeps_callback_and_does_not_close_twice() -> None:
    api = FakeEtwApi(close_statuses=[ERROR_CTX_CLOSE_PENDING])
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Close-Pending")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    callback = session._callback
    assert callback is not None
    callback_ref = weakref.ref(callback)

    session._close_consumer(ignore_errors=False)
    assert api.calls.count(("close", None)) == 1
    assert session._consumer_handle is None
    assert callback_ref() is not None

    session.stop(timeout=1)
    del callback
    assert callback_ref() is None
    assert api.calls.count(("close", None)) == 1


def test_thread_start_failure_preserves_original_error(monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeEtwApi()
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Thread-Start")  # type: ignore[arg-type]

    def fail_start(thread: threading.Thread) -> None:
        del thread
        raise RuntimeError("thread start exploded")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    with pytest.raises(RuntimeError, match="thread start exploded"):
        session.start()

    assert session.started is False
    assert session._thread is None
    assert session._callback is None
    assert session._controller_active is False
    assert session._properties is None


def test_thread_surviving_two_shutdown_waits_keeps_callback_for_retry() -> None:
    api = FakeEtwApi(process_release_on_control=False)
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Thread-Retry")  # type: ignore[arg-type]

    session.start()
    assert api.process_started.wait(1)
    callback = session._callback
    assert callback is not None
    callback_ref = weakref.ref(callback)

    with pytest.raises(EtwError, match="did not stop"):
        session.stop(timeout=0.001)
    with pytest.raises(EtwError, match="did not stop"):
        session.stop(timeout=0.001)
    assert callback_ref() is not None
    assert session._thread is not None and session._thread.is_alive()

    api.process_release.set()
    session.stop(timeout=1)
    del callback
    assert callback_ref() is None


def test_session_context_manager_cleans_up_after_exception() -> None:
    api = FakeEtwApi()

    with pytest.raises(RuntimeError, match="boom"):
        with EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Context"):  # type: ignore[arg-type]
            raise RuntimeError("boom")

    assert ("enable", EVENT_CONTROL_CODE_DISABLE_PROVIDER) in api.calls
    assert ("close", None) in api.calls


def test_enable_failure_stops_controller() -> None:
    api = FakeEtwApi(fail_enable=True)
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Failure")  # type: ignore[arg-type]

    with pytest.raises(EtwPermissionError):
        session.start()

    assert session.started is False
    assert ("enable", EVENT_CONTROL_CODE_ENABLE_PROVIDER) in api.calls
    assert any(name == "control" for name, _ in api.calls)


def test_double_start_is_rejected() -> None:
    api = FakeEtwApi()
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Double")  # type: ignore[arg-type]
    session.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            session.start()
    finally:
        session.stop()
