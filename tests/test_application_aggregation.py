from __future__ import annotations

from net_monitor.core.application_aggregation import (
    aggregate_application_network,
    application_key,
)
from net_monitor.core.models import ProcessInfo, ProcessNetworkStats


def test_same_executable_path_is_aggregated_case_insensitively() -> None:
    processes = (
        ProcessInfo(10, "chrome.exe", executable=r"C:\Program Files\Google\Chrome\chrome.exe", create_time=1.0),
        ProcessInfo(20, "chrome.exe", executable=r"c:\program files\google\chrome\CHROME.EXE", create_time=2.0),
    )
    stats = (
        ProcessNetworkStats(10, "chrome.exe", 100, 200, 10.0, 20.0),
        ProcessNetworkStats(20, "chrome.exe", 300, 400, 30.0, 40.0),
    )

    groups = aggregate_application_network(processes, stats)

    assert len(groups) == 1
    group = groups[0]
    assert group.name.lower() == "chrome.exe"
    assert group.process_count == 2
    assert group.upload_bytes == 400
    assert group.download_bytes == 600
    assert group.upload_bytes_per_second == 40.0
    assert group.download_bytes_per_second == 60.0
    assert group.process_identities == ((10, 1.0), (20, 2.0))


def test_different_executables_are_not_merged_even_when_names_match() -> None:
    processes = (
        ProcessInfo(10, "helper.exe", executable=r"D:\AppA\helper.exe", create_time=1.0),
        ProcessInfo(20, "helper.exe", executable=r"E:\AppB\helper.exe", create_time=2.0),
    )
    stats = (
        ProcessNetworkStats(10, "helper.exe", 1, 2, 3.0, 4.0),
        ProcessNetworkStats(20, "helper.exe", 5, 6, 7.0, 8.0),
    )

    groups = aggregate_application_network(processes, stats)

    assert len(groups) == 2
    assert groups[0].key != groups[1].key


def test_unknown_processes_without_executable_remain_separate() -> None:
    processes = (
        ProcessInfo(10, "mystery.exe", executable=None, create_time=1.0),
        ProcessInfo(20, "mystery.exe", executable=None, create_time=2.0),
    )
    stats = (
        ProcessNetworkStats(10, "mystery.exe", 1, 2, 3.0, 4.0),
        ProcessNetworkStats(20, "mystery.exe", 5, 6, 7.0, 8.0),
    )

    groups = aggregate_application_network(processes, stats)

    assert len(groups) == 2
    assert application_key(processes[0]).startswith("process:10:")
    assert application_key(processes[1]).startswith("process:20:")


def test_missing_network_member_propagates_unavailable_group_values() -> None:
    processes = (
        ProcessInfo(10, "browser.exe", executable=r"D:\Browser\browser.exe", create_time=1.0),
        ProcessInfo(20, "browser.exe", executable=r"D:\Browser\browser.exe", create_time=2.0),
    )
    stats = (ProcessNetworkStats(10, "browser.exe", 100, 200, 10.0, 20.0),)

    group = aggregate_application_network(processes, stats)[0]

    assert group.upload_bytes is None
    assert group.download_bytes is None
    assert group.upload_bytes_per_second is None
    assert group.download_bytes_per_second is None


def test_none_network_value_is_not_treated_as_zero() -> None:
    processes = (
        ProcessInfo(10, "browser.exe", executable=r"D:\Browser\browser.exe", create_time=1.0),
        ProcessInfo(20, "browser.exe", executable=r"D:\Browser\browser.exe", create_time=2.0),
    )
    stats = (
        ProcessNetworkStats(10, "browser.exe", 100, 200, 10.0, 20.0),
        ProcessNetworkStats(20, "browser.exe"),
    )

    group = aggregate_application_network(processes, stats)[0]

    assert group.upload_bytes is None
    assert group.download_bytes is None
    assert group.upload_bytes_per_second is None
    assert group.download_bytes_per_second is None


def test_application_group_key_survives_process_churn() -> None:
    first = ProcessInfo(10, "edge.exe", executable=r"C:\Program Files\Edge\edge.exe", create_time=1.0)
    second = ProcessInfo(20, "edge.exe", executable=r"C:\Program Files\Edge\edge.exe", create_time=2.0)

    assert application_key(first) == application_key(second)
