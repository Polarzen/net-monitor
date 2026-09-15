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

当前 `feat/etw-process-collector` 已完成 Stage 2A、2B、2C 和 2D 的核心工作：

- Windows ETW 按进程网络事件采集
- 真实 PID 级上传/下载 byte counters
- 按真实采样时间计算上传/下载 B/s
- `(pid, create_time)` 处理 PID reuse
- 已退出 PID 的聚合数据清理
- ETW Session 生命周期与退出清理
- 权限感知降级，不伪造数据
- GUI 显示进程网络采集状态
- `SYSTEM / APPLICATION / UNKNOWN` 进程分类
- 默认隐藏 Windows OS 系统进程，UNKNOWN 默认显示
- 可通过“显示 Windows 系统进程”查看全部进程
- 顶部汇总只计算非系统应用的真实 ETW 网络速率
- `仅显示有网络活动的进程` 与系统进程开关可组合
- 网络速率/累计量按原始数值排序
- 明确区分 `—`（不可用）与 `0 B/s`（采集正常但当前无流量）
- MonitorService 采样移出 Qt UI 主线程
- 进程完整枚举降为低频缓存，网络快照保持高频更新
- 表格按 `(pid, create_time)` 增量增删和更新，不再每个采样周期整表重建
- 排序在批量数据更新期间暂停，避免每个单元格更新触发排序风暴

> psutil 可以提供系统网络计数与进程信息，但不能直接、可靠地提供 Windows 下每个进程的实时收发字节数。本项目不会用连接数、随机数、系统总流量平均分配等方式伪造按进程流量。

## Stage 2D：第三方应用视图

### 进程分类

展示层使用明确分类：

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
- `C:\Program Files\WindowsApps\...` 不会因为目录名而整体判定为系统，当前保守归为 `UNKNOWN`
- `C:\WindowsSomething\app.exe` 不会因字符串前缀误判为 Windows 目录
- 即使进程名看起来像系统进程，只要 executable 明确位于 Windows 目录之外，也优先视为 `APPLICATION`

`UNKNOWN` 默认显示。该设计宁可多显示一个无法分类的进程，也不把真正联网的第三方程序错误隐藏。

Microsoft Edge、OneDrive、Visual Studio Code 等用户应用不会因为厂商是 Microsoft 就自动隐藏；分类关注它是否属于 Windows OS 系统目录，而不是 publisher。

### 默认 GUI 行为

启动后默认：

```text
SYSTEM      隐藏
APPLICATION 显示
UNKNOWN     显示
```

GUI 提供：

```text
☐ 显示 Windows 系统进程
☐ 仅显示有网络活动的进程
```

两个开关可以组合。打开系统进程开关只改变展示，不改变 ETW Provider 或底层聚合数据。

顶部显示：

```text
第三方应用总上传速度
第三方应用总下载速度
当前显示进程数
```

第三方应用汇总始终排除 `SYSTEM`，即使用户临时打开系统进程视图也不会把 Windows 后台流量混入第三方应用总速率。

## Stage 2D：GUI 性能重构

### 原始卡顿路径

Stage 2D 开始前，Qt 主线程中的 `QTimer` 每秒直接执行：

```text
QTimer / UI thread
    ↓
MonitorService.snapshot()
    ↓
psutil.process_iter(...)
    ↓
系统网络 + 按进程网络处理
    ↓
setRowCount(...)
    ↓
重新创建整张表全部 QTableWidgetItem
```

窗口拖动、缩放和绘制同样依赖 Qt 主线程，因此同步进程枚举与整表重建会周期性抢占事件循环，造成真实 Windows 桌面环境下的拖动卡顿。

### 新线程模型

现在改为：

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
immutable MonitorSnapshot
        ↓ Qt signal
Qt UI thread
        ↓
