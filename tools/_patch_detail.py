import pathlib

content = pathlib.Path('src/net_monitor/ui/detail_window.py').read_text(encoding='utf-8')

# Add SpotlightFrame import
old_import = 'from net_monitor.ui.micro_model import SESSION_CAPTION'
new_import = '''from net_monitor.ui.micro_model import SESSION_CAPTION
from net_monitor.ui.network_spotlight import SpotlightFrame'''
content = content.replace(old_import, new_import)

# Add spotlight label in __init__
old_init = '''        self.tabs = QTabWidget()
        self.session_view = SessionView()
        self.tabs.addTab(self.live_page, "当前应用 / PID")
        self.tabs.addTab(self.session_view, SESSION_CAPTION)
        self.setCentralWidget(self.tabs)'''

new_init = '''        # Spotlight summary label
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt
        self._spotlight_label = QLabel()
        self._spotlight_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._spotlight_label.setWordWrap(True)
        self._spotlight_label.setStyleSheet('QLabel { padding: 8px; background: #2a2a2a; border-radius: 4px; margin: 4px; }')
        self._spotlight_label.setVisible(False)
        
        self.tabs = QTabWidget()
        self.session_view = SessionView()
        self.tabs.addTab(self.live_page, "当前应用 / PID")
        self.tabs.addTab(self.session_view, SESSION_CAPTION)
        
        # Vertical layout with spotlight on top
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._spotlight_label)
        central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)'''

content = content.replace(old_init, new_init)

# Add update_spotlight method before apply_snapshot
old_apply = '''    def apply_snapshot(self, snapshot: MonitorSnapshot) -> None:'''
new_apply = '''    def update_spotlight(self, frame) -> None:
        """Update spotlight summary from WidgetFrame."""
        if frame is None or not hasattr(frame, 'spotlight') or frame.spotlight is None:
            self._spotlight_label.setVisible(False)
            return
        
        spotlight = frame.spotlight
        if not spotlight.source_usable:
            self._spotlight_label.setVisible(False)
            return
        
        lines = []
        
        # Foreground
        if spotlight.foreground is not None:
            fg_name = spotlight.foreground.name
            fg_total = spotlight.foreground.total_bps
            if fg_total is not None:
                from net_monitor.core.formatting import format_bytes_per_second
                lines.append(f'前台: {fg_name} ({format_bytes_per_second(fg_total)})')
            else:
                lines.append(f'前台: {fg_name}')
        else:
            lines.append('前台: 未知')
        
        # Background
        bg_total = spotlight.background_total_bps
        if bg_total is not None:
            from net_monitor.core.formatting import format_bytes_per_second
            bg_text = format_bytes_per_second(bg_total)
            if spotlight.background_share is not None and spotlight.share_reliable:
                pct = round(spotlight.background_share * 100)
                lines.append(f'后台: {bg_text} ({pct}%)')
            else:
                lines.append(f'后台: {bg_text}')
        else:
            lines.append('后台: 无活动')
        
        # Dominant background
        if spotlight.dominant_background is not None:
            dom_name = spotlight.dominant_background.name
            dom_total = spotlight.dominant_background.total_bps
            if dom_total is not None:
                from net_monitor.core.formatting import format_bytes_per_second
                lines.append(f'主导后台: {dom_name} ({format_bytes_per_second(dom_total)})')
            else:
                lines.append(f'主导后台: {dom_name}')
        
        self._spotlight_label.setText('\\n'.join(lines))
        self._spotlight_label.setVisible(True)

    def apply_snapshot(self, snapshot: MonitorSnapshot) -> None:'''

content = content.replace(old_apply, new_apply)

pathlib.Path('src/net_monitor/ui/detail_window.py').write_text(content, encoding='utf-8')
print('DetailWindow updated')
