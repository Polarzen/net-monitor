# Net Monitor

Net Monitor 是一个面向 Windows 11 的桌面网络监控工具，使用 Python 3.14、PySide6 和 psutil 构建；Windows 下的按进程网络流量通过 ETW + TDH + ctypes 获取。

## 版本状态

### v0.1.0

基础桌面网络监视器已经完成并以 `v0.1.0` 标记：

- 系统总上传/下载速度
- 当前运行进程枚举
- 基础 PySide6 GUI
- `Collector -> Service -> Model -> UI` 分层
- Windows CI / GUI smoke test

### v0.2 开发中

当前 `feat/etw-process-collector` 已完成 Stage 2A、2B、2C 的核心工作：

- Windows ETW 按进程网络事件采集
- 真实 PID 级上传/下载 byte counters
- 按真实采样时间计算上传/下载 B/s
- `(pid, create_time)` 处理 PID reuse
- 已退出 PID 的聚合数据清理
- ETW Session 生命周期与退出清理
- 权限感知降级，不伪造数据
- GUI 显示进程网络采集状态
- `仅显示有网络活动的进程` 筛选
- 网络速率/累计量按原始数值排序
- 明确区分 `—`（不可用）与 `0 B/s`（采集正常但当前无流量）

> psutil 可以提供系统网络计数与进程信息，但不能直接、可靠地提供 Windows 下每个进程的实时收发字节数。本项目不会用连接数、随机数、系统总流量平均分配等方式伪造按进程流量。

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
- `MonitorService.close()`、窗口关闭和应用退出时停止 ETW Session
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
PySide6 UI
```

UI 不直接访问 ETW API 或 psutil 网络采集逻辑。

## Stage 2C：采集状态与 GUI

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

权限不足不会让应用退出：系统总网络速度、进程列表等功能仍可继续使用。按进程网络字段显示 `—`，而不是伪造为 `0 B/s`。

当 ETW 正常运行但进程当前没有流量时，速度显示真实的 `0 B/s`；累计值保持实际计数。

“仅显示有网络活动的进程”按本次 Collector Session 中累计上传或下载字节是否大于 0 判断，因此短暂停顿不会让已产生流量的进程立即从列表消失。

网络速度和累计字节列保存原始数值用于排序，不使用格式化字符串的字典序。

## Windows 11 Actions 实验

独立 workflow `.github/workflows/etw-experiment.yml` 当前验证矩阵：

```text
windows-2025
windows-11-arm
```

Windows 11 Runner 实际环境：

- Microsoft Windows 11 Enterprise
- OS 10.0.26200
- ARM64
- Python 3.14.7 ARM64

2026-09-15 的 Stage 2C 最终 ETW Experiment 中：

- ETW / Collector 单元测试：`25 passed`
- 底层 loopback probe 使用同一 Session 名连续运行两次：通过
- 正式 `WindowsProcessNetworkCollector` probe 使用同一 Session 名连续运行两次：通过
- 两次正式 probe 均获得 `524288` upload bytes 与 `524288` download bytes
- `collector_available = true`
- close 后 `collector_closed = true`

该实验中 Windows 11 ARM64 正式 Collector 两次测得：

```text
run 1:
upload_bytes:               524288
download_bytes:             524288
upload_bytes_per_second:    2092071.61
download_bytes_per_second:  2092071.61

run 2:
upload_bytes:               524288
download_bytes:             524288
upload_bytes_per_second:    2095041.04
download_bytes_per_second:  2095041.04
```

正式 probe 对异步 ETW buffer delivery 使用有限轮询窗口，但验收条件没有放宽：必须实际观察到正的双向 bytes 和正的双向 B/s 才通过。

## Windows Server 2025 实验

当前 Runner：

- Microsoft Windows Server 2025 Datacenter
- OS 10.0.26100
- x64
- Python 3.14.7 x64

同一轮 ETW Experiment 中：

- ETW / Collector 单元测试：`25 passed`
- 底层双次 loopback probe：通过
- 正式 Collector 双次 probe：通过
- 两次正式 probe 均得到 `524288` upload bytes 与 `524288` download bytes
- Session cleanup / restart：通过

## 权限行为

在 GitHub Actions 的 Windows Server 2025 与 Windows 11 Enterprise ARM64 Runner 上均实际验证：

- 管理员 `runneradmin`：ETW Session 可启动、消费并停止，正式 Collector 可输出真实按进程流量。
- 临时标准本地用户：`StartTraceW` 返回 Windows error `5`（Access Denied）。

正式 Collector 将该错误映射为 `PERMISSION_DENIED`，GUI 显示需要管理员权限；其他 ETW 初始化异常映射为 `UNAVAILABLE`。

最终是否可用以 ETW Session 的真实启动结果为准，而不是单纯根据“当前用户是否管理员”进行猜测。

## 已知限制

- 当前 GitHub 托管 Windows 11 实验环境是 ARM64，不是 Windows 11 x64 物理桌面机。
- Windows 11 x64 物理机上的权限表现、长期运行和真实桌面 GUI 体验仍需最终本机验证。
- 当前已测试环境中，标准本地用户启动该 ETW Session 会收到 error 5；不同机器上的安全策略可能不同。
- ETW Provider 的 byte counters 表示所捕获网络事件中的字节计数；项目不会未经证据把它宣称为“应用层有效载荷的绝对精确字节数”。

## 环境

- Windows 11（目标环境）
- Python 3.14
- PySide6
- psutil

## 本地安装与启动

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
python -m net_monitor
```

在当前已测试环境中，需要具备 ETW Session 权限才能看到真实每进程上传/下载数据。权限不足时系统总流量和进程枚举仍保持可用。

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

## CI

主 CI 在 Windows Server 2025 x64 上使用 Python 3.14 创建独立 `.venv`，执行安装、导入、psutil、PySide6、ETW module、GUI tests 与完整 pytest。Stage 2C 当前回归：

```text
38 passed
```

主 CI 还验证 `.venv` 未被 Git 跟踪或作为未忽略改动出现，并确认仓库工作区干净。

独立 `ETW Experiment` workflow 在 `windows-2025` 与 `windows-11-arm` 上执行：

```text
Provider 查询
ETW / Collector 单元测试
底层 ETW 真实 loopback 双次捕获
正式 WindowsProcessNetworkCollector 双次端到端捕获
同名 Session cleanup / restart
标准本地用户权限表征
```

ETW Experiment 仅安装实验需要的最小 Python 依赖，避免 GUI 依赖影响 ETW 可行性结论。
