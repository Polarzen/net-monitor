"""Pure logic for Network Spotlight: foreground/background/dominant computation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpotlightApplication:
    key: str
    name: str
    executable: str | None
    upload_bps: float | None
    download_bps: float | None

    @property
    def total_bps(self) -> float | None:
        if self.upload_bps is None or self.download_bps is None:
            return None
        return self.upload_bps + self.download_bps


@dataclass(frozen=True, slots=True)
class SpotlightFrame:
    foreground: SpotlightApplication | None
    background_total_bps: float | None
    background_upload_bps: float | None
    background_download_bps: float | None
    dominant_background: SpotlightApplication | None
    background_share: float | None
    source_usable: bool
    share_reliable: bool

    @property
    def background_share_percent(self) -> int | None:
        if self.background_share is None or not self.share_reliable:
            return None
        return round(self.background_share * 100)


def compute_network_spotlight(groups, foreground_pid, source_usable):
    if not source_usable:
        return SpotlightFrame(
            foreground=None,
            background_total_bps=None,
            background_upload_bps=None,
            background_download_bps=None,
            dominant_background=None,
            background_share=None,
            source_usable=False,
            share_reliable=False,
        )
    if not groups:
        return SpotlightFrame(
            foreground=None,
            background_total_bps=0.0,
            background_upload_bps=0.0,
            background_download_bps=0.0,
            dominant_background=None,
            background_share=None,
            source_usable=True,
            share_reliable=True,
        )
    foreground_app = _find_foreground_application(groups, foreground_pid)
    background_groups = []
    for key, group in groups.items():
        if foreground_app is not None and key == foreground_app.key:
            continue
        background_groups.append(group)
    background_total, background_upload, background_download, all_reliable = (
        _compute_background_totals(background_groups)
    )
    dominant = _find_dominant_background(background_groups) if background_groups else None
    foreground_total = foreground_app.total_bps if foreground_app else None
    share, share_reliable = _compute_background_share(
        foreground_total, background_total, all_reliable
    )
    return SpotlightFrame(
        foreground=foreground_app,
        background_total_bps=background_total,
        background_upload_bps=background_upload,
        background_download_bps=background_download,
        dominant_background=dominant,
        background_share=share,
        source_usable=True,
        share_reliable=share_reliable,
    )


def _find_foreground_application(groups, foreground_pid):
    if foreground_pid is None:
        return None
    for key, group in groups.items():
        for process in group.processes:
            if process.pid == foreground_pid:
                if process.create_time is None:
                    continue
                return SpotlightApplication(
                    key=group.key,
                    name=group.name,
                    executable=group.executable,
                    upload_bps=group.upload_bytes_per_second,
                    download_bps=group.download_bytes_per_second,
                )
    return None


def _compute_background_totals(background_groups):
    if not background_groups:
        return 0.0, 0.0, 0.0, True
    total_upload = 0.0
    total_download = 0.0
    all_reliable = True
    for group in background_groups:
        upload = group.upload_bytes_per_second
        download = group.download_bytes_per_second
        if upload is None or download is None:
            all_reliable = False
            continue
        total_upload += upload
        total_download += download
    total = total_upload + total_download
    return total, total_upload, total_download, all_reliable


def _find_dominant_background(background_groups):
    if not background_groups:
        return None
    candidates = []
    for group in background_groups:
        upload = group.upload_bytes_per_second
        download = group.download_bytes_per_second
        if upload is None or download is None:
            continue
        total = upload + download
        candidates.append((total, group.name.casefold(), group))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1]))
    _, _, dominant_group = candidates[0]
    return SpotlightApplication(
        key=dominant_group.key,
        name=dominant_group.name,
        executable=dominant_group.executable,
        upload_bps=dominant_group.upload_bytes_per_second,
        download_bps=dominant_group.download_bytes_per_second,
    )


def _compute_background_share(foreground_total, background_total, all_reliable):
    if not all_reliable:
        return None, False
    if foreground_total is None or background_total is None:
        return None, False
    combined = foreground_total + background_total
    if combined <= 0:
        return None, True
    share = background_total / combined
    return share, True
