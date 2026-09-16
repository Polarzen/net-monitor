# Stage 3A 本轮验收记录（2026-09-16）

状态：**本轮验收与修复已执行；本地自动测试、真实 ETW、主要桌面项及最终正常退出已有实际记录，修复版运行时长超过 30 分钟；Stage 3A 保留监测记录缺口、CPU 性能风险及最终本地提交未运行 CI 等未完事项，尚未宣告无保留全部完成。**

本记录对应分支 `feat/etw-process-collector`，baseline HEAD 为
`d9752d3b85a131417029f12bc556fbe785bef986`。记录只保留本轮验收所需事实，不保存原始大日志、无关进程名或内部配置。

## 环境与基线

Windows 11 家庭中文版 `10.0.26200`（build 26200），Python `3.14.7`，net-monitor `0.2.0`，PySide6 `6.11.2`，psutil `7.2.2`，pytest `9.1.1`。

初始工作区为 clean；已核对分支、最近 10 条提交、README、pyproject 和 GitHub workflows。

本轮范围为 README、验收记录、`monitor_service.py`、`test_monitor_service.py`、`collector_probe.py` 和 `test_collector_probe.py` 六个文件；未新增依赖或产品功能。

## 本次实际通过

### 本次自动验证

- 文档修改后最终执行 `.\.venv\Scripts\python.exe -m pytest -ra`：`2026-09-16T18:03:05.247+08:00` 至 `18:03:07.349+08:00`，退出码 `0`；`92` 项收集，`91 passed`、`0 failed`、`1 skipped`。跳过项为 `tests/test_stage3a_ui.py:204`，原因是 runner 没有真实系统托盘。

- 自动测试：`.\.venv\Scripts\python.exe -m pytest -ra` 于 `15:48:52.739` 至 `15:48:54.557`（+08）完成，`87` 项收集，`86 passed`、`0 failed`、`1 skipped`。唯一跳过项为 `tests/test_stage3a_ui.py:204`，原因是 runner 没有真实系统托盘。

### 本次桌面观察


- 非管理员自动化桌面观察：Compact 显示真实权限提示；Detailed 可打开并复用同一窗口；关闭 Detailed 只隐藏窗口；关闭 Compact 只隐藏窗口且进程仍存活。
- 用户于 `15:57` 重启并接受 UAC 后，管理员运行实例已启动。Root 约 `16:06` 的真实截图确认程序运行中、有非零下载/上传速率，Compact 在 150% 缩放下（QtDPR `1.5`、logical DPI `96`）无明显裁切。
- 无控制台启动链路已观察为 `net-monitor.exe` → `pythonw.exe`。

### 本次管理员 ETW 自动验证

- 管理员权限 ETW probes 均成功：raw probe 两次分别于 `16:17:31.347` 至 `16:17:33.736`、`16:17:33.798` 至 `16:17:36.064` 退出码 `0`；collector probe 两次分别于 `16:17:36.068` 至 `16:17:38.396`、`16:17:38.401` 至 `16:17:40.936` 退出码 `0`。使用现有模块 `.\.venv\Scripts\python.exe -m net_monitor.collectors.etw.probe` 与 `collector_probe`，raw 两次共用会话名 `NetMonitor-Admin-20260916-081730-13dc89a9-Raw`，collector 两次共用对应 `-Collector` 会话名，均无残留冲突。

### 本次修复版 ETW 自动验证与首轮观察

- 修复版管理员 raw probe 两次于 `17:07:32.776` 至 `17:07:37.400` 完成，collector probe 两次于 `17:07:37.405` 至 `17:07:43.015` 完成，全部退出码 `0`，同类同名会话复用成功且无冲突。raw 每次双向各 `524288` bytes（`send1/receive6`）；collector 每次双向各 `524288` bytes，正速率约 `2,095,382/2,094,804 B/s`（约 `2.0 MiB/s`），`available`、`closed`、`identity_verified`、`rates_recovered`、`idle_totals_stable` 均为真。idle rates 均为 `0.0`，连续稳定总量窗口分别为 `0.5005041s`、`0.5006945s`。受控子进程身份包含 psutil 的 PID、name、executable、create_time 字段（PID `13280`、`43904`，name 均为 `python.exe`，executable 为受控 Python）。

