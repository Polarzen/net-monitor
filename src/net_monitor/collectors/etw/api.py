from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes

from net_monitor.collectors.etw.constants import ERROR_ACCESS_DENIED, ERROR_SUCCESS

TRACEHANDLE = ctypes.c_uint64
CONTROLTRACE_ID = ctypes.c_uint64
PROCESSTRACE_HANDLE = ctypes.c_uint64
ULONG64 = ctypes.c_uint64
ULONGLONG = ctypes.c_uint64
LONGLONG = ctypes.c_int64
ULONG = wintypes.ULONG
USHORT = wintypes.USHORT
UCHAR = ctypes.c_ubyte
PVOID = ctypes.c_void_p


class EtwError(RuntimeError):
    def __init__(self, api_name: str, error_code: int, context: str | None = None) -> None:
        self.api_name = api_name
        self.error_code = int(error_code)
        self.context = context
        suffix = f" ({context})" if context else ""
        super().__init__(f"{api_name} failed with Windows error {error_code}{suffix}")


class EtwPermissionError(EtwError):
    pass


class EtwPlatformError(RuntimeError):
    pass


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        parsed = uuid.UUID(value.strip("{}"))
        data = parsed.bytes_le
        result = cls()
        result.Data1 = int.from_bytes(data[0:4], "little")
        result.Data2 = int.from_bytes(data[4:6], "little")
        result.Data3 = int.from_bytes(data[6:8], "little")
        result.Data4[:] = data[8:16]
        return result

    def as_uuid(self) -> uuid.UUID:
        raw = (
            int(self.Data1).to_bytes(4, "little")
            + int(self.Data2).to_bytes(2, "little")
            + int(self.Data3).to_bytes(2, "little")
            + bytes(self.Data4)
        )
        return uuid.UUID(bytes_le=raw)


class _WNODE_VERSION_LINKAGE(ctypes.Structure):
    _fields_ = [("Version", ULONG), ("Linkage", ULONG)]


class _WNODE_CONTEXT(ctypes.Union):
    _anonymous_ = ("version_linkage",)
    _fields_ = [("HistoricalContext", ULONG64), ("version_linkage", _WNODE_VERSION_LINKAGE)]


class _WNODE_TIMESTAMP(ctypes.Union):
    _fields_ = [("CountLost", ULONG), ("KernelHandle", wintypes.HANDLE), ("TimeStamp", LONGLONG)]


class WNODE_HEADER(ctypes.Structure):
    _anonymous_ = ("context", "time")
    _fields_ = [
        ("BufferSize", ULONG),
        ("ProviderId", ULONG),
        ("context", _WNODE_CONTEXT),
        ("time", _WNODE_TIMESTAMP),
        ("Guid", GUID),
        ("ClientContext", ULONG),
        ("Flags", ULONG),
    ]


class EVENT_TRACE_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("Wnode", WNODE_HEADER),
        ("BufferSize", ULONG),
        ("MinimumBuffers", ULONG),
        ("MaximumBuffers", ULONG),
        ("MaximumFileSize", ULONG),
        ("LogFileMode", ULONG),
        ("FlushTimer", ULONG),
        ("EnableFlags", ULONG),
        ("AgeLimit", ctypes.c_long),
        ("NumberOfBuffers", ULONG),
        ("FreeBuffers", ULONG),
        ("EventsLost", ULONG),
        ("BuffersWritten", ULONG),
        ("LogBuffersLost", ULONG),
        ("RealTimeBuffersLost", ULONG),
        ("LoggerThreadId", wintypes.HANDLE),
        ("LogFileNameOffset", ULONG),
        ("LoggerNameOffset", ULONG),
    ]


class EVENT_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("Id", USHORT),
        ("Version", UCHAR),
        ("Channel", UCHAR),
        ("Level", UCHAR),
        ("Opcode", UCHAR),
        ("Task", USHORT),
        ("Keyword", ULONGLONG),
    ]


class _EVENT_HEADER_TIMES(ctypes.Structure):
    _fields_ = [("KernelTime", ULONG), ("UserTime", ULONG)]


