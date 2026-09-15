# Net Monitor

Net Monitor 是一个面向 Windows 11 的第三方应用网络使用监视器，使用 Python 3.14、PySide6 和 psutil 构建；Windows 下的按进程网络流量通过 ETW + TDH + ctypes 获取。

产品目标不是复制任务管理器，而是优先回答：**哪些用户应用正在联网、哪个应用正在上传或下载、用了多少流量。** Windows OS 核心组件默认从主视图隐藏，但底层 ETW 仍保持完整采集。

## 版本状态

### v0.1.0

基础桌面网络监视器已经完成并以 `v0.1.0` 标记：

- 系统网络速度采样
- 当前运行进程枚举
- 基础 PySide6 GUI
- `Collector -> Service -> Model -> UI` 分层
- Windows CI / GUI smoke test

### v0.2 开发中

当前 `feat/etw-process-collector` 已完成 Stage 2A～2E 的核心工作：

- Windows ETW 按进程网络事件采集
- 真实 PID 级上传/下载 byte counters 与 B/s
- `(pid, create_time)` 处理 PID reuse
- ETW Session 生命周期、退出清理与权限感知降级
- `SYSTEM / APPLICATION / UNKNOWN` 保守分类
- 默认隐藏 Windows OS 系统进程，UNKNOWN 默认显示
- 后台 SamplingWorker，采集不再阻塞 Qt UI 主线程
- 完整进程枚举低频缓存，网络快照保持高频更新
- 第三方应用按 executable 路径进行保守聚合
- 顶层显示应用汇总，展开后查看各 PID 网络明细
- 默认只显示**当前有实时上传/下载速率**的应用，减少后台进程噪声
- 权限不足时提供显式“以管理员身份重启”按钮，由用户主动触发 UAC
- 网络排序使用原始数值，严格区分 `—` 与真实 `0 B/s`

> psutil 可以提供系统网络计数与进程信息，但不能直接、可靠地提供 Windows 下每个进程的实时收发字节数。本项目不会用连接数、随机数、系统总流量平均分配等方式伪造按进程流量。

## Stage 2D：第三方应用过滤与 GUI 性能

### 进程分类

展示层使用：

```text
SYSTEM
APPLICATION
UNKNOWN
```

分类采用保守隐藏策略：只有高置信度 Windows OS 组件才会隐藏。

主要规则：

- PID `0`、`4` -> `SYSTEM`
- executable 明确位于 `%SystemRoot%` / `%WINDIR%` -> `SYSTEM`
- executable 明确位于 Windows 目录之外 -> `APPLICATION`
- executable 无法读取时，仅对少量明确 Windows 核心进程名使用系统 fallback；其他 -> `UNKNOWN`
- `C:\Program Files\WindowsApps\...` 当前保守归为 `UNKNOWN`
- `C:\WindowsSomething\app.exe` 不会因字符串前缀误判为 Windows 目录
- executable 明确位于 Windows 目录之外时，路径证据优先于看起来像系统进程的名称

`UNKNOWN` 默认显示：宁可多显示一个无法确定归属的进程，也不错误隐藏真正联网的第三方程序。

Microsoft Edge、OneDrive、Visual Studio Code 等用户应用不会仅因为厂商是 Microsoft 就自动隐藏。

### 默认 GUI 行为

启动后默认：

```text
SYSTEM      隐藏
APPLICATION 显示
UNKNOWN     显示
当前联网筛选 开启
```

GUI 提供：

```text
☐ 显示 Windows 系统进程
☑ 仅显示当前联网应用
```

“仅显示当前联网应用”依据当前聚合后的上传/下载 B/s 判断，而不是“本次 Session 曾经产生过流量”。因此已经停止传输的应用会从默认视图退出，避免列表随运行时间不断膨胀；取消勾选后仍可查看全部可见应用。

实时网络筛选只有在 ETW 进程网络监控处于 `AVAILABLE` 时才有可靠依据。权限不足或采集不可用时，该筛选会暂时禁用，而不是把未知网络状态误判成“无流量”。

两个开关可以组合。打开系统进程开关只改变展示，不改变 ETW Provider 或底层聚合数据。

顶部汇总只统计非系统应用的真实网络速率，即使临时打开系统进程，也不会把 Windows 后台流量混入第三方应用总速率。

### GUI 性能重构

Stage 2D 前的主要卡顿路径是：Qt 主线程定时调用 `MonitorService.snapshot()`，同步运行 `psutil.process_iter()`，随后整表重建。窗口移动、缩放和绘制也依赖同一事件循环，因此会出现周期性停顿。

