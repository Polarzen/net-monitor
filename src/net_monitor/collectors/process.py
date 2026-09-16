from __future__ import annotations

import psutil

from net_monitor.core.models import ProcessInfo


class ProcessCollector:
    def __init__(self, *, include_status: bool = True) -> None:
        self._include_status = include_status

    def collect(self) -> tuple[ProcessInfo, ...]:
        processes: list[ProcessInfo] = []
        attrs = ["pid", "name", "exe", "create_time"]
        if self._include_status:
            attrs.insert(3, "status")
        for proc in psutil.process_iter(attrs):
            try:
                info = proc.info
                create_time = info.get("create_time")
                processes.append(
                    ProcessInfo(
                        pid=int(info["pid"]),
                        name=str(info.get("name") or f"PID {info['pid']}"),
                        executable=info.get("exe"),
                        status=info.get("status") if self._include_status else None,
                        create_time=float(create_time) if create_time is not None else None,
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        return tuple(sorted(processes, key=lambda item: (item.name.lower(), item.pid)))
