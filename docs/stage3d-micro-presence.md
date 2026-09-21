# Stage 3D：Micro Presence

## 范围与基线

Stage 3D 从 Stage 3C 精确基线 `4440fe41ce695c67a81f01b4477ff7ae15dee527` 增量升级，目标分支为 `feat/stage-3d-micro-presence`。本记录冻结 Micro Presence 的显示、身份和成本边界；最终实现、测试、CI/ETW run 和 Windows 11 物理桌面结果以目标分支最终 SHA 的交付报告为准。

Stage 3D 保留 Stage 3C 的全部既有能力：Windows ETW 按进程采集、`Microsoft-Windows-Kernel-Network`、TDH/`ctypes`、PID + `create_time` 身份保护、application → PID 聚合、Application Session 累计、MicroWindow、ApplicationCard、Compact/Detailed、固定关注、自动主导应用选择及防抖、Top 3、图标缓存、窗口位置、系统托盘和 Detailed 本次监控累计页。Micro Presence 只增加 UI 状态投影，不重写采集内核或应用聚合。

## 架构

运行时继续只有一条采集链：

```text
ETW Session
    ↓
MonitorService
    ↓
SamplingWorker (约 500 ms)
    ↓
UiController / MonitorSnapshot
    ├── MicroProjection → MicroWindow / ApplicationCard
    ├── CompactWindow
    └── DetailWindow
```

进程网络采集、ETW parser/session、`MonitorService`、`SamplingWorker` 和现有 application aggregation 不因 Presence 增加第二份实例。Presence 相关逻辑属于 UI 边界，优先位于 `ui/windows_foreground.py`、`ui/micro_model.py` 和现有 controller/window 层。

`MicroProjection` 继续直接消费已有的 `_groups`、selected application key 和快照，不在 heartbeat 中再次调用 application aggregation。只读的 `presence_context()` 从 selected application group 提供 selected key、可信 member PID 集合和 `identity_complete`。`UiController` 是唯一控制中心；可以持有一个可依赖注入的 foreground reader，但它不是线程、timer、service 或 collector。

## MicroWindow

窗口使用 Qt logical pixels，固定默认和最大尺寸为 **220×112**（满足不超过 240×140 的阶段上限）。DPI 由 Qt 和系统负责，代码不手动乘 DPI 倍数。窗口仍为 frameless Tool Window，支持拖动、右键菜单、置顶、点击打开 ApplicationCard，并且不主动抢焦点。

Micro Presence 只显示一个当前对象：图标、可省略的应用名、前台/后台/状态未知 badge、下载速率、上传速率和当前状态行。数字刷新不能改变窗口尺寸；完整应用名继续通过 Tooltip 提供。它不显示 Top 3/Top 5、PID、路径、累计流量表、CPU、内存、连接列表或历史图表。

有可信正速率时，自动模式显示当前主导应用。没有默认可见应用产生可信正速率时显示 quiet state，例如“Net Monitor / 当前安静 / 暂无明显网络活动”，不使用 0 B/s 应用伪造主导对象。固定关注时继续显示关注应用及其当前速率；无流量时明确显示“当前无流量”，不因 idle 自动切换。

网络速率和 Presence 状态相互独立。因此“Chrome / 前台 / 当前无流量”和“Chrome / 后台 / 下载 3 MiB/s”都是合法状态。ETW permission denied、unavailable、failed 或 stale 时，Presence 仍不能被解释成网络正常；网络源状态继续使用现有 `—`、过期或具体错误语义。

## Presence 状态定义

公开状态只有：

```text
FOREGROUND  → 前台
BACKGROUND  → 后台
UNKNOWN     → 状态未知
```

foreground reader 每次只获取当前 foreground HWND 和对应 PID。严格判定规则如下：

* `FOREGROUND`：查询成功，foreground PID 非零，并且匹配当前 snapshot 中任意 `create_time != None` 的可信 member PID。
* `BACKGROUND`：查询成功，foreground PID 非零，当前 application 的成员身份完整可信，且没有 member PID 匹配 foreground PID。
* `UNKNOWN`：查询失败、PID 为 0、没有 selected application、无法可靠关联，或存在身份不完整 member 且没有可信匹配。