现在的线程关系：

```text
Microsoft-Windows-Kernel-Network
        ↓
ETW ProcessTrace thread
        ↓
NetworkAggregator

SamplingWorker / QThread
        ↓
MonitorService.snapshot()
        ↓
MonitorSnapshot
        ↓ Qt signal
Qt UI thread
        ↓
过滤、聚合、增量更新可见视图
```

默认 SamplingWorker 间隔约 `500 ms`；完整进程枚举默认约 `2 s` 刷新一次。Worker 不访问 QWidget，窗口关闭时会停止 worker、关闭 MonitorService 并清理 ETW Session。

## Stage 2E：应用级聚合视图

Stage 2E 将主视图从“一个 PID 一行”进一步调整为“一个应用一行，PID 可展开查看”。

例如多个 Chrome 进程：

```text
chrome.exe        8 个进程    4.2 MB/s    95 KB/s
├─ chrome.exe     PID 4120
├─ chrome.exe     PID 6844
├─ chrome.exe     PID 9180
└─ ...
```

### 聚合规则

当前聚合故意保持保守：

- executable 可读时，仅将**规范化后 executable 路径完全相同**的进程合并。
- Windows 路径比较大小写不敏感。
- 仅名称相同但 executable 路径不同的进程不会合并。
- executable 不可读的 UNKNOWN 进程不会仅凭名称互相合并，而是继续保持独立身份。
- 应用 key 基于规范化 executable 路径，因此同一程序某个子进程退出、另一个子进程出现时，顶层应用 identity 可以保持稳定。

当前不会根据 publisher、图标、产品名或“看起来属于同一厂商”做猜测式合并。

### 聚合网络数据语义

应用顶层网络数字来自当前成员 PID 的真实 `ProcessNetworkStats` 求和。

如果某个成员对应的网络数据不可获得，应用聚合值同样保持不可用 `—`，不会把缺失值当成 `0`。

因此：

```text
—      = 当前无法获得真实网络数据
0 B/s  = 采集正常，但当前确实没有流量
```

展开应用行后仍可以检查每个 PID 的下载/上传速度与累计字节，底层 PID 级 ETW accounting 没有被应用聚合替代。

### 增量树形更新

UI 当前使用 `QTreeWidget`：

- 顶层 item 对应应用 group key
- 子 item 使用 `(pid, create_time)` 作为进程 identity
- 应用仍存在时复用已有顶层 item
- 子进程出现/退出时只增删相应子 item
- 已展开应用在普通 snapshot 更新后保持展开状态
- 批量更新时暂停排序，完成后只恢复一次排序
- 数值列按 raw numeric role 排序，而不是按格式化字符串排序

Stage 2E 开发过程中曾发现 PySide6 `QTreeWidgetItem.__lt__` fallback 经 `super().__lt__()` 会重新进入 Python override，造成递归 stack overflow。当前实现已移除该递归路径，并由双平台 GUI smoke 测试覆盖。

## ETW 实现

Provider：

- `Microsoft-Windows-Kernel-Network`
- GUID `{7DD42A49-5329-4832-8DFD-43D979153A88}`
- IPv4 keyword `0x10`
- IPv6 keyword `0x20`
- level 4 / Informational

当前实现包括：

- `ctypes` 封装 ETW Session 与实时 Consumer
- TDH 按 schema 读取事件中的 `PID` 与 `size`
- manifest-backed TCP/UDP SEND / RECEIVE 方向映射
- 后台非 daemon 线程运行 `ProcessTrace`
- `NetworkAggregator` 线程安全累计 PID 级发送/接收字节
- 正式 `WindowsProcessNetworkCollector` 懒启动 ETW Session
- `(pid, create_time)` 身份基线，降低 PID 重用污染风险
- `retain_pids` 清理已退出进程的历史计数
- 正式 Collector 端到端 loopback probe

数据链路：

```text
Microsoft-Windows-Kernel-Network
        ↓
EtwSession / TDH
        ↓
NetworkEvent
        ↓
NetworkAggregator
        ↓
WindowsProcessNetworkCollector
        ↓
MonitorService / MonitorSnapshot
        ↓
ProcessClassifier
        ↓
Application aggregation
        ↓
PySide6 application tree
```

UI 不直接访问 ETW API 或 psutil 采集逻辑。

## 采集状态与权限

进程网络采集状态：

