"""Tests for net_monitor.ui.rate_history — bounded per-application rate store."""
from __future__ import annotations

import pytest

from net_monitor.ui.rate_history import RateHistoryStore, RateSample


# ---------------------------------------------------------------------------
# 1. Bounded samples
# ---------------------------------------------------------------------------

def test_bounded_samples():
    """max_samples = duration / interval; oldest are dropped when exceeded."""
    store = RateHistoryStore(duration_seconds=60.0, expected_interval_seconds=0.5)
    assert store.max_samples == 120

    for i in range(150):
        store.record("exe:a.exe", float(i), float(i * 2), timestamp=float(i))

    series = store.get_series("exe:a.exe")
    assert len(series) == 120
    # The first 30 samples (timestamps 0..29) were dropped; oldest remaining is 30.
    assert series[0].timestamp == 30.0
    assert series[0].upload_bytes_per_second == 30.0
    assert series[0].download_bytes_per_second == 60.0
    assert series[-1].timestamp == 149.0


# ---------------------------------------------------------------------------
# 2. Application key isolation
# ---------------------------------------------------------------------------

def test_application_key_isolation():
    """Different keys produce independent series."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=1.0)

    series_a = store.get_series("exe:a.exe")
    series_b = store.get_series("exe:b.exe")
    assert len(series_a) == 1
    assert len(series_b) == 1
    assert series_a[0].upload_bytes_per_second == 100.0
    assert series_a[0].download_bytes_per_second == 200.0
    assert series_b[0].upload_bytes_per_second == 300.0
    assert series_b[0].download_bytes_per_second == 400.0


# ---------------------------------------------------------------------------
# 3. None rates become 0.0
# ---------------------------------------------------------------------------

def test_none_rates_become_zero():
    """None upload/download are coerced to 0.0 for plotting continuity."""
    store = RateHistoryStore()
    store.record("exe:a.exe", None, None, timestamp=1.0)

    sample = store.get_series("exe:a.exe")[0]
    assert sample.upload_bytes_per_second == 0.0
    assert sample.download_bytes_per_second == 0.0


def test_none_rates_mixed_with_real():
    """Mixing None and real values: None -> 0.0, real stays."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, None, timestamp=1.0)
    store.record("exe:a.exe", None, 200.0, timestamp=2.0)

    s0, s1 = store.get_series("exe:a.exe")
    assert s0.upload_bytes_per_second == 100.0
    assert s0.download_bytes_per_second == 0.0
    assert s1.upload_bytes_per_second == 0.0
    assert s1.download_bytes_per_second == 200.0


# ---------------------------------------------------------------------------
# 4. Eviction policy (LRU by last-seen timestamp)
# ---------------------------------------------------------------------------

def test_eviction_policy():
    """With max_applications=2, adding a 3rd key evicts the least-recently-seen."""
    store = RateHistoryStore(max_applications=2)
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=2.0)
    store.record("exe:c.exe", 500.0, 600.0, timestamp=3.0)

    keys = store.tracked_keys()
    assert "exe:a.exe" not in keys  # evicted (oldest last-seen)
    assert "exe:b.exe" in keys
    assert "exe:c.exe" in keys


def test_eviction_refreshes_on_record():
    """Re-recording to a key refreshes its last-seen, protecting it from eviction."""
    store = RateHistoryStore(max_applications=2)
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=2.0)
    # Touch "a" again so it is more recent than "b"
    store.record("exe:a.exe", 150.0, 250.0, timestamp=3.0)
    # Now "b" is the least-recently-seen
    store.record("exe:c.exe", 500.0, 600.0, timestamp=4.0)

    keys = store.tracked_keys()
    assert "exe:b.exe" not in keys  # evicted
    assert "exe:a.exe" in keys
    assert "exe:c.exe" in keys


# ---------------------------------------------------------------------------
# 5. Monotonic timestamps (injected clock)
# ---------------------------------------------------------------------------

def test_monotonic_timestamps_with_injected_clock():
    """The store uses the injected clock when no explicit timestamp is given."""
    fake_times = iter([10.0, 20.0, 30.0])
    store = RateHistoryStore(clock=lambda: next(fake_times))

    store.record("exe:a.exe", 1.0, 2.0)
    store.record("exe:a.exe", 3.0, 4.0)
    store.record("exe:a.exe", 5.0, 6.0)

    series = store.get_series("exe:a.exe")
    assert [s.timestamp for s in series] == [10.0, 20.0, 30.0]


