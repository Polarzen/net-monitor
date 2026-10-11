import re

with open('src/net_monitor/ui/controller.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the duplicate aggregation in _on_snapshot with reuse of projection.groups
old_block = '''    def _on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        if self._shutdown_complete:
            return
        self._latest_snapshot = snapshot
        self.projection.receive(snapshot)
        
        # Record rates for each application group
        from net_monitor.core.application_aggregation import aggregate_application_network
        from net_monitor.core.process_visibility import visible_processes
        groups = aggregate_application_network(
            visible_processes(snapshot.processes, classifier=self.projection.classifier),
            snapshot.process_network
        )
        for group in groups:
            self._rate_history.record(
                group.key,
                group.upload_bytes_per_second,
                group.download_bytes_per_second,
            )'''

new_block = '''    def _on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        if self._shutdown_complete:
            return
        self._latest_snapshot = snapshot
        self.projection.receive(snapshot)
        
        # Record rates for each application group - reuse projection's aggregation
        for group in self.projection.groups.values():
            self._rate_history.record(
                group.key,
                group.upload_bytes_per_second,
                group.download_bytes_per_second,
            )'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('src/net_monitor/ui/controller.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: Updated controller.py')
else:
    print('ERROR: old block not found')