```text
STARTING
AVAILABLE
PERMISSION_DENIED
UNAVAILABLE
STOPPED
```

GUI 对应显示：

```text
进程网络监控：正在启动
进程网络监控：运行中
进程网络监控：不可用（需要管理员权限）
进程网络监控：不可用
进程网络监控：已停止
```

在当前已测试 Windows 环境中，普通用户启动 ETW Session 会得到 `StartTraceW` error 5。权限不足时应用/进程结构仍可显示，但上传/下载字段保持 `—`，绝不会伪造数据。

当状态为 `PERMISSION_DENIED` 时，GUI 会显示“以管理员身份重启”按钮。只有用户点击该按钮后，程序才通过 Windows `ShellExecuteW(..., "runas", ...)` 请求 UAC 提权；成功启动管理员实例后，旧窗口关闭。程序不会在后台自动提权。

## 自动验证

除必须在 Windows 11 x64 物理桌面完成的真实交互体验外，项目验证尽量放入 GitHub Actions。

### Full CI

主 CI 在以下两个环境运行完整测试套件：

```text
Windows Server 2025 x64
Windows 11 Enterprise ARM64
Python 3.14
PySide6 offscreen
```

Stage 2E 当前完整套件为 `56` 项，覆盖：

- ETW event/session/collector 单元测试
- SYSTEM / APPLICATION / UNKNOWN 分类
- 应用 executable-path 聚合
- unavailable 值传播
- 应用 group identity 稳定性
- 应用树展开与 PID 子项
- 默认当前联网应用过滤及切换为全部应用
- 权限不足时的管理员重启 UI 路径
- 系统过滤组合
- raw numeric sorting
- 增量 item 复用
- 大量 fake application snapshot
- SamplingWorker 非 UI 线程采样与关闭生命周期
- PID reuse / inactive PID cleanup

### ETW Experiment

ETW Experiment 同样在 Windows 11 ARM64 和 Windows Server 2025 x64 上执行：

- ETW / Collector 专项单元测试
- 底层真实 loopback probe 连续两次
- 正式 `WindowsProcessNetworkCollector` probe 连续两次
- 同一 Session 名的 restart / cleanup
- 标准本地用户权限表征

Stage 2E 的 application aggregation / GUI / worker 相关文件也已纳入 ETW workflow 的触发路径，因此以后修改应用视图时会自动重新验证真实 ETW 数据链路。

## 已知限制

- GitHub 托管 Windows 11 环境为 ARM64，不等同于 Windows 11 x64 物理桌面机。
- Windows 11 x64 物理机上的窗口拖动、缩放、滚动、长期运行手感仍属于重要实机验收项，不能由 offscreen Actions 替代。
- 系统进程分类采用 conservative rules；`UNKNOWN` 默认显示，取消“仅显示当前联网应用”后仍可能看到少量无法确定归属的系统/受保护进程。
- WindowsApps 当前保守归为 `UNKNOWN`，尚未实现 package identity / publisher 级分类。
- 应用聚合当前只认相同 executable 路径，不尝试跨 executable 合并同一产品的 helper / updater / launcher。
- 当前应用累计量是**当前活跃成员 PID 计数的聚合**。子进程退出后，其已退出 PID 不会作为永久应用历史保留；真正的“本次 Session 应用历史总流量”需要后续持久化/会话归因层。
- 当前已测试环境中，标准本地用户启动 ETW Session 会收到 `StartTraceW` error 5；不同机器策略可能不同。
- ETW Provider byte counters 表示所捕获网络事件中的字节计数，项目不会未经证据把它描述为应用层 payload 的绝对精确字节数。

## 环境与本地启动

- Windows 11（主要目标环境）
- Python 3.14
- PySide6
- psutil

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m net_monitor
```

普通自动化测试主要由 GitHub Actions 完成；本地主要用于 Windows 11 x64 物理桌面交互和长期运行验收。

## ETW 诊断入口

```powershell
logman query providers "Microsoft-Windows-Kernel-Network"
python -m net_monitor.collectors.etw
python -m net_monitor.collectors.etw.probe
python -m net_monitor.collectors.etw.collector_probe
```

## 架构

```text
Collector -> Service -> Model -> UI
```

当前运行线程关系：

```text
ETW ProcessTrace thread
        ↓
NetworkAggregator

SamplingWorker QThread
        ↓
MonitorService
        ↓
MonitorSnapshot
        ↓
Qt UI thread
        ↓
Process classification
        ↓
Application aggregation
        ↓
Incremental application tree
```
