from net_monitor.core.formatting import format_bytes_per_second
from net_monitor.core.models import ProcessInfo, ProcessNetworkStats, SystemNetworkStats


def test_models_can_be_constructed() -> None:
    process = ProcessInfo(pid=42, name="demo.exe", executable="C:/demo.exe", status="running")
    network = ProcessNetworkStats(pid=42, name="demo.exe")
    system = SystemNetworkStats(100, 200, 10.0, 20.0)
    assert process.pid == 42
    assert network.upload_bytes is None
    assert system.bytes_received == 200


def test_format_bytes_per_second() -> None:
    assert format_bytes_per_second(512) == "512 B/s"
    assert format_bytes_per_second(1280) == "1.25 KB/s"
    assert format_bytes_per_second(8.42 * 1024 * 1024) == "8.42 MB/s"
    assert format_bytes_per_second(-1) == "0 B/s"
