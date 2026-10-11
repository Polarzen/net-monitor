
import pathlib
content = pathlib.Path('src/net_monitor/ui/micro_model.py').read_text(encoding='utf-8')

# 1. Add import after rate_history import
old_import = 'from net_monitor.ui.rate_history import RateSample'
new_import = old_import + chr(10) + 'from net_monitor.ui.network_spotlight import SpotlightFrame, compute_network_spotlight'
content = content.replace(old_import, new_import, 1)

# 2. Add spotlight field to WidgetFrame
old_field = '    rate_history: tuple[RateSample, ...] = ()'
new_field = old_field + chr(10) + '    spotlight: SpotlightFrame | None = None'
content = content.replace(old_field, new_field, 1)

# 3. Add foreground_pid tracking to __init__
old_init_marker = '        self._rate_history_store = None'
new_init_marker = old_init_marker + chr(10) + '        self._spotlight_foreground_pid = None'
content = content.replace(old_init_marker, new_init_marker, 1)

# 4. Add set_foreground_pid method after set_rate_history_store
old_method = '    def set_rate_history_store(self, store) -> None:' + chr(10) + '        ' + chr(34)*3 + 'Attach a RateHistoryStore so frame() can populate rate_history.' + chr(34)*3 + chr(10) + '        self._rate_history_store = store'
new_method = old_method + chr(10)*2 + '    def set_foreground_pid(self, pid: int | None) -> None:' + chr(10) + '        ' + chr(34)*3 + 'Set the current foreground PID for spotlight computation.' + chr(34)*3 + chr(10) + '        self._spotlight_foreground_pid = pid'
content = content.replace(old_method, new_method, 1)

# 5. Compute spotlight in frame() and pass to WidgetFrame
old_return = '        return WidgetFrame(selected, state, source, message, upload, download,' + chr(10) + '                           ranked, self.choices(), self._focus is not None, account, partial,' + chr(10) + '                           self.cached_presence_state(), history)'
new_return = '        spotlight = compute_network_spotlight(' + chr(10) + '            self._groups, self._spotlight_foreground_pid,' + chr(10) + '            source is DisplayState.ACTIVE,' + chr(10) + '        )' + chr(10) + '        return WidgetFrame(selected, state, source, message, upload, download,' + chr(10) + '                           ranked, self.choices(), self._focus is not None, account, partial,' + chr(10) + '                           self.cached_presence_state(), history, spotlight)'
content = content.replace(old_return, new_return, 1)

pathlib.Path('src/net_monitor/ui/micro_model.py').write_text(content, encoding='utf-8')
print('OK')
