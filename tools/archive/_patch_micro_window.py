import re

with open('src/net_monitor/ui/micro_window.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the state_label text construction in apply_frame and add spotlight info
old_state_block = '''        set_text(self.state_label, activity)
        self.setToolTip(f\"{name}\\n{frame.presence.value}\\n{activity}\\n{frame.message}\\n\"
                        \"↓ 下载 / ↑ 上传；B 是字节，KiB=1024 B。点击展开，右键菜单。\")'''

new_state_block = '''        # Add spotlight context to state_label if available
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

content = content.replace(old_state_block, new_state_block)

with open('src/net_monitor/ui/micro_window.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched micro_window.py')
