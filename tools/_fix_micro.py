import pathlib
content = pathlib.Path('src/net_monitor/ui/micro_window.py').read_text(encoding='utf-8')
old = '''        # Add spotlight context to state_label if available
        spotlight_text = \"\"
        if hasattr(frame, 'spotlight') and frame.spotlight and frame.spotlight.source_usable:
            sp = frame.spotlight
            if sp.background_share is not None and sp.share_reliable:
                pct = round(sp.background_share * 100)
                if sp.dominant_background:
                    if frame.selected and sp.dominant_background.key == frame.selected.key:
                        spotlight_text = f\"\\n后台主导 · {pct}%\"
                    else:
                        dom_name = sp.dominant_background.name
                        spotlight_text = f\"\\n后台 {pct}% · {dom_name}\"
                elif pct > 0:
                    spotlight_text = f\"\\n后台 {pct}%\"
            elif sp.foreground is None and frame.source_usable:
                spotlight_text = \"\\n前台应用未知\"
        
        set_text(self.state_label, activity + spotlight_text)
        tooltip_sp = spotlight_text.replace(\"\\n\", \" \") if spotlight_text else \"\"
        self.setToolTip(f\"{name}\\n{frame.presence.value}\\n{activity}{tooltip_sp}\\n{frame.message}\\n\"
                        \"↓ 下载 / ↑ 上传；B 是字节，KiB=1024 B。点击展开，右键菜单。\")'''
new = '''        # Spotlight context goes into tooltip only to avoid 220x112 clipping
        spotlight_tip = \"\"
        if hasattr(frame, 'spotlight') and frame.spotlight and frame.spotlight.source_usable:
            sp = frame.spotlight
            if sp.background_share is not None and sp.share_reliable:
                pct = round(sp.background_share * 100)
                if sp.dominant_background:
                    if frame.selected and sp.dominant_background.key == frame.selected.key:
                        spotlight_tip = f\"后台主导 {pct}%\"
                    else:
                        spotlight_tip = f\"后台 {pct}% · {sp.dominant_background.name}\"
                elif pct > 0:
                    spotlight_tip = f\"后台 {pct}%\"
            if sp.foreground is not None:
                fg_tip = f\"前台: {sp.foreground.name}\"
                spotlight_tip = fg_tip + (\"\\n\" + spotlight_tip if spotlight_tip else \"\")
        extra = \"\\n\" + spotlight_tip if spotlight_tip else \"\"
        set_text(self.state_label, activity)
        self.setToolTip(f\"{name}\\n{frame.presence.value}\\n{activity}{extra}\\n{frame.message}\\n\"
                        \"↓ 下载 / ↑ 上传；B 是字节，KiB=1024 B。点击展开，右键菜单。\")'''
if old in content:
    content = content.replace(old, new)
    pathlib.Path('src/net_monitor/ui/micro_window.py').write_text(content, encoding='utf-8')
    print('Fixed')
else:
    print('NOT FOUND')
