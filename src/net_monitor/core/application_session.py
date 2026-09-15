from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import ntpath

from net_monitor.core.application_aggregation import application_key
from net_monitor.core.models import (
    ApplicationSessionStats,
    ProcessInfo,
    ProcessNetworkStats,
    RetiredProcessNetworkStats,
)

ProcessIdentity = tuple[int, float | None]


@dataclass(slots=True)
class _ProcessAttribution:
    key: str
    last_upload_bytes: int
    last_download_bytes: int


@dataclass(slots=True)
class _ApplicationTotals:
    key: str
    name: str
    executable: str | None
    upload_bytes: int = 0
    download_bytes: int = 0


class ApplicationSessionTracker:
    """Accumulate per-application bytes across process churn for one app session.

    Process identity is `(pid, create_time)`. The first trustworthy cumulative
    sample contributes its current value, and later samples contribute only
    monotonic deltas. Once an identity is first attributed, its application key
    remains fixed for the rest of the session; this avoids speculative merging
    when executable metadata is temporarily unavailable.
    """

    def __init__(self) -> None:
        self._processes: dict[ProcessIdentity, _ProcessAttribution] = {}
        self._applications: dict[str, _ApplicationTotals] = {}

    def update(
        self,
        processes: tuple[ProcessInfo, ...],
        network_rows: tuple[ProcessNetworkStats, ...],
        retired: tuple[RetiredProcessNetworkStats, ...] = (),
    ) -> tuple[ApplicationSessionStats, ...]:
        network_by_pid = {row.pid: row for row in network_rows}

        for process in processes:
            row = network_by_pid.get(process.pid)
            if row is not None:
                self._observe(process, row)

        for sample in retired:
            self._observe(sample.process, sample.network)

        return self.snapshot(processes)

    def snapshot(
        self,
        active_processes: tuple[ProcessInfo, ...] = (),
    ) -> tuple[ApplicationSessionStats, ...]:
        active_counts: Counter[str] = Counter()
        for process in active_processes:
            attribution = self._processes.get(process.identity)
            key = attribution.key if attribution is not None else application_key(process)
            active_counts[key] += 1

        result = [
            ApplicationSessionStats(
                key=totals.key,
                name=totals.name,
                executable=totals.executable,
                upload_bytes=totals.upload_bytes,
                download_bytes=totals.download_bytes,
                active_process_count=active_counts.get(totals.key, 0),
            )
            for totals in self._applications.values()
        ]
        result.sort(key=lambda item: (item.name.casefold(), item.key))
        return tuple(result)

    def _observe(self, process: ProcessInfo, row: ProcessNetworkStats) -> None:
        if row.upload_bytes is None or row.download_bytes is None:
            return

        upload = max(0, int(row.upload_bytes))
        download = max(0, int(row.download_bytes))
        identity = process.identity
        attribution = self._processes.get(identity)

        if attribution is None:
            key = application_key(process)
            totals = self._applications.get(key)
            if totals is None:
                totals = _ApplicationTotals(
                    key=key,
                    name=_application_name(process),
                    executable=process.executable,
                )
                self._applications[key] = totals
            totals.upload_bytes += upload
            totals.download_bytes += download
            self._processes[identity] = _ProcessAttribution(
                key=key,
                last_upload_bytes=upload,
                last_download_bytes=download,
            )
            return

        totals = self._applications[attribution.key]
        totals.upload_bytes += max(0, upload - attribution.last_upload_bytes)
        totals.download_bytes += max(0, download - attribution.last_download_bytes)
        attribution.last_upload_bytes = upload
        attribution.last_download_bytes = download


def _application_name(process: ProcessInfo) -> str:
    if process.executable:
        basename = ntpath.basename(process.executable)
        if basename:
            return basename
    return process.name
