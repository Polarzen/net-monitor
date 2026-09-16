# Net Monitor

Net Monitor 是一个面向 Windows 11 的轻量第三方应用网络活动监视器。它的核心问题不是“做另一个任务管理器”，而是让用户随时看一眼：**现在谁在联网、谁正在下载、谁正在上传、哪个应用最活跃。**

当前版本：**v0.2 / Stage 3A UI + Stage 3B session integration**。

## 产品形态

Stage 3A 默认启动 **Compact Mode**，并保留独立 **Detailed View**：

- Compact：约 380 px 宽的常驻小工具，显示第三方应用总下载/上传速度、当前活跃应用数和 Top 5 当前联网应用。
- Detailed：保留 `application -> PID` 聚合树、下载/上传速度、累计量、PID 子项、系统进程开关和当前联网筛选。
- System Tray：支持显示主窗口、打开详细信息、切换总在最前、退出。
- Always on Top：默认关闭，由用户主动切换。
- Permission state：ETW 权限不足时 Compact 只显示简洁的“需要管理员权限”和显式管理员重启入口，不用大量 `—` 表格干扰快速查看。

Compact 的 Top 应用按原始数值排序：

```text
activity_score = download_bytes_per_second + upload_bytes_per_second
```

不会按 `"1 MB/s"`、`"900 KB/s"` 等格式化字符串排序。网络数据不可用时保持 `—`，不会把未知值当作 0。

“当前联网”仍严格表示 GUI 约 2 秒测量窗口内有流量：

```text
upload rate > 0 OR download rate > 0
```

短 burst 在窗口内按真实采样时间计算平均速率，不是“本次 Session 曾经联网”，也不是伪造实时值。

## 架构

Stage 3A 不修改 ETW 采集设计，也不会为 Compact 和 Detailed 各开一套采集器。运行时保持单数据源：

```text
ETW thread
    ↓
MonitorService
    ↓
SamplingWorker (QThread, ~500 ms)
    ↓
UiController / shared MonitorSnapshot
    ├── CompactWindow
    └── DetailWindow (基于现有 MainWindow 的详细视图)
```

因此默认只有：

- 一个 `MonitorService`
- 一个 `SamplingWorker`
- 一个 `WindowsProcessNetworkCollector`
- 一个 ETW Session

Detailed View 只消费 controller 已有的 snapshot，不创建第二个采集生命周期。

## 网络采集

真实按进程网络流量使用：

- Windows ETW
- `Microsoft-Windows-Kernel-Network`
- TDH
- `ctypes`

实时 ETW 会话使用独立会话模式，避免并发或残留会话在启用同一 provider 时互相影响。

系统与进程信息使用 `psutil`。项目不会用连接数、随机数或系统总流量平均分配来伪造按进程流量。

应用可见性继续采用保守分类：

```text
SYSTEM      默认隐藏
APPLICATION 默认显示
UNKNOWN     默认显示
```

第三方应用按相同 executable 路径进行保守聚合。PID 子项仍保留 `(pid, create_time)` 身份，避免 PID reuse 回归。

### Stage 3B 当前会话累计

应用会话累计只在当前 Net Monitor 进程生命周期内保留，不写 SQLite，也不跨重启恢复。可信身份是 `(pid, create_time)`；首次可信累计样本全额计入，之后每个方向只计入超过该方向高水位的增量。计数器回退或乱序不会被猜成新的 epoch，因此同一身份在重新超过旧高水位前可能漏计。`create_time` 缺失、网络行任一累计字段缺失或退休行 PID 与进程 PID 不一致时，整行不进入会话累计。

进程退出时，ETW PID 桶在同一锁内原子取出并从活动桶删除，退休样本交给会话 tracker 后只消费一次。PID reuse 的旧身份只交接最后确认值，新身份从混合 PID 桶建立隔离基线；原子切点后的迟到事件不回猜给旧身份。身份和去重状态贯穿整个应用会话，内存增长来自已见身份与累计账户的有意保留。

## 启动方式

### 开发运行

保留控制台，方便调试日志：

```powershell
python -m net_monitor
```

### 普通 GUI 启动

安装项目后使用：

```powershell
net-monitor
```

`pyproject.toml` 使用 `[project.gui-scripts]` 生成 Windows GUI launcher。Windows 下该 launcher 使用 GUI subsystem，不分配普通控制台窗口。

管理员重启仍只由用户点击触发。提权重启会优先选择当前虚拟环境旁的 `pythonw.exe`，并以 `-m net_monitor` 启动，不写死任何本地路径，也不会出现“普通启动无 console、管理员重启又弹 console”的设计回退。只有 `ShellExecuteW(..., "runas", ...)` 成功后当前实例才退出；如果 UAC 被拒绝或启动失败，当前程序继续运行。

## Tray 与关闭行为

如果系统支持托盘：

- 关闭 Compact：隐藏到托盘，不停止采集。
- 关闭 Detailed：只关闭/隐藏详细窗口，不关闭 Service。
- Tray `显示 Net Monitor`：恢复 Compact。
- Tray `详细信息`：复用同一个 Detailed 实例；如果已存在则 `show / raise / activate`。
- Tray `退出`：停止 Worker，关闭 Service/Collector，停止 ETW Session，然后退出 QApplication。

