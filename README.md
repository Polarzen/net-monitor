# Net Monitor

Net Monitor 是一个面向 Windows 11 的轻量第三方应用网络活动监视器。它的核心问题不是“做另一个任务管理器”，而是让用户随时看一眼：**现在谁在联网、谁正在下载、谁正在上传、哪个应用最活跃。**

当前版本：**v0.2 / Stage 3C 微型应用状态窗与会话累计展示**。

实现、验证范围和指定桌面待验收项目见 [Stage 3C 记录](docs/stage3c-micro-widget.md)。

## 产品形态

新用户默认启动 **微型模式**；显示偏好可恢复上次选择的主模式。

- 微型窗：固定 **112×72 Qt 逻辑像素**，小圆角矩形，显示本地应用图标、短名称和上下行；长名称省略，完整信息在卡片。B 是字节，KiB/MiB 为 1024 进位，不是 bit/s。数字变化不改变窗体尺寸。
- 展开卡片：悬停约 350 ms 预览，跨入卡片不立即收起；离开联合区域延迟收起。点击后保持，Esc 收起。显示完整名称、可读路径、当前上下行、Top 3、固定关注及本次监控累计。`选择应用…` 不限于排行榜；从卡片点开菜单再选应用，共两次点击。
- Compact：原约 380 px 宽 Top 5 视图保留。微型窗右键菜单、卡片菜单或托盘可切回原 Compact；同一时刻只有一个主入口。
- Detailed：同一详细窗口保留 `application → PID` 树、原始数值排序和实时筛选；新增 **本次监控累计** 页签，已退出账户仍可查看，实时页筛选不删除累计账户。
- 固定关注绑定可信 application key，不绑定显示名称、PID 或排序位置。其他应用更快也不抢走对象；取消后恢复自动。本轮仅在当前运行期间保留关注。
- 窗口置顶和固定关注是不同操作。置顶默认关闭，微型窗置顶不会强制 Detailed 置顶。自动刷新、自动选择与悬停预览不主动激活窗口；实际焦点行为仍需物理桌面验收。

自动选择按原始上下行之和排序，稳定处理并列。首次有效数据立即选择；当前对象仍有流量时，挑战者持续领先约 2 秒后切换，当前归零则可立即换到有效候选。防抖只改变显示对象，不平滑速率或延长旧正速率；卡片 Top 3 始终按当前原始数值排序。

启动、权限不足、采集不可用、采样失败、数据过期、空闲、未运行与身份未知分别显示。可用数据停止更新约 4 秒后旧速率变为 `—`；已确认累计保留。`None` 不显示为 0，部分未知不声称全部应用空闲。缺失行或采样失败不能证明应用退出；可信账户的零关联进程数也会在存在未知身份时保守显示未知。

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

Stage 3C 冻结已验收 Stage 3B 内核，不为多个窗口各开一套采集器。运行时保持单数据源：

