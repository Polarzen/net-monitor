"""Read-only account presentation; never add bytes or infer attribution."""
from __future__ import annotations

from dataclasses import dataclass

from net_monitor.core.models import ApplicationSessionStats, MonitorSnapshot


@dataclass(frozen=True, slots=True)
class SessionRow:
    account: ApplicationSessionStats
    process_count: int | None
    presence: str


def observed_process_count(account: ApplicationSessionStats, snapshot: MonitorSnapshot) -> int | None:
    """A count describes the latest enumeration, not current network activity.

    Missing identities can make a zero count inconclusive. Do not use a PID or
    name to guess which historical account such a process belongs to.
    """
    return _count(account, snapshot.process_network_state.available,
                  any(p.create_time is None for p in snapshot.processes))


def _count(account: ApplicationSessionStats, available: bool, identity_missing: bool) -> int | None:
    count = account.active_process_count
    return None if not available or count < 0 or (count == 0 and identity_missing) else count


def session_rows(snapshot: MonitorSnapshot) -> tuple[SessionRow, ...]:
    # Accounts are supplied by the tracker. Metadata changes replace the same
    # key's presentation, never create another UI balance or add an increment.
    accounts = {account.key: account for account in snapshot.application_session}
    # Scan the enumeration once, not once per retained/retired account.
    identity_missing = any(p.create_time is None for p in snapshot.processes)
    available = snapshot.process_network_state.available
    rows = []
    for account in accounts.values():
        count = _count(account, available, identity_missing)
        presence = "进程状态未知" if count is None else "未运行" if count == 0 else "最近枚举有进程"
        rows.append(SessionRow(account, count, presence))
    return tuple(sorted(rows, key=lambda row: (row.account.name.casefold(), row.account.key)))