class _EVENT_HEADER_TIME_UNION(ctypes.Union):
    _anonymous_ = ("times",)
    _fields_ = [("times", _EVENT_HEADER_TIMES), ("ProcessorTime", ULONG64)]


class EVENT_HEADER(ctypes.Structure):
    _anonymous_ = ("processor",)
    _fields_ = [
        ("Size", USHORT),
        ("HeaderType", USHORT),
        ("Flags", USHORT),
        ("EventProperty", USHORT),
        ("ThreadId", ULONG),
        ("ProcessId", ULONG),
        ("TimeStamp", LONGLONG),
        ("ProviderId", GUID),
        ("EventDescriptor", EVENT_DESCRIPTOR),
        ("processor", _EVENT_HEADER_TIME_UNION),
        ("ActivityId", GUID),
    ]


class _ETW_PROCESSOR_BYTES(ctypes.Structure):
    _fields_ = [("ProcessorNumber", UCHAR), ("Alignment", UCHAR)]


class _ETW_PROCESSOR_UNION(ctypes.Union):
    _anonymous_ = ("bytes",)
    _fields_ = [("bytes", _ETW_PROCESSOR_BYTES), ("ProcessorIndex", USHORT)]


class ETW_BUFFER_CONTEXT(ctypes.Structure):
    _anonymous_ = ("processor",)
    _fields_ = [("processor", _ETW_PROCESSOR_UNION), ("LoggerId", USHORT)]


class EVENT_HEADER_EXTENDED_DATA_ITEM(ctypes.Structure):
    _fields_ = [
        ("Reserved1", USHORT),
        ("ExtType", USHORT),
        ("LinkageAndReserved2", USHORT),
        ("DataSize", USHORT),
        ("DataPtr", ULONGLONG),
    ]


class EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("EventHeader", EVENT_HEADER),
        ("BufferContext", ETW_BUFFER_CONTEXT),
        ("ExtendedDataCount", USHORT),
        ("UserDataLength", USHORT),
        ("ExtendedData", ctypes.POINTER(EVENT_HEADER_EXTENDED_DATA_ITEM)),
        ("UserData", PVOID),
        ("UserContext", PVOID),
    ]


CALLBACK_FACTORY = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
EVENT_RECORD_CALLBACK = CALLBACK_FACTORY(None, ctypes.POINTER(EVENT_RECORD))


class ETW_OPEN_TRACE_OPTIONS(ctypes.Structure):
    _fields_ = [
        ("ProcessTraceModes", ULONG),
        ("EventCallback", EVENT_RECORD_CALLBACK),
        ("EventCallbackContext", PVOID),
        ("BufferCallback", PVOID),
        ("BufferCallbackContext", PVOID),
    ]


class PROPERTY_DATA_DESCRIPTOR(ctypes.Structure):
    _fields_ = [("PropertyName", ULONGLONG), ("ArrayIndex", ULONG), ("Reserved", ULONG)]


def raise_for_status(api_name: str, status: int, context: str | None = None) -> None:
    if status == ERROR_SUCCESS:
        return
    if status == ERROR_ACCESS_DENIED:
        raise EtwPermissionError(api_name, status, context)
    raise EtwError(api_name, status, context)


def allocate_trace_properties(session_name: str, *, real_time_mode: int, wnode_flag: int):
    encoded_name = session_name.encode("utf-16-le") + b"\x00\x00"
    total_size = ctypes.sizeof(EVENT_TRACE_PROPERTIES) + len(encoded_name)
    storage = ctypes.create_string_buffer(total_size)
    properties = ctypes.cast(storage, ctypes.POINTER(EVENT_TRACE_PROPERTIES))
    properties.contents.Wnode.BufferSize = total_size
    properties.contents.Wnode.ClientContext = 1
    properties.contents.Wnode.Flags = wnode_flag
    properties.contents.LogFileMode = real_time_mode
    properties.contents.FlushTimer = 1
    properties.contents.LoggerNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
    properties.contents.LogFileNameOffset = 0
    ctypes.memmove(ctypes.addressof(storage) + properties.contents.LoggerNameOffset, encoded_name, len(encoded_name))
    return storage, properties