def test_explicit_timestamp_overrides_clock():
    """An explicit timestamp parameter bypasses the clock."""
    clock_called = False

    def failing_clock():
        nonlocal clock_called
        clock_called = True
        return 999.0

    store = RateHistoryStore(clock=failing_clock)
    store.record("exe:a.exe", 1.0, 2.0, timestamp=42.0)

    assert not clock_called
    assert store.get_series("exe:a.exe")[0].timestamp == 42.0


# ---------------------------------------------------------------------------
# 6. UNKNOWN != 0 — process keys are valid distinct keys
# ---------------------------------------------------------------------------

def test_unknown_key_distinct():
    """Process-style keys are treated as valid, distinct application keys."""
    store = RateHistoryStore()
    store.record("process:123:1234567890.0", 100.0, 200.0, timestamp=1.0)
    store.record("process:456:1234567891.0", 300.0, 400.0, timestamp=1.0)

    keys = store.tracked_keys()
    assert len(keys) == 2
    assert "process:123:1234567890.0" in keys
    assert "process:456:1234567891.0" in keys


# ---------------------------------------------------------------------------
# 7. STALE != 0 — series persist until evicted by capacity
# ---------------------------------------------------------------------------

def test_stale_series_persists():
    """A series with old timestamps is NOT auto-removed; only capacity eviction removes it."""
    store = RateHistoryStore(max_applications=10)
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)

    # Even after "a long time" the series is still there.
    store.record("exe:b.exe", 300.0, 400.0, timestamp=9999.0)

    assert "exe:a.exe" in store.tracked_keys()
    assert len(store.get_series("exe:a.exe")) == 1
    assert store.get_series("exe:a.exe")[0].timestamp == 1.0


# ---------------------------------------------------------------------------
# 8. get_series returns empty tuple for unknown key
# ---------------------------------------------------------------------------

def test_get_series_unknown_key():
    """Querying a non-existent key returns an empty tuple."""
    store = RateHistoryStore()
    result = store.get_series("exe:nonexistent.exe")
    assert result == ()
    assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# 9. tracked_keys returns all active keys
# ---------------------------------------------------------------------------

def test_tracked_keys():
    """After recording for 3 keys, tracked_keys() returns all 3."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=2.0)
    store.record("exe:c.exe", 500.0, 600.0, timestamp=3.0)

    keys = store.tracked_keys()
    assert isinstance(keys, tuple)
    assert set(keys) == {"exe:a.exe", "exe:b.exe", "exe:c.exe"}


# ---------------------------------------------------------------------------
# 10. clear() removes all history
# ---------------------------------------------------------------------------

def test_clear():
    """After clear(), tracked_keys() is empty and get_series() returns ()."""
    store = RateHistoryStore()
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=2.0)

    store.clear()

    assert store.tracked_keys() == ()
    assert store.get_series("exe:a.exe") == ()
    assert store.get_series("exe:b.exe") == ()


def test_clear_allows_fresh_recording():
    """After clear(), the store is fully reusable."""
    store = RateHistoryStore(max_applications=2)
    store.record("exe:a.exe", 100.0, 200.0, timestamp=1.0)
    store.record("exe:b.exe", 300.0, 400.0, timestamp=2.0)
    store.clear()

    # Can now record up to max_applications without eviction
    store.record("exe:x.exe", 1.0, 2.0, timestamp=10.0)
    store.record("exe:y.exe", 3.0, 4.0, timestamp=11.0)
    assert set(store.tracked_keys()) == {"exe:x.exe", "exe:y.exe"}


# ---------------------------------------------------------------------------
# Additional edge-case: RateSample is frozen
# ---------------------------------------------------------------------------

def test_rate_sample_is_frozen():
    """RateSample instances are immutable."""
    sample = RateSample(timestamp=1.0, upload_bytes_per_second=10.0, download_bytes_per_second=20.0)
    with pytest.raises(AttributeError):
        sample.timestamp = 2.0  # type: ignore[misc]