如果系统不支持托盘，关闭主窗口仍可正常结束应用，不会造成“程序关不掉”。Shutdown 是幂等的。

## UI 与性能

Stage 2D/2E 的性能原则保持不变：

- 网络采样仍在 `SamplingWorker / QThread` 中执行。
- 主线程不做 ETW 或 psutil 高成本采集。
- Detailed 树继续使用既有增量同步，不使用 `clear()` + 全量重建。
- Compact 的 Top 行在创建窗口时一次性构造，后续 snapshot 只更新文本和显隐，不在每次刷新重建 QWidget hierarchy。
- 不在刷新周期重载 stylesheet、重新创建托盘图标或做无必要 metadata 扫描。
- 采样频率继续约 500 ms，不改成 30/60 FPS UI timer。
- GUI 进程速率使用约 2 秒窗口：窗口内有流量时，“当前联网”表示近期测量窗口观察到流量；短 burst 在窗口内按真实采样时间计算平均速率，不伪造实时值。默认 `WindowsProcessNetworkCollector` 的窗口为 `0.0`，保留原有速率行为；GUI 使用 `2.0`，累计 bytes、PID/`create_time` 身份和进程刷新周期不变。

## 自动验证

完整 CI 在以下 GitHub 托管环境运行 Python 3.14：

- Windows Server 2025 x64 (`windows-2025`)
- Windows 11 Enterprise ARM64 (`windows-11-arm`)

执行：

```powershell
python -m pytest -v
```

Stage 3A 自动测试覆盖：

- Compact 创建与小尺寸默认值
- fake snapshot 消费
- Top active apps 原始数值排序
- 当前无网络活动 empty state
- permission denied 与管理员按钮可见性
- AVAILABLE 状态管理员按钮隐藏
- Detailed application aggregation / PID children / raw sorting / system filter / active filter
- Compact 与 Detailed 同一 snapshot
- Detailed 单实例复用
- 不创建第二个 MonitorService
- Tray 无能力环境 smoke 与真实托盘环境条件测试
- shutdown 幂等、detail close 不关闭 service、最终 exit 才关闭 service
- `[project.gui-scripts]` 配置
- Windows 安装后的 `net-monitor.exe` PE Subsystem 必须为 `IMAGE_SUBSYSTEM_WINDOWS_GUI`

## ETW Experiment

ETW Experiment 继续在双平台执行：

- Windows Server 2025 x64
- Windows 11 Enterprise ARM64

继续验证：

- Kernel Network provider
- ETW unit tests
- live loopback probe ×2
- production collector probe ×2
- same-session restart cleanup
- standard local user permission behavior

Stage 3A 的 `app.py`、controller、Compact/Detailed、Tray、theme、elevation、launcher 配置与 UI tests 均纳入 workflow path triggers，确保 UI 重构不会绕开真实 Collector 验证。

## Windows 11 x64 物理机仍需验收

GitHub Actions 不能替代真实桌面体验。Stage 3A 自动验证完成后仍需要在 Windows 11 x64 物理桌面确认：

- Compact 实际布局与信息密度
- 100% / 125% / 150% DPI
- Tray 恢复/隐藏行为
- Always-on-top 手感
- UAC relaunch
- `net-monitor` 实际无 console 启动
- 长时间驻留的 CPU、拖动和可用性

这些项目必须以实机体验为最终结论。

本轮（2026-09-16）验收记录见 [Stage 3A 本轮验收记录](docs/stage3a-acceptance-2026-09-16.md)。

### CPU 修复后的验收状态

已修复 GUI 进程采集不请求 `status` 带来的 CPU 开销，以及 ETW 批次在半秒刷新下造成的交替零速率。默认 collector/service 的公开行为兼容；GUI 采用用户接受的约 2 秒窗口，UI 约 500 ms 刷新、进程 2 秒刷新、PID/`create_time` 身份和累计 bytes 保持不变。Stage 3A 的精确验证结果记录在验收文档；Stage 3B 本地合并的测试结果和未验证边界记录在 [Stage 3B 集成记录](docs/stage3b-integration-2026-09-17.md)。

正式观察于 `2026-09-16 20:49:57–21:19:58+08` 完成 `1800.0012464s`、31 个连续样本；2 秒 collector probe 停流后约 `2.25s` 严格归零，GUI 观察中启动期外未再复现规律性双零，用户确认窗口、数据和托盘正常。该观察属于已验证的 Stage 3A 精确提交；当前 Stage 3B 集成本地工作树尚未产生最终提交，未来 CI/ETW 运行待集成后由 Root 安排。

## Stage 3A 范围边界

本阶段不实现 SQLite、历史数据库、时间线、图表、sparkline、AI 分析、域名/IP/GeoIP、限速、防火墙、Npcap、WinDivert、WFP、驱动、开机启动、自动更新、installer、账号或云同步。