class EtwApi:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise EtwPlatformError("ETW is only available on Windows")

        self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._tdh = ctypes.WinDLL("tdh", use_last_error=True)
        self._sechost = ctypes.WinDLL("sechost", use_last_error=True)

        self.StartTraceW = self._advapi32.StartTraceW
        self.StartTraceW.argtypes = [ctypes.POINTER(TRACEHANDLE), wintypes.LPCWSTR, ctypes.POINTER(EVENT_TRACE_PROPERTIES)]
        self.StartTraceW.restype = ULONG

        self.EnableTraceEx2 = self._advapi32.EnableTraceEx2
        self.EnableTraceEx2.argtypes = [CONTROLTRACE_ID, ctypes.POINTER(GUID), ULONG, UCHAR, ULONGLONG, ULONGLONG, ULONG, PVOID]
        self.EnableTraceEx2.restype = ULONG

        self.ControlTraceW = self._advapi32.ControlTraceW
        self.ControlTraceW.argtypes = [CONTROLTRACE_ID, wintypes.LPCWSTR, ctypes.POINTER(EVENT_TRACE_PROPERTIES), ULONG]
        self.ControlTraceW.restype = ULONG

        open_realtime = getattr(self._sechost, "OpenTraceFromRealTimeLogger", None)
        if open_realtime is None:
            open_realtime = getattr(self._advapi32, "OpenTraceFromRealTimeLogger", None)
        if open_realtime is None:
            raise EtwPlatformError("OpenTraceFromRealTimeLogger is unavailable; Windows 11 22H2 or newer is required")
        self.OpenTraceFromRealTimeLogger = open_realtime
        self.OpenTraceFromRealTimeLogger.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ETW_OPEN_TRACE_OPTIONS), PVOID]
        self.OpenTraceFromRealTimeLogger.restype = PROCESSTRACE_HANDLE

        self.ProcessTrace = self._advapi32.ProcessTrace
        self.ProcessTrace.argtypes = [ctypes.POINTER(PROCESSTRACE_HANDLE), ULONG, PVOID, PVOID]
        self.ProcessTrace.restype = ULONG

        self.CloseTrace = self._advapi32.CloseTrace
        self.CloseTrace.argtypes = [PROCESSTRACE_HANDLE]
        self.CloseTrace.restype = ULONG

        self.TdhGetPropertySize = self._tdh.TdhGetPropertySize
        self.TdhGetPropertySize.argtypes = [ctypes.POINTER(EVENT_RECORD), ULONG, PVOID, ULONG, ctypes.POINTER(PROPERTY_DATA_DESCRIPTOR), ctypes.POINTER(ULONG)]
        self.TdhGetPropertySize.restype = ULONG

        self.TdhGetProperty = self._tdh.TdhGetProperty
        self.TdhGetProperty.argtypes = [ctypes.POINTER(EVENT_RECORD), ULONG, PVOID, ULONG, ctypes.POINTER(PROPERTY_DATA_DESCRIPTOR), ULONG, ctypes.POINTER(ctypes.c_ubyte)]
        self.TdhGetProperty.restype = ULONG

    def read_uint32_property(self, record: ctypes.POINTER(EVENT_RECORD), name: str) -> int:
        name_buffer = ctypes.create_unicode_buffer(name)
        descriptor = PROPERTY_DATA_DESCRIPTOR()
        descriptor.PropertyName = ctypes.cast(name_buffer, ctypes.c_void_p).value or 0
        descriptor.ArrayIndex = 0xFFFFFFFF
        size = ULONG()
        status = self.TdhGetPropertySize(record, 0, None, 1, ctypes.byref(descriptor), ctypes.byref(size))
        raise_for_status("TdhGetPropertySize", int(status), name)
        if size.value != ctypes.sizeof(ctypes.c_uint32):
            raise EtwError("TdhGetPropertySize", int(size.value), f"{name}: expected UInt32")
        buffer = (ctypes.c_ubyte * size.value)()
        status = self.TdhGetProperty(record, 0, None, 1, ctypes.byref(descriptor), size, buffer)
        raise_for_status("TdhGetProperty", int(status), name)
        return int.from_bytes(bytes(buffer), byteorder="little", signed=False)
