# Net Monitor

Net Monitor 是一个面向 Windows 11 的桌面网络监控工具，使用 Python 3.14、PySide6 和 psutil 构建。

## 当前目标

- 实时显示系统总上传/下载速度
- 枚举当前运行进程
- 使用 Windows 原生 ETW 获取每个进程的真实网络流量

## 当前开发阶段

- 系统网络统计：已实现
- 进程枚举：已实现
- GUI：已实现基础版本
- Windows ETW 按进程网络采集 PoC：已验证
- 正式 `WindowsProcessNetworkCollector` ETW 接入：已在 `feat/etw-process-collector` 实现并通过 Actions 实验
- Windows 11 x64 物理机权限与长期运行验证：尚待目标机器完成

> psutil 可以提供系统网络计数与进程信息，但不能直接、可靠地提供 Windows 下每个进程的实时收发字节数。本项目不会用连接数、随机数或平均分配系统流量来伪造该数据。

## ETW Development Status

第二阶段 2A 使用 `Microsoft-Windows-Kernel-Network` Provider（GUID `{7DD42A49-5329-4832-8DFD-43D979153A88}`）验证按进程网络事件采集；第二阶段 2B 将已验证的 ETW 链路接入正式 `WindowsProcessNetworkCollector`。

当前实现包括：

- `ctypes` 封装 ETW Session 与实时 Consumer
- TDH 按 schema 读取事件中的 `PID` 与 `size`
- 区分 TCP/UDP 的 SEND / RECEIVE 事件
- 后台非 daemon 线程运行 `ProcessTrace`
- PID 级发送/接收字节与事件次数累计
- 正式 Collector 懒启动 ETW Session
- 按真实采样时间计算每进程上传/下载 B/s
- `ProcessInfo.create_time` 与 `(pid, create_time)` 基线，降低 PID 重用导致旧流量串入新进程的风险
- 清理已退出 PID 的历史聚合数据，避免长期运行无限积累
- ETW 权限不足时返回不可用值，而不是伪造数据或让 GUI 崩溃
- `MonitorService.close()`、窗口关闭和应用退出时停止 ETW Session
- 同一 Session 名连续启动两次的 cleanup / restart 验证

## Windows 11 Actions 实验

独立 workflow `.github/workflows/etw-experiment.yml` 使用矩阵同时验证：

```text
windows-2025
windows-11-arm
```

Windows 11 Runner 实际环境：

- Microsoft Windows 11 Enterprise
- OS 10.0.26200
- ARM64
- Python 3.14.7 ARM64

### 2A 底层 ETW 验证

在 Windows 11 Enterprise ARM64 Runner 上，受控 loopback 子进程的 PID 可以被 ETW 正确匹配，并能获得真实 SEND / RECEIVE 字节；相同 Session 名连续启动两次均成功。

### 2B 正式 Collector 验证

`collector_probe.py` 不直接读取 `NetworkAggregator`，而是通过正式 `WindowsProcessNetworkCollector` 完成完整路径验证：

```text
受控子进程
    ↓
Microsoft-Windows-Kernel-Network
    ↓
EtwSession / TDH
    ↓
NetworkAggregator
    ↓
WindowsProcessNetworkCollector
    ↓
ProcessNetworkStats
```

Windows 11 ARM64 上连续两次使用同一 Session 名验证均通过。

第一次：

```text
upload_bytes:               524288
download_bytes:             524288
upload_bytes_per_second:    228387.89
download_bytes_per_second:  228387.89
collector_available:        true
collector_closed:           true
```

第二次：

```text
upload_bytes:               524288
download_bytes:             524288
upload_bytes_per_second:    228217.79
download_bytes_per_second:  228217.79
collector_available:        true
collector_closed:           true
```

Windows Server 2025 x64 上相同的正式 Collector 双次探针也通过。

## 权限行为

在 GitHub Actions 的 Windows Server 2025 和 Windows 11 Enterprise ARM64 Runner 上均实际验证：

- `runneradmin` 管理员上下文：ETW Session 可以启动、消费并停止，正式 Collector 可以输出真实按进程流量。
- 临时创建且未授予额外组权限的标准本地用户：`StartTraceW` 返回 Windows error `5`（Access Denied）。

因此，在当前已测试环境中，真实 ETW 按进程统计需要相应权限。正式 Collector 在权限不足时会保持程序可用，并让进程网络字段显示为不可用，而不会生成估算值。

GitHub 托管 Windows 11 Runner 是 ARM64；项目最终主要目标仍是 Windows 11 x64 桌面环境，因此 x64 物理机的权限行为和长时间稳定性仍建议继续验证。

## 环境

- Windows 11（目标环境）
- Python 3.14

## 本地安装与启动

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
python -m net_monitor
```

在当前已测试环境中，需要以具备 ETW Session 权限的终端运行，才能看到真实每进程上传/下载数据；权限不足时系统总流量和进程枚举仍可使用。

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

UI 不直接依赖 psutil 或 Windows API。正式 ETW Collector 接入后，现有表格无需重写即可显示真实上传速度、下载速度和累计流量。

ETW 采集内部结构：

```text
Windows ETW API / TDH
        ↓
EtwSession
        ↓
NetworkEvent
        ↓
NetworkAggregator
        ↓
WindowsProcessNetworkCollector
        ↓
MonitorService
        ↓
UI
```

## CI

主 CI 在 `windows-latest` 上使用 Python 3.14 创建独立 `.venv`，执行安装、导入、psutil、PySide6、GUI smoke test 与完整 pytest。当前 2B 回归为：

```text
30 passed
```

独立 `ETW Experiment` workflow 在 `windows-2025` 与 `windows-11-arm` 上执行：

```text
Provider 查询
ETW / Collector 单元测试
底层 ETW 真实 loopback 双次捕获
正式 WindowsProcessNetworkCollector 双次端到端捕获
同名 Session cleanup / restart
标准本地用户权限表征
```

ETW Experiment 只安装该实验需要的最小 Python 依赖，避免 PySide6/psutil 的架构兼容性影响 ETW 结论。
