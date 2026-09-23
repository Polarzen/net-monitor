import pathlib

content = pathlib.Path('src/net_monitor/ui/micro_window.py').read_text(encoding='utf-8')

# 1. Add spotlight labels after session_totals in __init__
old_session = '        self.session_totals = SessionTotals()'
new_session = '''        self.session_totals = SessionTotals()
        # Network Spotlight section
        self.spotlight_caption = plain_label("网络焦点")
        self.spotlight_caption.setStyleSheet("font-weight:600;")
        self.spotlight_fg_label = plain_label("前台应用：—")
        self.spotlight_bg_label = plain_label("后台合计：—")
        self.spotlight_dom_label = plain_label("后台主导：—")'''
content = content.replace(old_session, new_session, 1)

# 2. Add spotlight widgets to layout after session_totals
old_layout = '        self.body_layout.addWidget(self.session_totals)'
new_layout = '''        self.body_layout.addWidget(self.session_totals)
        self.body_layout.addWidget(self.spotlight_caption)
        self.body_layout.addWidget(self.spotlight_fg_label)
        self.body_layout.addWidget(self.spotlight_bg_label)
        self.body_layout.addWidget(self.spotlight_dom_label)'''
content = content.replace(old_layout, new_layout, 1)

# 3. Add spotlight update in apply_frame, after session_totals.apply_frame
old_apply = '        self.session_totals.apply_frame(frame)'
new_apply = '''        self.session_totals.apply_frame(frame)
        # Update Network Spotlight section
        sp = getattr(frame, 'spotlight', None)
        if sp is not None and sp.source_usable:
            self.spotlight_caption.show()
            self.spotlight_fg_label.show()
            self.spotlight_bg_label.show()
            self.spotlight_dom_label.show()
            if sp.foreground is not None:
                fg_rate = format_rate(sp.foreground.total_bps, compact=True)
                set_text(self.spotlight_fg_label, f"当前前台：{sp.foreground.name}  {fg_rate}")
            else:
                set_text(self.spotlight_fg_label, "当前前台：未知")
            if sp.background_total_bps is not None:
                bg_rate = format_rate(sp.background_total_bps, compact=True)
                if sp.background_share is not None and sp.share_reliable:
                    pct = round(sp.background_share * 100)
                    set_text(self.spotlight_bg_label, f"后台合计：{bg_rate}（占已识别流量 {pct}%）")
                else:
                    set_text(self.spotlight_bg_label, f"后台合计：{bg_rate}")
            else:
                set_text(self.spotlight_bg_label, "后台合计：—")
            if sp.dominant_background is not None:
                dom_rate = format_rate(sp.dominant_background.total_bps, compact=True)
                set_text(self.spotlight_dom_label, f"后台主导：{sp.dominant_background.name}  {dom_rate}")
            else:
                set_text(self.spotlight_dom_label, "后台主导：无")
        else:
            self.spotlight_caption.hide()
            self.spotlight_fg_label.hide()
            self.spotlight_bg_label.hide()
            self.spotlight_dom_label.hide()'''
content = content.replace(old_apply, new_apply, 1)

pathlib.Path('src/net_monitor/ui/micro_window.py').write_text(content, encoding='utf-8')
print('Patched ApplicationCard with spotlight section')
