"""Read-only UI projection. No counter accumulation or process attribution."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
import math
import time

from net_monitor.core.application_aggregation import (
    ApplicationNetworkGroup, aggregate_application_network,
)
from net_monitor.core.models import (
    ApplicationSessionStats, MonitorSnapshot, ProcessNetworkState, ProcessNetworkStatus,
)
from net_monitor.core.process_visibility import ProcessClassifier, visible_processes
from net_monitor.ui.session_model import observed_process_count
from net_monitor.ui.rate_history import RateSample

CHALLENGER_SECONDS = 2.0
STALE_SECONDS = 4.0
HOVER_MS = 350
COLLAPSE_MS = 300
UI_TICK_MS = 500
MICRO_SIZE = (220, 112)
MICRO_MAX_SIZE = (240, 140)
SESSION_CAPTION = "本次监控累计"
SESSION_EXPLANATION = (
    "仅为当前 Net Monitor 进程运行期间已确认的数据；不是关注以来、应用全部历史或运营商账单。"
    "不跨 Net Monitor 重启保存；代理、回环及虚拟网卡不保证外网去重。"
)


class DisplayState(str, Enum):
    STARTING = "启动中"
    ACTIVE = "当前有流量"
    IDLE = "当前无流量"
    PERMISSION = "需要管理员权限"
    UNAVAILABLE = "采集不可用"
    FAILED = "采样失败"
    STALE = "数据已过期"
    NOT_RUNNING = "未运行"
    UNKNOWN = "数据或身份未知"
    EMPTY = "暂无可见应用数据"


class PresenceState(str, Enum):
    """Conservative foreground state for the currently selected application."""

    FOREGROUND = "前台"
    BACKGROUND = "后台"
    UNKNOWN = "状态未知"


@dataclass(frozen=True, slots=True)
class PresenceContext:
    """Identity evidence copied from one already-cached application group."""

    selected_key: str | None
    trusted_member_pids: frozenset[int]
    identity_complete: bool
    member_identities: frozenset[tuple[int, float | None]] = frozenset()

    @property
    def trusted_pids(self) -> frozenset[int]:
        """Short alias for callers that only need the trusted PID set."""

        return self.trusted_member_pids


def resolve_presence(context: PresenceContext, foreground_pid: int | None) -> PresenceState:
    """Resolve foreground/background without treating an unknown PID as safe."""

    if (context.selected_key is None or not isinstance(foreground_pid, int)
            or foreground_pid <= 0):
        return PresenceState.UNKNOWN
    if foreground_pid in context.trusted_member_pids:
        return PresenceState.FOREGROUND
    if context.identity_complete:
        return PresenceState.BACKGROUND
    return PresenceState.UNKNOWN


# Descriptive aliases keep the pure rule easy to discover for callers/tests.
classify_presence = resolve_presence
evaluate_presence = resolve_presence


@dataclass(frozen=True, slots=True)
class AppChoice:
    key: str
    name: str
    executable: str | None
    can_follow: bool = True


@dataclass(frozen=True, slots=True)
class RankedApp:
    choice: AppChoice
    upload: float
    download: float


@dataclass(frozen=True, slots=True)
class WidgetFrame:
    selected: AppChoice | None
    state: DisplayState
    source_state: DisplayState
    message: str
    upload: float | None
    download: float | None
    top: tuple[RankedApp, ...]
    choices: tuple[AppChoice, ...]
    focused: bool
    account: ApplicationSessionStats | None
    partial_unknown: bool = False
    presence: PresenceState = PresenceState.UNKNOWN
    rate_history: tuple[RateSample, ...] = ()

    @property
    def source_usable(self) -> bool:
        return self.source_state is DisplayState.ACTIVE


def rate_number(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def format_rate(value: float | int | None, *, compact: bool = False) -> str:
    """Byte/s; explicit IEC units. Positive sub-byte rates never become zero."""
    number = rate_number(value)
    if number is None:
        return "—"
    if number == 0:
        return "0 B/s"
    if number < 0.1:
        return "<0.1 B/s"
    units = ("B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s", "PiB/s", "EiB/s", "ZiB/s", "YiB/s")
    index = 0
    while number >= 1024 and index < len(units) - 1:
        number /= 1024
        index += 1
    if compact and number >= 10000:
        return f">999{units[index]}"
    if number >= 10000:
        text = f"{number:.1e}"
    elif compact:
        # At most four significant digits; the window never changes its width.
        text = f"{number:.0f}" if number >= 100 else f"{number:.1f}"
    else:
        text = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text}{'' if compact and index else ' '}{units[index]}"


def format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    # Raw bytes remain visible; no precision is lost to float conversion.
    return f"{value:,} B"


def _choice(group: ApplicationNetworkGroup) -> AppChoice:
    stable = bool(group.executable) or all(p.create_time is not None for p in group.processes)
    return AppChoice(group.key, group.name, group.executable, stable)


def _score(group: ApplicationNetworkGroup) -> float | None:
    upload = rate_number(group.upload_bytes_per_second)
    download = rate_number(group.download_bytes_per_second)
    if upload is None or download is None:
        return None
    return rate_number(upload + download)


class MicroProjection:
    """Select an application, never smooth rates or reconstruct session totals.

    The first valid frame chooses immediately. A different strictly faster
    leader must remain ahead for CHALLENGER_SECONDS while the current app is
    active. Only received snapshots advance that evidence, not heartbeat ticks.
    """

    def __init__(
        self, *, clock: Callable[[], float] = time.monotonic,
        classifier: ProcessClassifier | None = None,
        challenger_seconds: float = CHALLENGER_SECONDS,
        stale_seconds: float = STALE_SECONDS,
    ) -> None:
        self.clock = clock
        self.classifier = classifier or ProcessClassifier()
        self.challenger_seconds = challenger_seconds
        self.stale_seconds = stale_seconds
        self.snapshot: MonitorSnapshot | None = None
        self.last_valid_at: float | None = None
        self._created_at = clock()
        self._received_at: float | None = None
        self._failure: str | None = None
        self._groups: dict[str, ApplicationNetworkGroup] = {}
        self._accounts: dict[str, ApplicationSessionStats] = {}
        self._auto_key: str | None = None
        self._challenger: str | None = None
        self._challenger_since = 0.0
        self._focus: AppChoice | None = None
        self._presence = PresenceState.UNKNOWN
        self._presence_context: PresenceContext | None = None
        self._rate_history_store = None

    def set_rate_history_store(self, store) -> None:
        """Attach a RateHistoryStore so frame() can populate rate_history."""
        self._rate_history_store = store

    def receive(self, snapshot: MonitorSnapshot) -> None:
        now = self.clock()
        # A gap is not evidence of a continuously leading challenger.
        if self._received_at is not None and now - self._received_at >= self.stale_seconds:
            self._challenger = None
        self.snapshot = snapshot
        self._received_at = now
        self._failure = None
        self._groups = {g.key: g for g in aggregate_application_network(
            visible_processes(snapshot.processes, classifier=self.classifier),
            snapshot.process_network,
        )}
        self._accounts = {a.key: a for a in snapshot.application_session}
        if snapshot.process_network_state.available:
            self.last_valid_at = now
            if self._focus is None:
                self._select_auto(now)
        else:
            self._challenger = None

    def fail(self, message: str) -> None:
        self._failure = message or "采样未成功完成"
        self._challenger = None

    def choices(self) -> tuple[AppChoice, ...]:
        choices = {key: _choice(group) for key, group in self._groups.items()}
        # Do not silently drop exited accounts just because history lacks category.
        for account in self._accounts.values():
            if account.active_process_count == 0:
                choices.setdefault(account.key, AppChoice(account.key, account.name, account.executable))
        return tuple(sorted(choices.values(), key=lambda c: (c.name.casefold(), c.key)))

    def follow(self, key: str) -> bool:
        choice = next((c for c in self.choices() if c.key == key), None)
        if choice is None or not choice.can_follow:
            return False
        self._focus = choice
        self._challenger = None
        return True

    def unfollow(self) -> None:
        self._focus = None
        self._auto_key = None
        self._challenger = None
        if self.snapshot is not None and self.source_state() is DisplayState.ACTIVE:
            self._select_auto(self.clock())

    def presence_context(self) -> PresenceContext:
        """Return identity evidence from the selected cached application group."""

        key = self._focus.key if self._focus else self._auto_key
        group = self._groups.get(key or "")
        if group is None or not group.processes:
            return PresenceContext(key if group is not None else None, frozenset(), False)
        trusted = frozenset(process.pid for process in group.processes
                             if process.create_time is not None)
        return PresenceContext(group.key, trusted,
                               all(process.create_time is not None for process in group.processes),
                               frozenset(process.identity for process in group.processes))

    def set_presence_state(self, state: PresenceState,
                           context: PresenceContext | None = None) -> None:
        self._presence = state
        self._presence_context = context if context is not None else self.presence_context()

    def cached_presence_state(self) -> PresenceState:
        """Reuse a poll only while its selected identity context is unchanged."""

        if self._presence_context != self.presence_context():
            self._presence = PresenceState.UNKNOWN
            self._presence_context = None
        return self._presence

    def source_state(self) -> DisplayState:
        if self._failure is not None:
            return DisplayState.FAILED
        snapshot = self.snapshot
        if snapshot is None:
            return (DisplayState.STALE if self.clock() - self._created_at >= self.stale_seconds
                    else DisplayState.STARTING)
        status = snapshot.process_network_state.status
        if status is ProcessNetworkStatus.PERMISSION_DENIED:
            return DisplayState.PERMISSION
        if status in (ProcessNetworkStatus.UNAVAILABLE, ProcessNetworkStatus.STOPPED):
            return DisplayState.UNAVAILABLE
        if status is ProcessNetworkStatus.STARTING:
            anchor = self._received_at if self._received_at is not None else self._created_at
            return (DisplayState.STALE if self.clock() - anchor >= self.stale_seconds
                    else DisplayState.STARTING)
        if self.last_valid_at is None or self.clock() - self.last_valid_at >= self.stale_seconds:
            return DisplayState.STALE
        return DisplayState.ACTIVE

    def _ranked_groups(self) -> list[ApplicationNetworkGroup]:
        candidates = [g for g in self._groups.values() if (_score(g) or 0) > 0]
        return sorted(candidates, key=lambda g: (-float(_score(g)), g.name.casefold(), g.key))

    def _select_auto(self, now: float) -> None:
        ranked = self._ranked_groups()
        if not ranked:
            self._auto_key = self._challenger = None
            return
        leader = ranked[0]
        current = self._groups.get(self._auto_key or "")
        current_score = None if current is None else _score(current)
        if current_score is None or current_score == 0:
            self._auto_key = leader.key
            self._challenger = None
        elif leader.key == self._auto_key or float(_score(leader)) <= current_score:
            self._challenger = None
        elif self._challenger != leader.key:
            self._challenger, self._challenger_since = leader.key, now
        elif now - self._challenger_since >= self.challenger_seconds:
            self._auto_key, self._challenger = leader.key, None

    def frame(self) -> WidgetFrame:
        source = self.source_state()
        key = self._focus.key if self._focus else self._auto_key
        group = self._groups.get(key or "")
        selected = _choice(group) if group is not None else self._focus
        account = self._accounts.get(key or "")
        # No name/PID fallback. Even exact keys cannot certify unknown identities.
        if group is not None and any(p.create_time is None for p in group.processes):
            account = None
        partial = any(_score(g) is None for g in self._groups.values())
        state, message = source, source.value
        upload = download = None
        ranked: tuple[RankedApp, ...] = ()
        if source is DisplayState.ACTIVE:
            ranked = tuple(RankedApp(_choice(g), float(g.upload_bytes_per_second),
                                     float(g.download_bytes_per_second))
                           for g in self._ranked_groups()[:3])
            if group is not None:
                upload = rate_number(group.upload_bytes_per_second)
                download = rate_number(group.download_bytes_per_second)
                score = _score(group)
                state = (DisplayState.UNKNOWN if score is None else
                         DisplayState.ACTIVE if score > 0 else DisplayState.IDLE)
                message = state.value
                if not _choice(group).can_follow:
                    state, message = DisplayState.UNKNOWN, "当前速率可见，但身份不稳定；不能跨刷新固定关注或关联累计"
            elif self._focus is not None:
                # A missing row alone is never evidence of exit.
                if (account is not None and self.snapshot is not None
                        and observed_process_count(account, self.snapshot) == 0):
                    state, message = DisplayState.NOT_RUNNING, "按当前可信账户与进程枚举：未运行"
                    upload = download = 0.0
                else:
                    state, message = DisplayState.UNKNOWN, "无法可靠关联当前进程；不据缺失数据判断退出"
            elif not self._groups:
                state, message = DisplayState.EMPTY, "暂无可见应用数据；不代表整机没有网络活动"
            elif partial:
                state, message = DisplayState.UNKNOWN, "部分应用数据未知；不能判断全部空闲"
            else:
                state, message = DisplayState.IDLE, "当前默认可见应用未观察到流量"
                upload = download = 0.0
        elif source is DisplayState.FAILED:
            message = f"采样失败：{self._failure}"
        elif source is DisplayState.STALE:
            message = "数据更新已停止；旧速率不作为实时值。已确认累计仍保留。"
        elif self.snapshot is not None:
            message = self.snapshot.process_network_state.message or source.value
        history: tuple[RateSample, ...] = ()
        if selected is not None and self._rate_history_store is not None:
            history = self._rate_history_store.get_series(selected.key)
        return WidgetFrame(selected, state, source, message, upload, download,
                           ranked, self.choices(), self._focus is not None, account, partial,
                           self.cached_presence_state(), history)

    def display_snapshot(self) -> MonitorSnapshot | None:
        """Fresh snapshots keep identity. Failure/staleness produces a UI-only copy."""
        snapshot = self.snapshot
        if snapshot is None or self.source_state() is DisplayState.ACTIVE:
            return snapshot
        source = self.source_state()
        status = snapshot.process_network_state.status
        if source in (DisplayState.STALE, DisplayState.FAILED):
            status = ProcessNetworkStatus.UNAVAILABLE
        return replace(snapshot,
                       process_network=tuple(replace(row, upload_bytes_per_second=None,
                                                     download_bytes_per_second=None)
                                             for row in snapshot.process_network),
                       process_network_state=ProcessNetworkState(status, self.frame().message,
                                                                 snapshot.process_network_state.error_code))