```text
ETW thread
    ↓
MonitorService
    ↓
SamplingWorker (QThread, ~500 ms)
    ↓
UiController / shared MonitorSnapshot
    ├── MicroWindow / ApplicationCard (只读 UI 投影)
    ├── CompactWindow (回退入口)
    └── DetailWindow (原实时树 + 只读累计页签)
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

### 本次监控累计（沿用 Stage 3B 内核）

应用会话累计只在当前 Net Monitor 进程生命周期内保留，不写 SQLite，也不跨重启恢复。可信身份是 `(pid, create_time)`；首次可信累计样本全额计入，之后每个方向只计入超过该方向高水位的增量。计数器回退或乱序不会被猜成新的 epoch，因此同一身份在重新超过旧高水位前可能漏计。`create_time` 缺失、网络行任一累计字段缺失或退休行 PID 与进程 PID 不一致时，整行不进入会话累计。

进程退出时，ETW PID 桶在同一锁内原子取出并从活动桶删除，退休样本交给会话 tracker 后只消费一次。PID reuse 的旧身份只交接最后确认值，新身份从混合 PID 桶建立隔离基线；原子切点后的迟到事件不回猜给旧身份。身份和去重状态贯穿整个应用会话，内存增长来自已见身份与累计账户的有意保留。

UI 直接消费 `MonitorSnapshot.application_session`，只按精确可信 key 关联；没有可证明的关联就显示“无可信累计”。不在 UI 积分速率、移动历史账户、合并同名账户或重复加账。首次归因的 key 不因路径元数据恢复而迁移，因而当前应用与旧匿名累计可能无法关联；旧账户仍独立保留在累计页签。历史分类缺失时保持未知，不臆造系统/第三方标签。

“本次监控累计”不是从点击关注开始、今日流量、应用全部历史或运营商账单；也不保证代理、回环与虚拟网卡已按外网去重。`active_process_count` 只表示最近枚举关联的进程数，不是当前联网进程数；累计大于 0 不等于当前联网。无流量不表示下载完成、上传成功或任务失败。Compact/实时页的应用合计不等于整机总流量。原详细树的存活进程累计不能替代会话累计页签。

## UI 设置与图标

仅保存主模式、微型/Compact 窗口逻辑位置和微型置顶偏好；默认使用当前用户本地 `NetMonitor/ui.json`，损坏时安全回退。不保存流量历史、累计、访问记录或关注应用 key。窗口拖动与点击分开，按可用区域停靠、展开并恢复越界位置；不改变系统缩放，不创建桌面拦截层。

图标只从可信本地可执行文件读取，失败显示本地通用图标；有界缓存包含失败项，阻塞 IO 在线程中处理，返回后校验 key，Qt 图像对象在 GUI 线程创建。不联网下载图标。CI 使用的测试字体不进入产品运行链路。

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

- 关闭当前主入口：隐藏到托盘，不停止采集。卡片关闭也不停止采集。
- 关闭 Detailed：只关闭/隐藏详细窗口，不关闭 Service。
- Tray `显示 Net Monitor`：恢复当前主模式，不强制回到 Compact。
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

继承的 Stage 3A 自动测试覆盖：

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

Stage 3C 另增可控单调时钟的选择/防抖/过期、精确 key 关注、未知状态、卡片与详细窗口单实例、模式切换与单 Worker、悬停联合区域、拖动、设置损坏、负坐标恢复、异步图标缓存、累计账户保留与大整数原始排序等测试。隐藏累计页签只接收引用，不重绘树；重复快照不增加流量。

CI 使用 real widgets + **fake snapshot** 生成 100% / 125% / 150% 渲染，并检查字体字形、微型尺寸、速率宽度/高度；失败先保存 PNG 和诊断。测试专用 Noto CJK 字体锁定上游提交和 Git blob、校验字节，不打包或上传字体。JUnit、布局、环境/完整 SHA 和精确源码归档作为短期产物。它们不是真实桌面截图或 ETW 流量证据。

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

Stage 3C 分支、UI/测试/辅助工具和工作流文件均纳入 branch/path triggers。每次 raw/production probe 独立传播原生命令退出码，不以第二次成功掩盖第一次失败；保留两平台、psutil 与真实子进程 PID 握手。CI 还比较冻结内核与精确 Stage 3B 基线的 diff。

## Windows 11 x64 物理机仍需验收

GitHub Actions 不替代真实桌面体验。**新微型窗仍待** Windows 11 物理桌面确认 100% / 125% / 150% 可读性、悬停/刷新不抢焦点、拖动无误触、卡片不闪烁越界、多显示器负坐标与拔插恢复、托盘按当前模式恢复、UAC 接受/取消、实际无控制台启动和退出清理。旧 GUI 与旧 150% 缩放结论不能直接算作新 UI 通过。

本机验证仅针对上述桌面差异，先核对实际加载源码路径和精确 SHA；不默认要求重跑全量 pytest/ETW 或 30 分钟驻留。当前开发环境不是用户 Windows 本机，未启动其 GUI、ETW 或 Codex。小窗口不意味着更低内存或 CPU；无新的同机性能证据，不作 CPU/内存降低或长期无泄漏保证。

2026-09-16 的历史验收记录见 [Stage 3A 历史验收记录](docs/stage3a-acceptance-2026-09-16.md)。

### CPU 修复后的验收状态

已修复 GUI 进程采集不请求 `status` 带来的 CPU 开销，以及 ETW 批次在半秒刷新下造成的交替零速率。默认 collector/service 的公开行为兼容；GUI 采用用户接受的约 2 秒窗口，UI 约 500 ms 刷新、进程 2 秒刷新、PID/`create_time` 身份和累计 bytes 保持不变。Stage 3A 的精确验证结果记录在验收文档；Stage 3B 本地合并的测试结果和未验证边界记录在 [Stage 3B 集成记录](docs/stage3b-integration-2026-09-17.md)。

正式观察于 `2026-09-16 20:49:57–21:19:58+08` 完成 `1800.0012464s`、31 个连续样本；2 秒 collector probe 停流后约 `2.25s` 严格归零，GUI 观察中启动期外未再复现规律性双零，用户确认窗口、数据和托盘正常。该观察属于已验证的 Stage 3A 精确提交；该历史记录中的“待集成”不是当前状态：本轮基于远端 Stage 3B `09ff140dfa5c299840189fe02ede1b1cb95fd9cb` 续接 Stage 3C，当前验证以对应功能分支精确 SHA 的交付报告为准。

## Stage 3C 范围边界

本阶段不提供网络加速、任务完成识别、动画宠物、流量控制，也不实现 SQLite、历史数据库、时间线、图表、sparkline、AI 分析、域名/IP/GeoIP、限速、防火墙、Npcap、WinDivert、WFP、驱动、开机启动、自动更新、installer、账号或云同步。
