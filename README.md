# Net Monitor

Net Monitor 是一个面向 Windows 11 的桌面网络监控工具，使用 Python 3.14、PySide6 和 psutil 构建。

## 当前目标

- 实时显示系统总上传/下载速度
- 枚举当前运行进程
- 使用 Windows 原生机制获取每个进程的真实网络流量

## 当前开发阶段

- 系统网络统计：已实现
- 进程枚举：已实现
- GUI：已实现基础版本
- Windows ETW 按进程网络采集 PoC：已在 GitHub Actions Windows Server 2025 上验证
- 正式 `WindowsProcessNetworkCollector` ETW 接入：尚未实现
- Windows 11 真机普通用户/管理员权限验证：尚待真机完成

> psutil 可以提供系统网络计数与进程信息，但不能直接、可靠地提供 Windows 下每个进程的实时收发字节数。本项目不会用连接数、随机数或平均分配系统流量来伪造该数据。

## ETW Development Status

第二阶段 2A 使用 `Microsoft-Windows-Kernel-Network` Provider（GUID `{7DD42A49-5329-4832-8DFD-43D979153A88}`）验证按进程网络事件采集。

当前 PoC 已实现：

- `ctypes` 封装 ETW Session 与实时 Consumer
- TDH 按 schema 读取事件中的 `PID` 与 `size`
- 区分 TCP/UDP 的 SEND / RECEIVE 事件
- 后台线程运行 `ProcessTrace`
- PID 级发送/接收字节累计
- Session stop / cleanup
- 受控 loopback 子进程验证 PID 与双向字节

GitHub Actions 的受控探针已确认测试子进程 PID 可以被匹配，并可获得真实的发送与接收字节。本阶段仍属于 PoC，尚未替换 GUI 当前使用的占位 `WindowsProcessNetworkCollector`。

Windows PID 会被重用；2B 正式 Collector 应使用 `(pid, process_create_time)` 或等价方式管理长生命周期进程身份。

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

## ETW PoC

先确认 Provider：

```powershell
logman query providers "Microsoft-Windows-Kernel-Network"
```

交互式 PoC：

```powershell
python -m net_monitor.collectors.etw
```

受控 loopback 验证：

```powershell
python -m net_monitor.collectors.etw.probe
```

受控探针会启动独立 Python 子进程产生本地 TCP 双向流量，并要求 ETW 结果中出现该子进程 PID、SEND 事件、RECEIVE 事件以及正的双向累计字节数。

## 架构

```text
Collector -> Service -> Model -> UI
```

UI 不直接依赖 psutil 或 Windows API，因此后续接入正式 ETW Collector 时无需重写界面层。

ETW PoC 自身进一步拆分为：

```text
Windows ETW API / TDH
        ↓
EtwSession
        ↓
NetworkEvent
        ↓
NetworkAggregator
```

## CI

GitHub Actions 在 `windows-latest` 上使用 Python 3.14 创建独立 `.venv`，执行安装、导入、psutil、PySide6、GUI smoke test 与 pytest。`feat/etw-network-poc` 分支还会查询 Kernel Network Provider，并运行真实 ETW loopback 探针验证 PoC。
