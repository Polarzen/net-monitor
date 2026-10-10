from __future__ import annotations

from dataclasses import dataclass
import ntpath

from net_monitor.core.models import ProcessInfo, ProcessNetworkStats


@dataclass(slots=True, frozen=True)
class ApplicationNetworkGroup:
    """A conservative application-level view of one or more process instances.

    Processes are grouped only when they expose the same normalized executable
    path. Entries without a readable executable path remain separate so the UI
    never merges unrelated UNKNOWN processes merely because their names match.
    """

    key: str
    name: str
    executable: str | None
    processes: tuple[ProcessInfo, ...]
    upload_bytes: int | None
    download_bytes: int | None
    upload_bytes_per_second: float | None
    download_bytes_per_second: float | None

    @property
    def process_count(self) -> int:
        return len(self.processes)

    @property
    def process_identities(self) -> tuple[tuple[int, float | None], ...]:
        return tuple(process.identity for process in self.processes)


def application_key(process: ProcessInfo) -> str:
    """Return a stable, conservative aggregation key for a process."""

    if process.executable:
        normalized = ntpath.normcase(ntpath.normpath(process.executable))
        return f"exe:{normalized}"
    create_time = "none" if process.create_time is None else repr(process.create_time)
    return f"process:{process.pid}:{create_time}"


def aggregate_application_network(
    processes: tuple[ProcessInfo, ...] | list[ProcessInfo],
    network_rows: tuple[ProcessNetworkStats, ...] | list[ProcessNetworkStats],
) -> tuple[ApplicationNetworkGroup, ...]:
    """Aggregate network counters for processes that share an executable path.

    Optional network values are deliberately propagated: if any member lacks a
    trustworthy value, the aggregate value is unavailable instead of treating
    missing data as zero.
    """

    network_by_pid = {row.pid: row for row in network_rows}
    grouped: dict[str, list[ProcessInfo]] = {}
    for process in processes:
        grouped.setdefault(application_key(process), []).append(process)

    result: list[ApplicationNetworkGroup] = []
    for key, members in grouped.items():
        members.sort(key=lambda process: (process.pid, process.create_time or -1.0))
        member_tuple = tuple(members)
        executable = member_tuple[0].executable
        name = _application_name(member_tuple[0])
        rows = [network_by_pid.get(process.pid) for process in member_tuple]

        result.append(
            ApplicationNetworkGroup(
                key=key,
                name=name,
                executable=executable,
                processes=member_tuple,
                upload_bytes=_sum_field(rows, "upload_bytes"),
                download_bytes=_sum_field(rows, "download_bytes"),
                upload_bytes_per_second=_sum_field(rows, "upload_bytes_per_second"),
                download_bytes_per_second=_sum_field(rows, "download_bytes_per_second"),
            )
        )

    result.sort(key=lambda group: (group.name.casefold(), group.key))
    return tuple(result)


def _application_name(process: ProcessInfo) -> str:
    if process.executable:
        basename = ntpath.basename(process.executable)
        if basename:
            return basename
    return process.name


def _sum_field(
    rows: list[ProcessNetworkStats | None],
    field: str,
) -> int | float | None:
    values: list[int | float] = []
    for row in rows:
        if row is None:
            return None
        value = getattr(row, field)
        if value is None:
            return None
        values.append(value)
    return sum(values)
