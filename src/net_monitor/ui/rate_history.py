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
    """One instantaneous rate observation for an application."""

    timestamp: float
    upload_bytes_per_second: float
    download_bytes_per_second: float


@dataclass(slots=True)
class RateSeries:
    """Bounded time series for one application key.

    The deque maxlen enforces a hard cap on samples. With a 500 ms heartbeat
    and 60 s duration, maxlen=120 provides ~60 s of history.
    """

    application_key: str
    samples: deque[RateSample]

    def __init__(self, application_key: str, maxlen: int) -> None:
        self.application_key = application_key
        self.samples = deque(maxlen=maxlen)

    def record(self, timestamp: float, upload_bps: float, download_bps: float) -> None:
        """Append one sample. Oldest samples are automatically dropped."""
        self.samples.append(RateSample(timestamp, upload_bps, download_bps))

    def as_tuple(self) -> tuple[RateSample, ...]:
        """Return a snapshot of current samples (oldest first)."""
        return tuple(self.samples)

    def __len__(self) -> int:
        return len(self.samples)


class RateHistoryStore:
    """Bounded store of per-application rate series.

    Parameters
    ----------
    duration_seconds : float
        Target history window. Actual sample count is derived from
        expected_interval_seconds to avoid depending on exact timing.
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

        None rates are treated as 0.0 for plotting continuity. The application
        key is the sole identity; PID changes within the same trusted key do
        not create a new series.
        """
        if timestamp is None:
            timestamp = self._clock()

        upload = 0.0 if upload_bytes_per_second is None else float(upload_bytes_per_second)
        download = 0.0 if download_bytes_per_second is None else float(download_bytes_per_second)

        if application_key not in self._series:
            self._evict_if_needed(application_key)
            self._series[application_key] = RateSeries(application_key, self._max_samples)

        self._series[application_key].record(timestamp, upload, download)
        self._last_seen[application_key] = timestamp

    def get_series(self, application_key: str) -> tuple[RateSample, ...]:
        """Return the current sample history for one application (oldest first)."""
        series = self._series.get(application_key)
        return series.as_tuple() if series is not None else ()

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