如果一个 application 同时有可信 member 和 `create_time is None` 的不完整 member，只要 foreground PID 匹配可信 member，仍可判定 `FOREGROUND`；如果没有可信匹配，则只能是 `UNKNOWN`，不能判定 `BACKGROUND`。foreground API 只返回 PID，不能替换既有 `(pid, create_time)` 身份模型，也不能单凭 PID 绕过 PID reuse 保护。

## Win32 边界与轮询成本

Windows 边界通过 `ctypes` 调用：

```text
GetForegroundWindow
GetWindowThreadProcessId
```

查询只使用现有 `UiController._heartbeat` → `_refresh_views()` 路径，不在 `frame()` 内调用。每个 UI tick 最多一次 foreground PID 查询；当 MicroWindow 和 ApplicationCard 都不可见且当前为 Compact 时，可以跳过查询。不得新增 `psutil.process_iter()`、进程 metadata 扫描、按应用 Win32 查询、线程、timer、service、collector 或后台任务。

因此本阶段的预期新增数量为：

```text
threads: 0
timers: 0
collectors: 0
```

foreground reader 支持 dependency injection，使纯逻辑测试不依赖真实桌面窗口。采集频率、Application Session、自动选择、challenger 防抖、follow 状态和 upload/download rate 均保持 Stage 3C 语义。

## 测试与验证边界

确定性 Presence 测试应至少覆盖：可信 PID 匹配得到 `FOREGROUND`；查询成功且完整可信成员均不匹配得到 `BACKGROUND`；`create_time is None`、查询错误、PID 0、无 selected application 和不完整身份无可信匹配得到 `UNKNOWN`；可信匹配与不完整第二成员并存时仍得到 `FOREGROUND`。

UI/架构测试应覆盖 220×112 默认和最大逻辑尺寸、240×140 阶段上限、长名称 elide 与 Tooltip、前台/后台/未知文本、quiet state、固定关注 idle、上下行速率刷新、刷新不改尺寸、每 heartbeat 至多一次查询，以及切换 Micro/Compact/Detailed/Card 不创建第二条采集链。100%/125%/150% 的 CI fake snapshot 布局证据只用于自动布局回归。

本轮本地验证：Python 3.14 项目虚拟环境的 `compileall src` 通过；完整 pytest 为 **242 passed, 1 skipped**，跳过原因为测试运行环境没有真实系统托盘，未新增 skip/xfail。针对性测试为 **53 passed**。使用锁定字体的 100% / 125% / 150% fake snapshot 渲染均通过，窗口保持 220×112 logical pixels；另人工检查了 100%/150% 活跃态和 125% quiet 布局图。采集内核、core、collectors、services 和 SamplingWorker 相对 Stage 3C 基线无修改。

物理桌面上，用户已确认微型窗可见，并观察到“后台”和“状态未知”；同时报告浏览器获得焦点且有正常速率时仍未显示“前台”。随后定位并修复了每次快照清空 Presence 缓存的问题：相同成员身份的快照保留结果，application key 或 `(pid, create_time)` 变化则失效，直接读取 frame 也检查身份上下文。新增回归测试已包含在上述结果中。该修复的真实浏览器前台→后台→前台复测仍待确认，不能将确定性测试记作物理通过。

Windows 11 物理验收还需确认三档系统 DPI、拖动/点击、卡片、Compact、Detailed、托盘和关闭/退出行为；CI 不能替代这些桌面观察。当前分支的 CI / ETW 结果以推送后精确提交对应的 Actions run 为准。

## CI 与 ETW

`feat/stage-3d-micro-presence` 纳入 CI 的 Stage 3C frozen-kernel branch check，并纳入 ETW Experiment 的 push branch filter。两个 workflow 继续使用 Windows Server 2025 x64 与 Windows 11 Enterprise ARM64，保留 Python 3.14、完整测试、ETW provider/unit/live probe、同 session 重启清理和标准用户权限验证。Stage 3D 不降低 workflow 权限，不使用 `continue-on-error`，也不删除平台或既有测试要求。

## 已知限制与后续范围

foreground 结果只基于当前 foreground HWND/PID 与当前可信 snapshot 的 member PID 比较；API 失败、PID 为 0 或身份不完整时保守显示 `UNKNOWN`。当前记录不提供历史速率、sparkline、SQLite、通知、域名解析、远端 IP 地理位置、防火墙、限速、WFP、WinDivert、Npcap、驱动、开机启动、installer、自动更新或云同步。速率历史属于后续阶段。