- 首轮实机观察从 `16:17:43.474` 至 `16:47:44.780+08`，持续 `1801.306` 秒、`31` 个样本；全部样本 `responding`、`session_query_ok`、`session_present` 均为真。working set 完整范围为 `17,559,552–63,143,936` bytes，private 完整范围为 `41,975,808–50,049,024` bytes；CPU 单逻辑核区间 `84.65–96.03%`、均值 `90.62%`，bad samples 为 `0`。该轮是修复前单 runtime 观察，不能代表修复版第二轮结果。
- 已最小修复系统计数器读取在慢枚举后、速率时间戳取枚举前的问题；`tests/test_monitor_service.py` 的 `8` 项针对性验证通过，旧实现 `33.333/66.667` 的回归值现为 `100/200`。

### 本次修复版第二轮自动观察

- 修复版同一 GUI family（3 进程）从 `17:07:49.271+08` 运行至 `17:48:28.582+08`，总时长 `2439.311s`（`40m39.311s`），期间无重启；Root 约 `17:38` 的真实截图仍显示运行中且数值变化，无明显裁切。总计 `35` 个资源样本，working set 完整范围 `17,633,280–96,038,912` bytes，private 完整范围 `43,311,104–49,987,584` bytes（首值 `43,311,104`、末值 `44,834,816`）；CPU 全时段均值约为单逻辑核 `85.9675%`、`32` 逻辑核整机约 `2.6865%`，续观察均值单核 `91.9095%`。自动记录存在 `455.085s`（约 `7m35s`）间隔缺口，不能写作连续每分钟无缺口。
- 续记录从 `17:38:25.586` 至 `17:48:28.578`，共 `11` 个样本；`600s` 目标实际运行 `603.504s`。精确 session 查询均退出码 `0`，三个进程均保持 `responding` 且正常；续脚本的中文 OEM 输出解码使 status 文字为 `unknown`，不能宣称该字符串解析通过，证据依赖退出码 `0` 与独立 `Running` 查询。
- 观察期间未见崩溃、卡死、停止更新或样本持续异常内存增长；这不等于排除长期泄漏。

### 本次托盘与 UAC 人工观察

- 约 `17:28+08` 用户确认修复版托盘隐藏后恢复、Detailed 单实例复用和窗口持续更新均正常；这些是用户实机观察，不能用共享服务源码或单元测试支持替代独立实机对象证据。

- 用户在 `17:00` 前通过托盘右键退出全部旧实例；`16:55:50` 核对相关进程均已退出，精确 ETW session `NetMonitor-ProcessNetwork-PoC-3bf1426e-4a08-4210-ad5a-9ced9d12191e` 的 `logman` 查询为 `notfound`。
- `16:57:27` 另开非管理员实例并取消 UAC 后，原窗口保持正常运行，随后经托盘退出；`16:59:03` 核对该路径实例均已退出。接受和取消 UAC 路径均有人工事实。
- 管理员下两个窗口中途显示正常、持续更新且无裁切；自动化管理员 Detailed 点击未成功属于工具限制，不作为程序失败结论。
- 首轮 Detailed 中途打开后内存上升但未崩溃；这不构成无长期泄漏结论。
- 用户确认窗口正常并从托盘退出后，于 `17:58:32.461+08` 核查本轮已知进程和 worker `remaining=[]`；六个精确 ETW session 查询均为 `Data Collector Set was not found`、退出码 `-2144337918`，包括两次 GUI session、两组 raw/collector session。进程、worker 和 session 均已释放，未强杀进程或停止其他 session。

