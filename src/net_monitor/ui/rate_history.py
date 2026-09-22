"""Bounded application rate history for Stage 3E sparklines.

Pure logic module: no Qt, no ETW, no collector. Consumes already-computed
application rates from MonitorSnapshot and maintains a fixed-duration ring
buffer per application key.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time


@dataclass(frozen=True, slots=True)
class RateSample:
    """One instantaneous rate observation for an application.

    upload_bytes_per_second and download_bytes_per_second can be None to
    indicate unknown/unavailable rate (UNKNOWN != 0). Only actual measured
    zero rates should be stored as 0.0.
    """

    timestamp: float
    upload_bytes_per_second: float | None
    download_bytes_per_second: float | None


@dataclass(slots=True)
class RateSeries:
    """Bounded time series for one application key.

    Maintains both time-based expiry (duration_seconds) and sample count
    limit (maxlen). Samples older than duration_seconds are pruned on access.
    """

    application_key: str
    samples: deque[RateSample]
    duration_seconds: float

    def __init__(self, application_key: str, maxlen: int, duration_seconds: float) -> None:
        self.application_key = application_key
        self.samples = deque(maxlen=maxlen)
        self.duration_seconds = duration_seconds

    def record(self, timestamp: float, upload_bps: float | None, download_bps: float | None) -> None:
        """Append one sample. Validates timestamp ordering."""
        if self.samples and timestamp < self.samples[-1].timestamp:
            # Reject out-of-order timestamps to maintain monotonic time axis
            return
        self.samples.append(RateSample(timestamp, upload_bps, download_bps))

    def as_tuple(self, now: float) -> tuple[RateSample, ...]:
        """Return samples within the time window (oldest first).

        Prunes samples older than duration_seconds from the reference time.
        """
        cutoff = now - self.duration_seconds
        # Remove expired samples from the left
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()
        return tuple(self.samples)

    def __len__(self) -> int:
        return len(self.samples)


class RateHistoryStore:
    """Bounded store of per-application rate series.

    Parameters
    ----------
    duration_seconds : float
        Time window for history. Samples older than this are pruned.
    expected_interval_seconds : float
        Nominal sampling interval (e.g. 0.5 for 500 ms heartbeat).
    max_applications : int
        Hard cap on tracked applications. Oldest-evicted when exceeded.
    clock : callable
        Monotonic clock for timestamps. Defaults to time.monotonic.
    """

    def __init__(
        self,
        *,
        duration_seconds: float = 60.0,
        expected_interval_seconds: float = 0.5,
        max_applications: int = 32,
        clock: callable = time.monotonic,
    ) -> None:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if expected_interval_seconds <= 0:
            raise ValueError("expected_interval_seconds must be positive")
        if max_applications <= 0:
            raise ValueError("max_applications must be positive")

        self._duration_seconds = duration_seconds
        self._expected_interval_seconds = expected_interval_seconds
        self._max_applications = max_applications
        self._clock = clock
        self._max_samples = max(1, int(duration_seconds / expected_interval_seconds))
        self._series: dict[str, RateSeries] = {}
        self._last_seen: dict[str, float] = {}

    @property
    def max_samples(self) -> int:
        """Maximum samples per series (derived from duration / interval)."""
        return self._max_samples

    @property
    def max_applications(self) -> int:
        """Hard cap on tracked applications."""
        return self._max_applications

    @property
    def duration_seconds(self) -> float:
        """Target history duration."""
        return self._duration_seconds

    def record(
        self,
        application_key: str,
        upload_bytes_per_second: float | None,
        download_bytes_per_second: float | None,
        *,
        timestamp: float | None = None,
    ) -> None:
        """Record one rate observation for an application.

        None rates are preserved as None (UNKNOWN != 0). The application
        key is the sole identity; PID changes within the same trusted key do
        not create a new series.
        """
        if timestamp is None:
            timestamp = self._clock()

        if application_key not in self._series:
            self._evict_if_needed(application_key)
            self._series[application_key] = RateSeries(
                application_key, self._max_samples, self._duration_seconds
            )

        self._series[application_key].record(timestamp, upload_bytes_per_second, download_bytes_per_second)
        self._last_seen[application_key] = timestamp

    def get_series(self, application_key: str, *, now: float | None = None) -> tuple[RateSample, ...]:
        """Return the current sample history for one application (oldest first).

        Prunes samples older than duration_seconds. If now is None, uses the
        injected clock. Accessing a key refreshes its last-seen timestamp for
        LRU eviction purposes.
        """
        series = self._series.get(application_key)
        if series is None:
            return ()
        if now is None:
            now = self._clock()
        # Refresh last-seen timestamp for LRU eviction
        self._last_seen[application_key] = now
        return series.as_tuple(now)

    def tracked_keys(self) -> tuple[str, ...]:
        """Return all currently tracked application keys."""
        return tuple(self._series.keys())

    def _evict_if_needed(self, new_key: str) -> None:
        """Evict the least-recently-updated application if at capacity."""
        if len(self._series) < self._max_applications:
            return
        if new_key in self._series:
            return

        # Evict the oldest (least recently seen) application.
        oldest_key = min(self._last_seen, key=self._last_seen.get)
        del self._series[oldest_key]
        del self._last_seen[oldest_key]

    def clear(self) -> None:
        """Remove all history. Used for testing or reset scenarios."""
        self._series.clear()
        self._last_seen.clear()
