from __future__ import annotations

from types import SimpleNamespace

import pytest

from net_monitor.collectors import process as process_module
from net_monitor.collectors.process import ProcessCollector


def _fake_processes() -> tuple[SimpleNamespace, ...]:
    return (
        SimpleNamespace(
            info={
                "pid": 7,
                "name": "beta.exe",
                "exe": r"D:\Apps\beta.exe",
                "status": "running",
                "create_time": 1.0,
            }
        ),
        SimpleNamespace(
            info={
                "pid": 7,
                "name": "beta.exe",
                "exe": r"D:\Apps\beta.exe",
                "status": "sleeping",
                "create_time": 2.0,
            }
        ),
        SimpleNamespace(
            info={
                "pid": 4,
                "name": "Alpha.exe",
                "exe": r"C:\Apps\alpha.exe",
                "status": "stopped",
                "create_time": 3.0,
            }
        ),
    )


@pytest.mark.parametrize("include_status", [True, False])
def test_collect_preserves_identity_and_sorting_with_optional_status(
    monkeypatch: pytest.MonkeyPatch,
    include_status: bool,
) -> None:
    requested_attrs: list[list[str]] = []
    fake_processes = _fake_processes()

    def process_iter(attrs: list[str]) -> tuple[SimpleNamespace, ...]:
        requested_attrs.append(attrs)
        return fake_processes

    monkeypatch.setattr(process_module.psutil, "process_iter", process_iter)

    collector = ProcessCollector() if include_status else ProcessCollector(include_status=False)
    processes = collector.collect()

    expected_attrs = ["pid", "name", "exe", "create_time"]
    if include_status:
        expected_attrs.insert(3, "status")
    assert requested_attrs == [expected_attrs]
    assert [(process.name, process.pid, process.create_time) for process in processes] == [
        ("Alpha.exe", 4, 3.0),
        ("beta.exe", 7, 1.0),
        ("beta.exe", 7, 2.0),
    ]
    assert processes[1].identity != processes[2].identity
    assert [process.status for process in processes] == (
        ["stopped", "running", "sleeping"] if include_status else [None, None, None]
    )