增量更新可见表格
```

职责边界：

- ETW consumer thread：持续消费真实网络事件。
- SamplingWorker QThread：执行 `MonitorService.snapshot()`，包括 psutil 进程枚举和网络快照组织，不访问 QWidget。
- Qt UI thread：只消费已经准备好的 snapshot、执行过滤和必要的可见表格更新。

默认 SamplingWorker 间隔约 `500 ms`；完整进程枚举默认约 `2 s` 刷新一次，中间网络 snapshot 复用进程列表。这样网络速率仍能较快更新，而 `psutil.process_iter()` 不再每次网络刷新都扫描全部进程。

### 增量表格更新

表格现在用 `(pid, create_time)` 作为行身份：

- 新进程 -> 插入新行
- 已退出进程 -> 删除对应行
- 仍存在进程 -> 复用已有 `QTableWidgetItem`，只更新变化的值
- 数据不变 -> 避免无意义地创建整套新 Item

批量更新时临时关闭排序，全部数据写入后再恢复一次排序，避免单元格更新期间反复重排。

当前仍使用 `QTableWidget`，因为增量更新已经能消除原先最明显的全表重建问题；暂未为架构形式强行迁移到 `QAbstractTableModel`。

### 开发级性能观测

当前保留轻量性能数据，不默认刷屏输出：

- `MonitorService.last_performance.total_seconds`
- `MonitorService.last_performance.process_enumeration_seconds`
- `MonitorService.last_performance.process_count`
- `MainWindow.last_apply_seconds`
- `MainWindow.last_visible_rows`

这些数据用于后续 Windows 11 x64 实机性能验收，而不是 CI 中设置脆弱的毫秒级阈值。

## ETW 实现

使用 Provider：

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
- 窗口/worker/application 退出时关闭 MonitorService 和 ETW Session
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
ProcessClassifier / UI filtering
        ↓
PySide6 UI
```

UI 不直接访问 ETW API 或 psutil 采集逻辑。

## 采集状态与权限

进程网络采集使用明确状态模型：

```text
STARTING
AVAILABLE
PERMISSION_DENIED
UNAVAILABLE
STOPPED
```

主要语义：

- `STARTING`：Collector 尚未完成首次 ETW 启动尝试。
- `AVAILABLE`：ETW Session 已成功启动，可提供真实按进程数据。
- `PERMISSION_DENIED`：实际启动 ETW 时收到权限错误，例如 `StartTraceW` error 5。
- `UNAVAILABLE`：非权限类 ETW 初始化/运行错误或采集器不可用。
- `STOPPED`：Collector 已关闭。

GUI 对应显示：

```text
进程网络监控：正在启动
进程网络监控：运行中
进程网络监控：不可用（需要管理员权限）
进程网络监控：不可用
进程网络监控：已停止
```

权限不足不会让应用退出；应用列表和分类仍可显示，但按进程网络字段与第三方应用总速率显示 `—`，而不是伪造为 `0 B/s`。

当 ETW 正常运行但进程当前没有流量时，速度显示真实的 `0 B/s`；累计值保持实际计数。

“仅显示有网络活动的进程”按本次 Collector Session 中累计上传或下载字节是否大于 0 判断，因此短暂停顿不会让已产生流量的进程立即从列表消失。

## Stage 2D 验证

### 主 CI

2026-09-15 Stage 2D 最终代码在 Windows Server 2025 x64、Python 3.14.7 上通过：

```text
49 passed
```

覆盖包括：

- SYSTEM / APPLICATION / UNKNOWN 分类
- WindowsApps 保守分类
- Windows 路径边界与大小写
- executable 不可读时 UNKNOWN 默认显示
- 系统进程默认隐藏 / 手动显示
- 系统过滤与网络活动过滤组合
- `—` 与 `0 B/s`
- 网络数字排序
- 300 行 fake snapshot
- 增量更新复用现有表格 Item
- 进程枚举低频缓存
- snapshot 确实运行在非 UI worker thread
- worker / service / window shutdown 生命周期
- PID reuse 和 inactive PID cleanup

同时验证：PySide6、psutil、ETW module import、`.venv` ignore 和 repository clean。

### Windows 11 ARM64 ETW Experiment

最终 Stage 2D 回归运行环境：

- Microsoft Windows 11 Enterprise
- OS `10.0.26200`
- ARM64
- Python `3.14.7` ARM64

