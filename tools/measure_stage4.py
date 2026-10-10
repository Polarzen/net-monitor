"""Offline UI workload, never imported by the product; NOT a real ETW benchmark.

Run each revision in a separate process with the same interpreter and fixed fake
application identities. CPU 100% means one fully occupied logical processor.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--scenario', choices=('micro', 'detail', 'hidden', 'cycles'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--warmup', type=float, default=30)
    parser.add_argument('--duration', type=float, default=120)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve() / 'src'))
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    import psutil
    import PySide6
    from PySide6.QtCore import QObject, QTimer, qVersion
    from PySide6.QtWidgets import QApplication
    from layout_fonts import configure_application
    from net_monitor.core.application_aggregation import application_key
    from net_monitor.core.models import (ApplicationSessionStats, MonitorSnapshot,
        ProcessInfo, ProcessNetworkState, ProcessNetworkStats, ProcessNetworkStatus, SystemNetworkStats)
    import net_monitor.ui.controller as module
    from net_monitor.ui.compact_window import CompactWindow
    from net_monitor.ui.detail_window import DetailWindow
    from net_monitor.ui.main_window import MainWindow
    from net_monitor.ui.micro_window import ApplicationCard, MicroWindow
    from net_monitor.ui.micro_model import MicroProjection
    from net_monitor.ui.rate_history import RateHistoryStore
    from net_monitor.ui.icon_cache import IconCache
    from net_monitor.ui.session_view import SessionView
    from net_monitor.ui.preferences import PreferencesStore

    counts = Counter()
    hidden_counts = Counter()
    for cls, name in ((MicroWindow, 'apply_frame'), (ApplicationCard, 'apply_frame'),
                      (CompactWindow, 'apply_snapshot'), (DetailWindow, 'apply_snapshot'),
                      (MainWindow, '_sync_tree'), (SessionView, '_flush'),
                      (RateHistoryStore, 'get_series'), (MicroProjection, 'frame'),
                      (IconCache, 'request')):
        original = getattr(cls, name)
        label = f'{cls.__name__}.{name}'
        def wrapped(self, *a, _original=original, _label=label, **kw):
            counts[_label] += 1
            if hasattr(self, 'isVisible') and not self.isVisible():
                hidden_counts[_label] += 1
            return _original(self, *a, **kw)
        setattr(cls, name, wrapped)

    class Service:
        def close(self):
            pass
    class Tray:
        available = True
        def __init__(self, **callbacks):
            pass
        def set_always_on_top_checked(self, enabled):
            pass
        def hide(self):
            pass
    module.TrayController = Tray
    app = QApplication([])
    font = configure_application(app)
    from net_monitor.ui.theme import DARK_STYLESHEET
    app.setStyleSheet(DARK_STYLESHEET)
    processes = tuple(ProcessInfo(1000+i, f'App{i//4:02d}.exe',
                     rf'D:\FakeApps\App{i//4:02d}.exe', create_time=100.+i) for i in range(96))
    accounts = tuple(ApplicationSessionStats(application_key(p), p.name, p.executable,
                     10000, 20000, 4) for p in processes[::4])
    def snapshot(tick):
        rows = tuple(ProcessNetworkStats(p.pid, p.name, 10000+tick*100,
                     20000+tick*1000, float(100+i+tick%4), float(1000+i*10+tick%4))
                     for i, p in enumerate(processes))
        return MonitorSnapshot(SystemNetworkStats(0,0,0,0), processes, rows,
                               ProcessNetworkState(ProcessNetworkStatus.AVAILABLE),
                               tuple(replace(a, upload_bytes=10000+tick*400,
                                             download_bytes=20000+tick*4000) for a in accounts))
    with tempfile.TemporaryDirectory(prefix='net-monitor-stage4-bench-') as temp:
        c = module.UiController(service=Service(), start_worker=False,
             preferences_store=PreferencesStore(Path(temp)/'ui.json'),
             icon_reader=lambda path: None, foreground_pid_reader=lambda: 1000)
        detail = c.show_details()
        detail.close()
        if args.scenario == 'micro':
            c.show_primary(activate=False)
        elif args.scenario == 'detail':
            c.show_details()
        proc = psutil.Process()
        records = []
        tick = 0
        cycles = 0
        started = time.monotonic()
        next_tick = started
        next_observation = started + args.warmup
        measuring = False
        try:
            while time.monotonic()-started < args.warmup+args.duration:
                now = time.monotonic()
                if now >= next_tick:
                    c._on_snapshot(snapshot(tick))
                    tick += 1
                    next_tick += .5
                    if args.scenario == 'cycles':
                        c.show_primary(activate=False)
                        c.show_card()
                        assert c.show_details() is detail
                        detail.tabs.setCurrentIndex(tick % 2)
                        c.show_compact()
                        c.show_micro()
                        detail.close()
                        c._close_primary()
                        cycles += 1
                app.processEvents()
                if now >= next_observation:
                    if not measuring:
                        measuring = True
                        measurement_started = time.monotonic()
                        counts.clear()
                        hidden_counts.clear()
                        proc.cpu_percent()
                    else:
                        memory = proc.memory_info()
                        records.append({'elapsed': time.monotonic()-measurement_started,
                            'cpu_one_core_percent': proc.cpu_percent(),
                            'working_set_bytes': memory.rss,
                            'private_bytes': getattr(memory, 'private', None),
                            'threads': proc.num_threads(), 'handles': proc.num_handles(),
                            'qt_widgets': len(app.allWidgets()),
                            'qt_objects': len(c.findChildren(QObject)),
                            'controller_timers': len(c.findChildren(QTimer)),
                            'history_apps': len(c._rate_history.tracked_keys()),
                            'history_points': sum(len(s.samples) for s in c._rate_history._series.values()),
                            'session_accounts': len(c.projection._accounts)})
                    next_observation += 1
                time.sleep(.005)
        finally:
            c.shutdown()
        elapsed = time.monotonic()-measurement_started
        def stats(key):
            values = sorted(r[key] for r in records if r[key] is not None)
            return {'mean': statistics.mean(values), 'p95': values[math.ceil(.95*len(values))-1],
                    'min': min(values), 'max': max(values), 'first': records[0][key], 'last': records[-1][key]}
        result = {'revision': args.revision, 'source': str(args.source.resolve()),
            'source_sha256': {str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((args.source/'src/net_monitor/ui').glob('*.py'))},
            'scenario': args.scenario, 'real_etw': False, 'fake_snapshot': True,
            'physical_desktop': False, 'qt_platform': app.platformName(),
            'windows': platform.platform(), 'python': sys.version, 'executable': sys.executable,
            'qt': qVersion(), 'pyside': PySide6.__version__, 'psutil': psutil.__version__,
            'logical_processors': psutil.cpu_count(), 'font': font,
            'warmup_seconds': args.warmup, 'observed_seconds': elapsed,
            'cpu_convention': '100% = one logical processor; divide by logical_processors for total-machine %',
            'load': {'applications':24,'processes':96,'sample_interval_seconds':.5,
                     'snapshots':tick,'window_cycles':cycles,'icon_reader':'fake None'},
            'summary': {k:stats(k) for k in records[0] if k != 'elapsed'},
            'calls': dict(counts), 'hidden_calls': dict(hidden_counts), 'samples':records}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output':str(args.output),'seconds':elapsed,'calls':dict(counts)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
