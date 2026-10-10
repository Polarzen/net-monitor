"""Tests for bounded application rate history."""
from __future__ import annotations

import pytest

from net_monitor.ui.rate_history import RateHistoryStore, RateSample


def test_rate_sample_none_preserved():
    """None rates must be preserved as None (UNKNOWN != 0)."""
    store = RateHistoryStore()
    store.record("exe:a.exe", None, None, timestamp=1.0)
    samples = store.get_series("exe:a.exe", now=2.0)
    assert len(samples) == 1
    assert samples[0].upload_bytes_per_second is None
    assert samples[0].download_bytes_per_second is None


def test_rate_sample_zero_vs_none():
    """0.0 (measured zero) must be distinct from None (unknown)."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 0.0, 0.0, timestamp=1.0)
    store.record("exe:b.exe", None, None, timestamp=1.0)
    
    a_samples = store.get_series("exe:a.exe", now=2.0)
    b_samples = store.get_series("exe:b.exe", now=2.0)
    
    assert a_samples[0].upload_bytes_per_second == 0.0
    assert a_samples[0].upload_bytes_per_second is not None
    assert b_samples[0].upload_bytes_per_second is None


def test_time_based_pruning():
    """Samples older than duration_seconds must be pruned."""
    store = RateHistoryStore(duration_seconds=60.0)
    
    # Record samples at different times
    store.record("exe:a.exe", 100.0, 200.0, timestamp=10.0)
    store.record("exe:a.exe", 150.0, 250.0, timestamp=30.0)
    store.record("exe:a.exe", 200.0, 300.0, timestamp=50.0)
    store.record("exe:a.exe", 250.0, 350.0, timestamp=80.0)
    
    # At time 100, samples at 10 and 30 should be pruned (>60s old)
    samples = store.get_series("exe:a.exe", now=100.0)
    assert len(samples) == 2
    assert samples[0].timestamp == 50.0
    assert samples[1].timestamp == 80.0


def test_max_samples_hard_limit():
    """max_samples=120 is a hard limit even within time window."""
    store = RateHistoryStore(duration_seconds=60.0, expected_interval_seconds=0.5)
    assert store.max_samples == 120
    
    # Record 150 samples all within a short time span (15 seconds)
    # This ensures all samples are within the 60-second window
    for i in range(150):
        store.record("exe:a.exe", float(i), float(i), timestamp=float(i * 0.1))
    
    # Query at time 20.0, so cutoff is -40.0
    # All samples (0.0 to 14.9) are within the window
    # The hard limit of 120 should be enforced by the deque
    samples = store.get_series("exe:a.exe", now=20.0)
    assert len(samples) == 120  # Hard limit enforced
    # The oldest 30 samples should have been dropped
    assert samples[0].timestamp == 3.0  # Sample 30 (30 * 0.1 = 3.0)
    assert samples[-1].timestamp == 14.9  # Sample 149 (149 * 0.1 = 14.9)


def test_timestamp_ordering_rejects_out_of_order():
    """Out-of-order timestamps must be rejected."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=10.0)
    store.record("exe:a.exe", 150.0, 250.0, timestamp=20.0)
    
    # Try to record with earlier timestamp - should be rejected
    store.record("exe:a.exe", 999.0, 999.0, timestamp=15.0)
    
    samples = store.get_series("exe:a.exe", now=30.0)
    assert len(samples) == 2
    assert samples[0].timestamp == 10.0
    assert samples[1].timestamp == 20.0


def test_timestamp_ordering_accepts_monotonic():
    """Monotonic timestamps must be accepted."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=10.0)
    store.record("exe:a.exe", 150.0, 250.0, timestamp=20.0)
    store.record("exe:a.exe", 200.0, 300.0, timestamp=30.0)
    
    samples = store.get_series("exe:a.exe", now=40.0)
    assert len(samples) == 3


def test_application_key_isolation():
    """Different application keys must have independent histories."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=1.0)
    
    a_samples = store.get_series("exe:a.exe", now=2.0)
    b_samples = store.get_series("exe:b.exe", now=2.0)
    
    assert len(a_samples) == 1
    assert len(b_samples) == 1
    assert a_samples[0].upload_bytes_per_second == 100.0
    assert b_samples[0].upload_bytes_per_second == 300.0


def test_lru_eviction():
    """When max_applications is reached, least-recently-seen key is evicted."""
    store = RateHistoryStore(max_applications=2)
    
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 150.0, 250.0, timestamp=2.0)
    store.record("exe:c.exe", 200.0, 300.0, timestamp=3.0)  # Should evict a.exe
    
    keys = store.tracked_keys()
    assert "exe:a.exe" not in keys
    assert "exe:b.exe" in keys
    assert "exe:c.exe" in keys


def test_lru_refresh_on_access():
    """Accessing a key refreshes its last-seen timestamp."""
    store = RateHistoryStore(max_applications=2)
    
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 150.0, 250.0, timestamp=2.0)
    
    # Access a.exe to refresh its last-seen
    store.get_series("exe:a.exe", now=3.0)
    
    store.record("exe:c.exe", 200.0, 300.0, timestamp=4.0)  # Should evict b.exe, not a.exe
    
    keys = store.tracked_keys()
    assert "exe:a.exe" in keys
    assert "exe:b.exe" not in keys
    assert "exe:c.exe" in keys


def test_get_series_with_explicit_now():
    """get_series() must accept explicit now parameter for testing."""
    store = RateHistoryStore(duration_seconds=10.0)
    store.record("exe:a.exe", 100.0, 200.0, timestamp=5.0)
    
    # At time 12, sample should still be present
    samples = store.get_series("exe:a.exe", now=12.0)
    assert len(samples) == 1
    
    # At time 20, sample should be pruned
    samples = store.get_series("exe:a.exe", now=20.0)
    assert len(samples) == 0


def test_unknown_application_key():
    """Querying unknown key returns empty tuple."""
    store = RateHistoryStore()
    samples = store.get_series("exe:nonexistent.exe", now=1.0)
    assert samples == ()


def test_clear():
    """clear() removes all history."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=2.0)
    
    store.clear()
    
    assert store.tracked_keys() == ()
    assert store.get_series("exe:a.exe", now=3.0) == ()


def test_mixed_none_and_real_rates():
    """Mixing None and real rates in same series."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, None, timestamp=1.0)
    store.record("exe:a.exe", None, 200.0, timestamp=2.0)
    store.record("exe:a.exe", 150.0, 250.0, timestamp=3.0)
    
    samples = store.get_series("exe:a.exe", now=4.0)
    assert len(samples) == 3
    assert samples[0].upload_bytes_per_second == 100.0
    assert samples[0].download_bytes_per_second is None
    assert samples[1].upload_bytes_per_second is None
    assert samples[1].download_bytes_per_second == 200.0
    assert samples[2].upload_bytes_per_second == 150.0
    assert samples[2].download_bytes_per_second == 250.0
