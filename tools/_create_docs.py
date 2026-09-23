import pathlib
content = '''# Stage 3F: Network Spotlight

**版本**: v0.4  
**日期**: 2026-09-23  
**状态**: 实现完成，待物理机验收

## 概述

Stage 3F 引入 **Network Spotlight** 功能，让用户一眼看清：
- 当前前台应用是谁
- 后台总流量是多少
- 哪个后台应用最活跃
- 后台流量占比多少

## 核心概念

### 前台应用 (Foreground Application)
- 通过 Win32 API 获取当前前台窗口的 PID
- 匹配到对应的应用分组（必须满足 PID + create_time 双重验证）
- 如果无法可靠匹配，显示为"前台应用未知"

### 后台应用 (Background Applications)
- 除前台应用外的所有可见应用
- 计算总上传/下载速率
- 找出主导后台应用（速率最高的后台应用）

### 后台占比 (Background Share)
- 后台总流量 / (前台流量 + 后台总流量)
- 如果任何数据不可靠（None 值），不显示百分比
- 避免伪造精确度

## 实现细节

### 纯逻辑模块
**文件**: src/net_monitor/ui/network_spotlight.py

核心数据结构：
- SpotlightApplication: 应用快照（key、名称、上传/下载速率）
- SpotlightFrame: 完整 Spotlight 状态（前台、后台总量、主导后台、占比）

关键函数：
- compute_network_spotlight(): 计算 Spotlight 状态
- _find_foreground_application(): 根据 foreground_pid 查找前台应用
- _compute_background_totals(): 汇总后台流量
- _find_dominant_background(): 找出主导后台应用
- _compute_background_share(): 计算后台占比

### UI 集成

#### MicroWindow（微型窗）
在状态标签下方显示 Spotlight 信息：
`
后台 91% · Steam
`
或
`
后台主导 · 94%
`

#### ApplicationCard（应用卡片）
新增"网络焦点"区域，显示：
- 当前前台应用及速率
- 后台总流量及占比
- 主导后台应用及速率

#### DetailWindow（详细窗口）
在标签页上方显示 Spotlight 摘要：
`
前台: Chrome (1.2 MiB/s)
后台: 18.7 MiB/s (91%)
主导后台: Steam (18.1 MiB/s)
`

### 控制器集成
**文件**: src/net_monitor/ui/controller.py

- 在 _refresh_views() 中调用 projection.set_foreground_pid()
- 非 micro 模式下清空 foreground_pid
- 确保每 heartbeat 最多查询一次 foreground PID

## 测试覆盖

**文件**: 	ests/test_network_spotlight.py

18 个测试用例覆盖：
1. 前台 PID 匹配可信成员
2. 前台 PID 不匹配任何应用
3. 身份不完整时不猜测前台应用
4. 后台总量计算正确
5. 主导后台应用识别正确
6. 上传/下载使用原始数值
7. 并列情况确定性排序
8. 仅前台流量时后台为 0
9. 仅后台流量时前台为 None
10. None 不等于 0
11. 未知数据不产生假比例
12. 不可用状态不产生假比例
13. 后台占比计算正确
14. 空应用列表处理
15. 无前台 PID 时所有应用为后台
16. 同一应用多个 PID 正确处理
17. 全零流量时占比为 None
18. 百分比显示正确

**运行测试**:
`ash
python -m pytest tests/test_network_spotlight.py -v
`

## 架构约束

### 未新增
- ❌ 数据库
- ❌ 持久化存储
- ❌ 新的采集器
- ❌ 新的线程
- ❌ 新的定时器
- ❌ 新的 ETW Session

### 保持
- ✅ 单 MonitorService
- ✅ 单 SamplingWorker
- ✅ 单 ETW Session
- ✅ 每 heartbeat 最多一次 foreground PID 查询
- ✅ 纯计算，无副作用

## 已知限制

1. **物理机验收待完成**: 当前仅在 CI 环境测试，需在 Windows 11 物理机上验证：
   - 100% / 125% / 150% DPI 缩放下的可读性
   - 前台/后台切换的响应速度
   - 多显示器环境下的行为
   - 长时间运行的稳定性

2. **字体环境**: CI 环境缺少完整中文字体，部分渲染测试跳过

3. **GUI Launcher**: 开发环境中 net-monitor.exe 未生成，相关测试跳过

## 下一步

- [ ] Windows 11 物理机验收
- [ ] 性能测试（CPU/内存占用）
- [ ] 用户反馈收集
- [ ] 考虑 Stage 3G（待定）

## 回滚方案

如需回滚到 Stage 3E：
`ash
git checkout feat/stage-3e-rate-history
`

## 相关文档

- [Stage 3E: Rate History](stage3e-rate-history.md)
- [Stage 3D: Micro Presence](stage3d-micro-presence.md)
- [Stage 3C: Micro Widget](stage3c-micro-widget.md)
- [Stage 3B: Integration](stage3b-integration-2026-09-17.md)
- [Stage 3A: Acceptance](stage3a-acceptance-2026-09-16.md)
'''
pathlib.Path('docs/stage3f-network-spotlight.md').write_text(content, encoding='utf-8')
print('Documentation created')
