import re

# 1. Update controller.py to pass groups with the signal
with open('src/net_monitor/ui/controller.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change signal definition
content = content.replace(
    'snapshot_ready = Signal(object)',
    'snapshot_ready = Signal(object, object)'
)

# Change signal emission to include groups
old_emit = '''        if snapshot is not None:
            self._published_snapshot = snapshot
            self.snapshot_ready.emit(snapshot)'''
new_emit = '''        if snapshot is not None:
            self._published_snapshot = snapshot
            self.snapshot_ready.emit(snapshot, self.projection.groups)'''
content = content.replace(old_emit, new_emit)

with open('src/net_monitor/ui/controller.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated controller.py signal')

# 2. Update compact_window.py to accept groups parameter
with open('src/net_monitor/ui/compact_window.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change method signature
content = content.replace(
    'def apply_snapshot(self, snapshot: MonitorSnapshot) -> None:',
    'def apply_snapshot(self, snapshot: MonitorSnapshot, groups: dict = None) -> None:'
)

# Remove redundant aggregation
old_agg = '''        state = snapshot.process_network_state
        groups = aggregate_application_network(
            visible_processes(snapshot.processes, show_system=False, classifier=self._classifier),
            snapshot.process_network,
        )
        upload_rate, download_rate = self._third_party_rates(state, groups)'''
new_agg = '''        state = snapshot.process_network_state
        # Use pre-aggregated groups from controller
        if groups is None:
            groups = aggregate_application_network(
                visible_processes(snapshot.processes, show_system=False, classifier=self._classifier),
                snapshot.process_network,
            )
        groups_list = list(groups.values()) if isinstance(groups, dict) else groups
        upload_rate, download_rate = self._third_party_rates(state, groups_list)'''
content = content.replace(old_agg, new_agg)

# Update references to use groups_list
content = content.replace(
    'active = [] if not state.available else [group for group in groups if self._is_active(group)]',
    'active = [] if not state.available else [group for group in groups_list if self._is_active(group)]'
)
content = content.replace(
    'partial_unknown = any(g.upload_bytes_per_second is None or g.download_bytes_per_second is None\n                                for g in groups)',
    'partial_unknown = any(g.upload_bytes_per_second is None or g.download_bytes_per_second is None\n                                for g in groups_list)'
)

with open('src/net_monitor/ui/compact_window.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated compact_window.py')
