# Stage 3A 本轮验收记录（2026-09-16）

状态：**正式 GUI 观察已完成并正常退出；核心本地测试、真实 ETW、窗口行为和资源释放均有证据。point 28 有一次按精确会话名执行的 `logman` 查询 warning，原始错误已保留，不能称作 logman 全部通过。Stage 3A 精确提交 `ee156d725f4a2ea2d1ee7255070d91d8b54ad1d6` 的双平台 CI 与 ETW 已成功；Stage 3B 当前只是本地未提交集成，未来 CI/ETW 尚未运行。**

## 环境与基线

Windows 11 家庭中文版 `10.0.26200`（build 26200），Python `3.14.7`，net-monitor `0.2.0`，PySide6 `6.11.2`，psutil `7.2.2`，pytest `9.1.1`。Stage 3A 的精确验证提交为 `ee156d725f4a2ea2d1ee7255070d91d8b54ad1d6`，其代码父提交为 `95232da817281de6e615f3eea42c09fbae063572`；当前 Stage 3B 集成以 B HEAD `962a3a04e4bdd21d309106c017a5fd96ad7b9d98` 和 A `ee156d725f4a2ea2d1ee7255070d91d8b54ad1d6` 为已知输入，最终合并 SHA 尚不存在。本会话 shell 非管理员，真实 probe/GUI 由 RunAs/UAC 管理员子进程执行。

本次 Stage 3A 续修涉及 `src/net_monitor/collectors/process.py`、`src/net_monitor/collectors/windows_network.py`、`src/net_monitor/ui/controller.py`，以及对应测试和文档。未新增依赖。GUI `ProcessInfo.status=None` 和约 2 秒进程速率是用户接受的限定变化，不声称所有 Python 可观察值均不变。Stage 3B 的累计与退休交接语义另记于集成记录。

## 修复与公开语义

- 默认 `ProcessCollector`/`MonitorService` 继续请求并保留 `status`，默认 `WindowsProcessNetworkCollector` 的 `rate_window_seconds=0.0` 保留旧速率行为。
- GUI 自建 collector 不请求进程 `status`，并使用 `rate_window_seconds=2.0`。窗口以不晚于 `now-2s` 的最近样本为基线，按真实 elapsed 计算；启动不足窗口时使用首样本。累计 bytes、PID/`create_time` 身份、约 500 ms UI 采样和 2 秒进程刷新保持不变。
- 计数器回退只清窗口速率历史并保留累计基线；时钟回退重新锚定当前样本。此前系统计数器读取和速率时间戳顺序修复也保留，相关 service 回归曾验证旧值 `33.333/66.667` 修正为 `100/200`。

## 自动验证与 CI

