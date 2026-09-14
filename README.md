# Net Monitor

Net Monitor 是一个面向 Windows 11 的桌面网络监控工具，使用 Python 3.14、PySide6 和 psutil 构建。

## 当前目标

- 实时显示系统总上传/下载速度
- 枚举当前运行进程
- 为后续 Windows 原生按进程网络流量采集保留统一 Collector 接口

## 当前开发阶段

- 系统网络统计：已实现
- 进程枚举：已实现
- GUI：已实现基础版本
- 按进程网络字节统计：尚未实现，后续使用 Windows 原生机制（计划 ETW）实现

> psutil 可以提供系统网络计数与进程信息，但不能直接、可靠地提供 Windows 下每个进程的实时收发字节数。本项目不会用连接数、随机数或平均分配系统流量来伪造该数据。

## 环境

- Windows 11
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

## 架构

```text
Collector -> Service -> Model -> UI
```

UI 不直接依赖 psutil 或 Windows API，因此后续接入 ETW Collector 时无需重写界面层。

## CI

GitHub Actions 在 `windows-latest` 上使用 Python 3.14 执行安装、导入、psutil、PySide6、GUI smoke test 与 pytest 验证。
