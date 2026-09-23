import pytest
from unittest.mock import Mock
from net_monitor.ui.micro_model import MicroProjection
from net_monitor.ui.rate_history import RateHistoryStore
from net_monitor.core.models import MonitorSnapshot, ProcessInfo, ProcessNetworkStats, SystemNetworkStats
from net_monitor.core.process_visibility import ProcessClassifier


class PermissiveClassifier(ProcessClassifier):
    """Classifier that accepts all processes for testing."""
    def is_visible(self, process):
        return True


def test_longevity_bounded_state():
    """10k+ update longevity test - verify state remains bounded."""
    projection = MicroProjection(classifier=PermissiveClassifier())
    rate_store = RateHistoryStore()
    projection.set_rate_history_store(rate_store)
    
    # Create a realistic snapshot
    processes = tuple(
        ProcessInfo(pid=i, name=f"app{i}.exe", executable=f"C:\\app{i}.exe", create_time=1000.0)
        for i in range(1, 11)
    )
    network_stats = tuple(
        ProcessNetworkStats(pid=i, name=f"app{i}.exe", upload_bytes=i*1000, download_bytes=i*2000,
                           upload_bytes_per_second=100.0, download_bytes_per_second=200.0)
        for i in range(1, 11)
    )
    system_stats = SystemNetworkStats(
        bytes_sent=0,
        bytes_received=0,
        upload_bytes_per_second=0.0,
        download_bytes_per_second=0.0
    )
    snapshot = MonitorSnapshot(
        system=system_stats,
        processes=processes,
        process_network=network_stats,
        process_network_state=Mock(available=True, status="available"),
        application_session=tuple()
    )
    
    # Simulate 15,000 updates
    for _ in range(15000):
        projection.receive(snapshot)
        frame = projection.frame()
        assert frame is not None
    
    # Verify state remains bounded (flexible count due to filtering)
    initial_groups = len(projection._groups)
    assert initial_groups <= 10, "Groups should not exceed input count"
    assert len(projection._accounts) == 0, "Accounts should not grow"
    
    # Verify rate history is bounded
    assert len(rate_store._series) <= 10, "Rate history apps should not exceed input count"
    for key, series in rate_store._series.items():
        assert len(series._samples) <= 120, f"Rate history samples for {key} should be <= 120"
    
    # Run another 5,000 iterations to verify state doesn't grow
    for _ in range(5000):
        projection.receive(snapshot)
        frame = projection.frame()
        assert frame is not None
    
    # Verify state still bounded after 20,000 total iterations
    assert len(projection._groups) == initial_groups, "Groups should not grow over time"
    assert len(projection._accounts) == 0, "Accounts should not grow over time"
    for key, series in rate_store._series.items():
        assert len(series._samples) <= 120, f"Rate history samples for {key} should remain <= 120"
    
    print(f"✓ Longevity test passed: 20,000 updates, {initial_groups} groups, state bounded")
