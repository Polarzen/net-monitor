from __future__ import annotations

import ctypes

import pytest

from net_monitor.collectors.etw.api import EtwPermissionError, GUID, TRACEHANDLE
from net_monitor.collectors.etw.constants import (
    EVENT_CONTROL_CODE_DISABLE_PROVIDER,
    EVENT_CONTROL_CODE_ENABLE_PROVIDER,
    PROVIDER_GUID,
)
from net_monitor.collectors.etw.session import EtwSession


class FakeEtwApi:
    def __init__(self, *, fail_enable: bool = False) -> None:
        self.fail_enable = fail_enable
        self.calls: list[tuple[str, int | str | None]] = []

    def StartTraceW(self, handle_ptr: object, session_name: str, properties: object) -> int:
        del properties
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
        del options, context
        self.calls.append(("open", session_name))
        return 202

    def ProcessTrace(self, handles: object, count: int, start: object, end: object) -> int:
        del handles, start, end
        self.calls.append(("process", count))
        return 0

    def ControlTraceW(self, handle: object, session_name: str, properties: object, control_code: int) -> int:
        del handle, properties
        self.calls.append(("control", control_code))
        self.calls.append(("control_session", session_name))
        return 0

    def CloseTrace(self, handle: object) -> int:
        del handle
        self.calls.append(("close", None))
        return 0


def test_guid_round_trip() -> None:
    guid = GUID.from_string(PROVIDER_GUID)
    assert "{" + str(guid.as_uuid()).upper() + "}" == PROVIDER_GUID


def test_session_start_stop_and_repeated_stop_are_safe() -> None:
    api = FakeEtwApi()
    session = EtwSession(lambda event: None, api=api, session_name="NetMonitor-Test-Session")  # type: ignore[arg-type]

    session.start()
    assert session.started is True
    session.stop()
    assert session.started is False

    first_stop_calls = list(api.calls)
    session.stop()
    assert api.calls == first_stop_calls
    assert ("enable", EVENT_CONTROL_CODE_ENABLE_PROVIDER) in api.calls
    assert ("enable", EVENT_CONTROL_CODE_DISABLE_PROVIDER) in api.calls
    assert ("close", None) in api.calls


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
