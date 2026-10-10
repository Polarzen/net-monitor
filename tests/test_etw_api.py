from __future__ import annotations

import ctypes
import sys

import pytest

from net_monitor.collectors.etw.api import (
    EVENT_DESCRIPTOR,
    EVENT_HEADER,
    EVENT_RECORD,
    EVENT_TRACE_PROPERTIES,
    ETW_OPEN_TRACE_OPTIONS,
    WNODE_HEADER,
)


@pytest.mark.skipif(sys.platform != "win32", reason="ETW ABI is a Windows SDK contract")
def test_etw_structures_match_the_64_bit_windows_sdk_abi() -> None:
    assert ctypes.sizeof(ctypes.c_void_p) == 8

    assert ctypes.sizeof(WNODE_HEADER) == 48
    assert ctypes.alignment(WNODE_HEADER) == 8
    assert WNODE_HEADER.Guid.offset == 24
    assert WNODE_HEADER.Flags.offset == 44

    assert ctypes.sizeof(EVENT_TRACE_PROPERTIES) == 120
    assert ctypes.alignment(EVENT_TRACE_PROPERTIES) == 8
    assert EVENT_TRACE_PROPERTIES.EventsLost.offset == 88
    assert EVENT_TRACE_PROPERTIES.LoggerThreadId.offset == 104

    assert ctypes.sizeof(EVENT_DESCRIPTOR) == 16
    assert ctypes.alignment(EVENT_DESCRIPTOR) == 8
    assert EVENT_DESCRIPTOR.Keyword.offset == 8

    assert ctypes.sizeof(EVENT_HEADER) == 80
    assert ctypes.alignment(EVENT_HEADER) == 8
    assert EVENT_HEADER.EventDescriptor.offset == 40

    assert ctypes.sizeof(EVENT_RECORD) == 112
    assert ctypes.alignment(EVENT_RECORD) == 8
    assert EVENT_RECORD.ExtendedData.offset == 88
    assert EVENT_RECORD.UserData.offset == 96
    assert EVENT_RECORD.UserContext.offset == 104

    assert ctypes.sizeof(ETW_OPEN_TRACE_OPTIONS) == 40
    assert ctypes.alignment(ETW_OPEN_TRACE_OPTIONS) == 8
    assert [getattr(ETW_OPEN_TRACE_OPTIONS, field).offset for field, _ in ETW_OPEN_TRACE_OPTIONS._fields_] == [
        0,
        8,
        16,
        24,
        32,
    ]