## 仅源码或历史证据

- README 与现有源码描述了 Compact/Detailed、Tray、提权重启和单采集器设计；这些内容是设计或源码证据，不能替代尚未完成的桌面验收。
- 以下三次 workflow 运行均为 baseline HEAD `d9752d3b85a131417029f12bc556fbe785bef986` 的 exact HEAD 历史结果，状态为 `completed/success`：
  - [CI #34979881270](https://github.com/Polarzen/net-monitor/actions/runs/34979881270)
  - [ETW Experiment #34973522989](https://github.com/Polarzen/net-monitor/actions/runs/34973522989)
  - [CI #34973522976](https://github.com/Polarzen/net-monitor/actions/runs/34973522976)
- 当前工作区的后续修复和测试改动尚未形成新的远端提交，也没有为新 HEAD 运行 CI；上述历史结果不覆盖新 HEAD。

## 失败或受限

- 非管理员 `permission_probe` 于 `15:49:14.990` 至 `15:49:15.174` 退出码 `0`，但 JSON 为 `success=false`，`EnableTraceEx2` 返回 code `5`。
- 非管理员 `liveprobe` 于 `15:49:44.222` 至 `15:49:44.472` 退出码 `1`，原因为同一权限错误。未产生测试流量，精确 session 查询为 `not found`，相关 Python 进程计数为 `0`。
- 上述 probe 失败反映权限前置条件未满足，不能作为代码失败结论，也不能作为管理员 probe 的替代证据。
- 首轮观察脚本完成后等待人工退出超过 `300` 秒，原因是 Root 通知较晚，不是程序退出失败。
- 独立 ProcessCollector 诊断在约 `380` 个进程上耗时 `3.127` 至 `4.792` 秒，超过 `2` 秒刷新周期，构成性能风险；保持现有刷新与身份语义，不做任意降频。
- 自动化管理员 Detailed 点击未成功属于工具限制，不作为程序失败结论。
- 修复版原 observer 于 `17:30:50.501+08` 运行 `1381.229` 秒、采集到第 `24` 个样本时，因完整 `logman query -ets` 的 WMI GUID 查询退出码 `-2147020696`（`0x80071068`）而停止。三个 GUI 进程当时仍存活且 `responding=true`；约 `17:32` 的精确 session 查询显示 `Running`、`BuffersLost=0`。这是监测工具故障和记录缺口，不是应用崩溃。

## 保留事项与后续复核

- 修复版第二轮已有超过 30 分钟的实际运行记录，但原 observer 的 WMI 查询故障造成 `455.085s` 记录缺口；续观察已完成，不能写作连续每分钟无缺口。
- CPU 性能和实际采样节奏风险仍保留：ProcessCollector 诊断曾在约 `380` 个进程上耗时 `3.127–4.792s`，且自动记录存在上述间隔缺口。
- 最终本地提交尚未运行 CI；现有三条 success workflow 只覆盖 baseline HEAD，不能覆盖修复后的新提交。
- 证据边界：本轮仅实际验证 150% 缩放；100% / 125% 未测，且没有 PID-to-session 专用 API 证明。这些不作为用户规定的必需条件。

后续复核步骤：

1. 在同一环境重新执行完整低开销观察。
2. 单独核对实际采样间隔并记录缺口。
3. 用户允许远端更新最终提交后，再运行新 HEAD 的 CI。

## 命令摘要

```powershell
.\.venv\Scripts\python.exe -m pytest -ra
.\.venv\Scripts\python.exe -m net_monitor.collectors.etw.probe
.\.venv\Scripts\python.exe -m net_monitor.collectors.etw.collector_probe
gh run list --repo Polarzen/net-monitor --commit d9752d3b85a131417029f12bc556fbe785bef986 --json workflowName,headSha,status,conclusion,url
logman query <本轮精确会话名> -ets
```

以上保留事项属于证据边界和后续复核，不引入新功能。