结果：

- ETW / Collector 单元测试：`25 passed`
- 底层真实 loopback probe 使用同一 Session 名连续两次：通过
- 正式 `WindowsProcessNetworkCollector` probe 使用同一 Session 名连续两次：通过
- 标准本地用户权限表征：通过，`StartTraceW` 仍返回 error `5`
- repository status：clean

正式 Collector 两次结果：

```text
run 1:
upload_bytes:               524288
download_bytes:             524288
upload_bytes_per_second:    2095313.15
download_bytes_per_second:  2095313.15
collector_available:        true
collector_closed:           true

run 2:
upload_bytes:               524288
download_bytes:             524288
upload_bytes_per_second:    2096003.39
download_bytes_per_second:  2096003.39
collector_available:        true
collector_closed:           true
```

### Windows Server 2025 x64 ETW Experiment

最终 Stage 2D 回归运行环境：

- Microsoft Windows Server 2025 Datacenter
- OS `10.0.26100`
- x64
- Python `3.14.7` x64

结果：

- ETW / Collector 单元测试：`25 passed`
- 底层真实 loopback 双次捕获：通过
- 正式 Collector 双次捕获：通过
- Session cleanup / restart：通过
- 标准用户权限表征：通过，`StartTraceW` error `5`

正式 Collector 两次均得到 `524288` upload bytes 和 `524288` download bytes，且 `collector_available = true`、close 后 `collector_closed = true`。

## 已知限制

- GitHub 托管 Windows 11 实验环境仍是 ARM64，不是 Windows 11 x64 物理桌面机。
- Stage 2D 已从代码层移除同步 UI-thread 采集与整表重建，但 Windows 11 x64 物理机上的实际拖动、缩放、滚动流畅度仍需用户更新代码后重新验收，README 不提前宣称实机性能已经通过。
- 系统进程分类采用 conservative rules；`UNKNOWN` 会默认显示，因此可能看到少量无法确定归属的系统/受保护进程，这是为了避免误隐藏真正的第三方应用。
- WindowsApps 当前保守归为 `UNKNOWN`，尚未实现 packaged-app publisher / package identity 级分类。
- 当前仍以进程为行，不做 Chrome、Edge、Electron 等多进程应用聚合。
- 当前已测试环境中，标准本地用户启动该 ETW Session 会收到 error 5；不同机器上的安全策略可能不同。
- ETW Provider 的 byte counters 表示所捕获网络事件中的字节计数；项目不会未经证据把它宣称为“应用层有效载荷的绝对精确字节数”。

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
python -m pytest
python -m net_monitor
```

在当前已测试环境中，需要具备 ETW Session 权限才能看到真实每进程上传/下载数据。权限不足时应用列表、分类与过滤仍可使用，但网络数字保持不可用状态。

## ETW 诊断入口

确认 Provider：

```powershell
logman query providers "Microsoft-Windows-Kernel-Network"
```

交互式 ETW PoC：

```powershell
python -m net_monitor.collectors.etw
```

底层受控 loopback 验证：

```powershell
python -m net_monitor.collectors.etw.probe
```

正式 Collector 端到端验证：

```powershell
python -m net_monitor.collectors.etw.collector_probe
```

## 架构

```text
Collector -> Service -> Model -> UI
```

Stage 2D 后的运行线程关系：

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
```

## CI

主 CI 在 Windows Server 2025 x64 上使用 Python 3.14 创建独立 `.venv`，执行安装、导入、psutil、PySide6、ETW module、GUI tests 与完整 pytest。

独立 `ETW Experiment` workflow 在 `windows-2025` 与 `windows-11-arm` 上执行：

```text
Provider 查询
ETW / Collector 单元测试
底层 ETW 真实 loopback 双次捕获
正式 WindowsProcessNetworkCollector 双次端到端捕获
同名 Session cleanup / restart
标准本地用户权限表征
```

ETW Experiment 的路径触发范围包括 ETW Collector、核心状态/分类和 MonitorService 变化，确保服务层重构后重新验证真实 ETW 数据链路。