Stage 3A 精确提交 `ee156d725f4a2ea2d1ee7255070d91d8b54ad1d6` 的 CI 运行 [#35118756782](https://github.com/Polarzen/net-monitor/actions/runs/35118756782) 为 `100 passed`、`0 failed`、`1 skipped`（runner 无真实系统托盘）；ETW 运行 [#35118757413](https://github.com/Polarzen/net-monitor/actions/runs/35118757413) 为 `45 passed`、`0 failed`，raw loopback ×2 与 production collector ×2 均完成，身份双向 `512 KiB` 闭合通过，standard-user permission error `5` 通过。Stage 3B 集成后的本地全量 pytest 结果见集成记录，未来 CI/ETW 尚未运行。

历史 baseline `d9752d3b85a131417029f12bc556fbe785bef986` 的 workflow 结果为 success：[CI #34979881270](https://github.com/Polarzen/net-monitor/actions/runs/34979881270)、[ETW Experiment #34973522989](https://github.com/Polarzen/net-monitor/actions/runs/34973522989)、[CI #34973522976](https://github.com/Polarzen/net-monitor/actions/runs/34973522976)。`gh` 查询 `fe5bb35103cb749a5e906b3f8a55aa37d321b435` 成功并返回空列表 `[]`；这些历史 success 不覆盖已发布 HEAD。

此前 `95232da817281de6e615f3eea42c09fbae063572` 的远端运行 [CI #35111080385](https://github.com/Polarzen/net-monitor/actions/runs/35111080385) 与 [ETW #35111080247](https://github.com/Polarzen/net-monitor/actions/runs/35111080247) 仍作为历史证据保留：两个平台的 production collector probe 当时以 exit code `1` 结束，日志 API 返回 `403` 且无 traceback，不能据此断言唯一运行异常。随后 A 精确提交已完成上面的成功双平台验证。

## 管理员 ETW 与 collector probe

历史记录：当时补齐 `psutil` 的普通 push 曾被 GitHub 以 token 缺少更新 workflow 所需的 `workflow` scope 拒绝；该权限阻塞不代表当前 A 精确验证结果。当前 Stage 3B 仅在本地未提交集成，未来 CI/ETW 由集成后的最终提交单独运行。

本轮 raw probe 两次、collector probe 两次均退出码 `0`，每次双向各 `524288` bytes。raw probe 证明 `pid_matched`；collector probe 另外确认完整的 name/exe/`create_time` identity，退出后四次精确 session 查询均为 `4201`。这些是 A 精确提交验证；Stage 3B 本地合并尚未启动真实 probe。

停流后，collector probe 的上传/下载 idle 严格归零恢复窗口分别为 `2.254364s`、`2.253547s`，`totals_stable` 和 `closed` 均为真。A 的 CI/ETW 日志没有直接 `loss` 字段；旧本地正式观察 point 28 的 `logman` 返回码为 `2147946600`（`0x80071068`），同点另行执行的 direct numeric QUERY status 为 `0` 且 loss 为 `0`，warning 和原始 stdout/stderr 均保留。

## 正式 GUI 观察

正式观察时间为 `2026-09-16 20:49:57–21:19:58+08`，持续 `1800.0012464s`，31 点 `0..30` 连续完成。31/31 点 numeric QUERY 为 `0`，`EventsLost=0`、`RealTimeBuffersLost=0`，snapshot 均 `AVAILABLE`，Responding 均为 true，fatal errors 为 `0`；唯一 warning 是上述 point 28 的 logman 查询失败。

CPU 单逻辑核为 min `3.3593%`、max `11.1459%`、mean `5.8029%`；按 32 个逻辑核折算整机 mean `0.1813%`。working set 首/末为 `91.31/48.58 MiB`，全程范围 `26.13–106.48 MiB`；private bytes 首/末为 `42.12/51.87 MiB`，范围 `42.12–52.05 MiB`，净变化 `+9.75 MiB`，期间 8 次下降、10 次上升，非单调，不据此承诺不存在长期泄漏。

完整 GUI 诊断日志共 `4300` 个 snapshot，包含正式观察后等待用户退出的阶段；`snapshot 1..4300`、`event 1..4305` 无 gap，`monitor_service_init/session_init` 次数为 `1/1`。全 GUI 日志的 snapshot cadence p50/p95/max 为 `0.498965/0.509387/0.518918s`，单次 service total p50/p95/max 为 `0.0241458/0.0310339/0.0861856s`，process enumeration p50/p95/max 为 `0.0039851/0.0053697/0.0329672s`；这些统计包含退出等待阶段，不等同于正式 31 点窗口。

ETW 双向零速率只出现在启动期 `seq1–5`，`seq6` 后未再出现。用户在启动、约 15 分钟和结束时确认窗口、数据更新和托盘行为正常，无规律性零速率复现。`app_returned` 于 `21:25:46+08` 返回 code `0` 且 `log_failed=false`；observer 于 `21:25:48` 核查 child return code `0`、已知 GUI PIDs `49188/48608/25656` 全部 gone、`unknown=[]`，精确 GUI session `NetMonitor-ProcessNetwork-PoC-be54de08-9a1d-453f-b918-05709b755b3b` 查询为 `4201`。

## 桌面与历史证据边界

- 用户实机确认启动、约 15 分钟和结束状态下窗口、数据和托盘正常；此前还确认非管理员权限提示、UAC 接受与取消、Detailed 单实例、托盘隐藏恢复和管理员 150% DPI 下无明显裁切。无控制台链路为 `net-monitor.exe` → `pythonw.exe`。
- 100% / 125% DPI 未测；本轮已测 150%。桌面自动化 native pipe 不可用，相关结论来自用户实机确认，不用 mock 代替。
- 19:34 旧观察在第 12 分钟因 logman 中止了资源记录，GUI 实际运行约 29m52；20:14 旧诊断约 5m59，曾观察到 `344/716` 个 snapshot 的 system positive 与 ETW zero 分层现象。旧 40m39 记录另有 `455.085s` 缺口，均只作为历史工具失败记录，不作为本轮正式 soak 结论；相关旧实例已正常退出并查询 `4201`。
- 非管理员 permission probe 曾返回 code `5`；这是权限前置条件失败，不是管理员 ETW 或本轮应用失败。

三轮观察涉及的 GUI、probe、observer 进程均已不存在，9 个精确 ETW session 查询均为 `4201`。TEMP 诊断包装调用原 `app.main` 记录标量，按分钟记录资源并执行 direct QUERY；这些操作有少量未单独量化的观察开销，指标不是零扰动基准，也未捕获流量内容。临时目录尚未删除：PowerShell 删除命令执行前被工具策略以 `CreateProcess ... rejected: blocked by policy` 拒绝，未执行也未重试绕过。待人工清理的本地目录名称为 `net-monitor-stage3a-final-ad5ad7118cff4db28ceb72a950e36e98`（50 files，1,710,258 bytes）、`net-monitor-stage3a-rate-002d4ef7b0fa494cb1fd01bb5e86e617`（28 files，541,987 bytes）、`net-monitor-stage3a-window-f7fac68b3904407f87d35df896f4bfcc`（79 files，3,292,172 bytes）；绝对路径仅保留在本地交付记录中。除当前新 HEAD CI 外，本记录未引入新的功能待办。

## 命令摘要

```powershell
.\.venv\Scripts\python.exe -m pytest -ra
.\.venv\Scripts\python.exe -m net_monitor.collectors.etw.probe
.\.venv\Scripts\python.exe -m net_monitor.collectors.etw.collector_probe
.\.venv\Scripts\python.exe -c "import functools; import net_monitor.collectors.etw.collector_probe as p; p.WindowsProcessNetworkCollector=functools.partial(p.WindowsProcessNetworkCollector,rate_window_seconds=2.0); raise SystemExit(p.main())"
gh run list --repo Polarzen/net-monitor --commit d9752d3b85a131417029f12bc556fbe785bef986 --json workflowName,headSha,status,conclusion,url
logman query <本轮精确会话名> -ets
```
