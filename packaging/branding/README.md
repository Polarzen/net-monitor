# Net Monitor 应用图标

蓝色上行箭头与薄荷绿下行箭头组成近似 N 的轮廓，表达按应用监控网络上下行流量。深蓝圆角底保持桌面和托盘上的对比度，外部透明。

- `net-monitor-master.png`：内置 imagegen 生成的原始图稿，保留透明通道。
- [运行时 ICO](../../src/net_monitor/assets/net-monitor.ico)：16、20、24、32、40、48、64、128、256 像素，供 EXE、默认窗口图标和托盘共用。
- 在锁定 PySide6 构建环境中运行 `python tools/build_icon.py` 可从原图重新编码 ICO；不需要在线生成或额外运行时依赖。
- 原始 PNG 不进入产品发行目录。构建会校验运行时 ICO 和 EXE 内每一帧均与受版本控制的 ICO 相同。

## 图稿生成记录

2026-10-12，使用内置 imagegen，`transparent_background=true`。以下为最终提示词：

> Use case: logo-brand. Asset type: finished Windows desktop EXE application icon for Net Monitor, a compact per-application upload/download network traffic monitor. Design a single exceptionally crisp professional app icon, straight-on square composition. A substantial smooth dark midnight-navy rounded-square tile, with two bold interlocking vertical data-flow arrows: one electric sky-blue arrow pointing up, one fresh mint-cyan arrow pointing down. The two arrows should subtly suggest an N through their relationship and connected diagonal negative space; keep upload and download instantly legible. A restrained soft gradient and very subtle dimensional finish, generous clean geometry, high contrast, visually balanced. The icon tile fills about 90% of the square canvas. Broad silhouettes and large negative spaces designed to remain readable at 16px. True transparent alpha outside the rounded square. No text, letters, words, digits, watermark, screen mockup, extra symbols, charts, tiny dots, external shadows, decorative thin lines, border, multiple variants, or background scene. Deliver only the single centered production icon.
