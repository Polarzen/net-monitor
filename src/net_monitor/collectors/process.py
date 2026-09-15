from __future__ import annotations

import psutil

from net_monitor.core.models import ProcessInfo


class ProcessCollector:
    def collect(self) -> tuple[ProcessInfo, ...]:
        processes: list[ProcessInfo] = []
        for proc in psutil.process_iter(["pid", "name", "exe", "status", "create_time"]):
            try:
                info = proc.info
                create_time = info.get("create_time")
                processes.append(
                    ProcessInfo(
                        pid=int(info["pid"]),
                        name=str(info.get("name") or f"PID {info['pid']}"),
                        executable=info.get("exe"),
                        status=info.get("status"),
                        create_time=float(create_time) if create_time is not None else None,
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        return tuple(sorted(processes, key=lambda item: (item.name.lower(), item.pid)))
