# Net Monitor

Net Monitor 是一个面向 **Windows 11** 的桌面应用网络活动监视器。它按应用显示上传、下载速率和本次运行期间的累计流量，帮助你了解当前哪个应用在联网，以及后台下载或上传是否仍在持续。

默认的微型窗口占用 **220 × 112 Qt 逻辑像素**；需要更多信息时，可以展开应用卡片、切换 Compact 列表，或打开按应用和进程组织的详细窗口。

**[下载 Windows x64 公开测试版 0.2.1.dev4](https://github.com/Polarzen/net-monitor/releases/tag/v0.2.1.dev4)** · [产品 ZIP](https://github.com/Polarzen/net-monitor/releases/download/v0.2.1.dev4/NetMonitor-0.2.1.dev4-windows-x64-4bf4e02fce84-prerelease.zip) · [校验文件](https://github.com/Polarzen/net-monitor/releases/download/v0.2.1.dev4/SHA256SUMS.txt) · [中文说明](https://github.com/Polarzen/net-monitor/releases/download/v0.2.1.dev4/USAGE.zh-CN.txt)

本版已作为 GitHub **Pre-release** 发布，未签名，不是稳定版。新增累计搜索和 CSV 导出，并减少隐藏详细视图的无用刷新。最终 ZIP 已完成实际启动、管理员身份核验、两小时资源观察、两轮回环累计 CSV 精确核对、正常退出及所观察 ETW 会话清理。完整范围与尚未验证项见[本版发布记录](docs/releases/0.2.1.dev4.md)。

发布包固定来自源码 `4bf4e02fce841a721f59f786e2f5fc8ec758db97`，标签 `v0.2.1.dev4` 精确指向它；main 可包含其后的合并和文档提交。后续 CI 产物不会自动替换已发布 ZIP。PID 身份不确定区间采用保守归属，可能少计未知区间或退出尾部。

[使用方法](#使用方法) · [源码运行](#从源码运行) · [构建测试包](#构建-windows-x64-测试包) · [历史包](#历史包对照)

## 主要功能

- **按应用观察网络活动**：查看上传、下载速率、活跃应用排行，以及应用下属的进程。
- **微型窗口与应用卡片**：平时只显示一个应用；展开后查看短期曲线、Top 3 和本次累计。
- **自动显示与固定关注**：自动选择活跃应用，也可以固定一个应用，避免显示对象随排行榜变化。
- **详细窗口**：按应用／PID 展开、排序和筛选，单独查看本次监控累计；有流量的已退出应用仍保留累计记录。累计页支持搜索和手动 CSV 导出。
- **托盘与显示偏好**：隐藏主窗口后继续采集，保存主模式、窗口位置和微型窗口置顶偏好。
- **区分零值与未知**：权限不足、采集不可用或数据过期时显示 `—`，不会用 `0 B/s` 代替未知流量。

网络数据来自 Windows ETW；系统与进程信息由 psutil 提供。当前不提供限速、防火墙、流量拦截、网络加速或长期流量数据库。

## 下载与首次启动

### 运行要求

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 11 x64 |
| 安装方式 | 解压完整目录后运行，无安装器 |
| Python | 使用测试包无需另装 Python、pip 或 PySide6 |
| 采集权限 | 真实按进程网络采集需要管理员权限 |
| ARM64 | 已有源码回归，当前没有 ARM64 发行包 |

### 获取公开测试版

1. 打开 [v0.2.1.dev4 Release](https://github.com/Polarzen/net-monitor/releases/tag/v0.2.1.dev4)，下载 `NetMonitor-0.2.1.dev4-windows-x64-4bf4e02fce84-prerelease.zip`。
2. 将产品 ZIP **完整解压**，打开其中的 `NetMonitor` 文件夹。
3. 双击 `NetMonitor.exe`。首次默认微型模式；之后按已保存偏好恢复。

无需安装 Python。请保留 EXE、`_internal`、`licenses` 等全部内容，**不能只复制 EXE**。普通用户不需要下载组件源码附件，也不要把 GitHub 自动生成的 Source code.zip 当作产品程序。

| 产物信息 | 值 |
| --- | --- |
| 版本／标签 | `0.2.1.dev4` / `v0.2.1.dev4` |
| 构建源码 S | `4bf4e02fce841a721f59f786e2f5fc8ec758db97` |
| 产品 ZIP 大小 | 38,790,423 字节 |
| SHA-256 | `640e10c7bd00cd71aff3030935421cbf674104e0f9941d80d0fcceda7d1af9f2` |
| 构建来源 | Windows 11 x64 本地锁定构建，见[发布记录](docs/releases/0.2.1.dev4.md#产物身份)；对应源码 CI 通过 |

需要校验时，可将 `Get-FileHash -Algorithm SHA256` 的结果与 Release 的 [SHA256SUMS.txt](https://github.com/Polarzen/net-monitor/releases/download/v0.2.1.dev4/SHA256SUMS.txt) 对照；校验和不是数字签名。包内 `BUILD-INFO.json`、中文说明及第三方材料对应同一源码；发布记录集中在 [0.2.1.dev4.md](docs/releases/0.2.1.dev4.md)。

### 历史包对照

旧 [0.2.1.dev3 Pre-release](https://github.com/Polarzen/net-monitor/releases/tag/v0.2.1.dev3) 保留原资产：源码 `e5e4329b48f55fd48dbf7c72673a7a287690da1b`，ZIP SHA-256 `062f0efcc43149a174e1c7ebd95fc86f0250f57fcf003e022e323b694ea9c241`。其采集界面由用户定性确认，未取得精确 CSV；详细边界见[dev3 发布记录](docs/releases/0.2.1.dev3.md)，不继承 dev4 的两小时观察和精确导出结果。

旧 `0.2.1.dev2 / 82ba3a1` 修复候选保留为历史：源码 `82ba3a1f21f240e114a112d2b94800ef3b285696`，产品 `NetMonitor-0.2.1.dev2-windows-x64-82ba3a1f21f2-test.zip`，SHA-256 `400f047c83ec3d8341f9356fa41db6de202f4ca28b3bef19ce07f70d4648cb9d`。[原 artifact](https://github.com/Polarzen/net-monitor/actions/runs/38056842914/artifacts/11671937543) 可能到期；该包当时由用户停止运行确认，未取得有效采集结论，不自动继承 dev3 结果。

旧 [dev2 artifact 11668988603](https://github.com/Polarzen/net-monitor/actions/runs/38051119145/artifacts/11668988603) 仅保留作历史对照，**存在已复现的 PID 复用归属问题，不再作为默认推荐**：

- 源码：`2b6db24173a17532e3371d7e14406247d72e380e`。
- 产品 ZIP：`NetMonitor-0.2.1.dev2-windows-x64-2b6db24173a1-test.zip`。
- SHA-256：`b63547f20e0f09418cdd1194d93be05650ec92c3ef53c6f46c8f634e5c27e795`。

其权限说明、管理员启动和短回环活动的实测记录继续保留在 [Stage 5 历史记录](docs/stage5-windows-package.md#内部试用与问题闭环2026-10-10)。两个包都显示 `0.2.1.dev2`，必须用源码提交和 ZIP 哈希区分。

### 开始采集

程序默认以普通权限启动，不自动要求提权。提示需要管理员权限时，展开应用卡片，或切换到 Compact，点击 **“以管理员身份重启”**，再由你决定是否接受 Windows 原生 UAC。

权限不足时仍可查看界面，但上传、下载显示为 `—`，不能据此判断应用没有流量。dev4 已核实同一发行目录的管理员新实例与有效令牌；原生取消仍只有自动测试证据。如果没有出现 UAC 或重启后仍提示权限不足，保留提示和构建信息用于反馈。

## 使用方法

以下描述当前已实现的操作方式；各项在打包 EXE 上的实测覆盖情况见后面的验证表。

### 选择视图

| 视图 | 如何打开 | 适合查看 |
| --- | --- | --- |
| 微型模式（Micro） | 默认启动；或主窗口右键菜单 →“微型模式” | 一个应用的上下行速率、前台／后台／未知状态 |
| 应用卡片（Card） | 悬停微型窗口预览，或单击微型窗口打开 | 完整名称、短期曲线、Top 3、固定关注和本次累计 |
| Compact | 主窗口右键菜单 →“原 Compact 模式”，也可从卡片“菜单”进入 | Top 5 活跃应用和整体状态 |
| 详细窗口（Detailed） | 点击“详细信息”，或从主窗口右键／托盘菜单打开 | 应用与 PID 列表、排序筛选和“本次监控累计”页签 |

微型窗本身不显示曲线，短期曲线位于应用卡片中。悬停预览后，将鼠标移出窗口和卡片区域会延迟收起；点击打开或与卡片交互后可保持展开，按 `Esc` 收起。拖动微型窗口可调整位置，长名称的完整信息可通过悬停提示查看。

关闭详细窗口只关闭该视图，不结束主程序。Compact 顶部的“窗口”菜单也提供“微型模式”和“退出”。

### 固定关注一个应用

1. 打开应用卡片，点击 **“固定关注”**，关注当前应用。
2. 要选择其他应用，点击 **“选择应用…”**，再点击列表中的目标；选择后会固定关注该应用。卡片 Top 3 中的应用也可点击关注。
3. 点击 **“取消关注”**，或从主窗口右键菜单选择“取消固定关注”，恢复自动显示。

固定关注后，其他应用更活跃也不会抢走显示对象。无法可靠识别身份的应用不能固定关注；关注状态仅在当前运行期间保留。

**固定关注与窗口置顶是两件事**：前者决定看哪个应用，后者决定窗口是否盖在其他窗口上方。“前台／后台”描述应用状态，也不代表它是否被固定关注。

### 搜索和导出本次累计

打开“详细信息 → 本次监控累计”，按应用名称、路径或账户标识搜索；清空搜索可以恢复全部累计记录。点击“导出 CSV…”会保存点击时可见的搜索结果和排序，取消或完成导出都不会清零累计。

默认不导出路径及账户标识；只有勾选“导出包含路径和账户标识”才加入这两列。应用名称本身仍可能包含私人信息，分享前请检查文件。字节列使用原始整数，电子表格可能舍入超长数值，需要精确处理时按文本导入。导出仅写入你选择的位置，不自动上传或定时保存。

### 隐藏、恢复与退出

- **隐藏**：系统支持托盘时，关闭主窗口或选择“隐藏到托盘”，程序继续运行和采集。
- **恢复**：右键系统托盘中的 Net Monitor 图标，选择“显示 Net Monitor”，恢复当前主模式；图标可能位于系统托盘的隐藏图标区域。
- **退出**：选择托盘菜单、主窗口右键菜单或 Compact“窗口”菜单中的“退出”，结束本次监控。

没有可用系统托盘时，关闭主窗口会结束应用。退出或重启后，本次累计从新会话重新开始。

## 如何理解数据

| 显示内容 | 含义 |
| --- | --- |
| 下载 / 上传 | 数据进入 / 离开应用的速率 |
| `B/s`、`KiB/s`、`MiB/s` | 每秒字节数；KiB、MiB 按 1024 进位，不是 bit/s |
| `0 B/s` | 当前有效采样确认没有流量 |
| `—` | 数据未知、不可用或已过期；结合状态文字判断原因 |
| 当前联网 | 最近约 2 秒测量窗口内有上传或下载流量 |
| 本次监控累计 | 本次 Net Monitor 进程运行期间确认的流量，不跨重启保存 |

界面约每 500 ms 更新，速率采用约 2 秒测量窗口，因此停止下载后可能短暂保留窗口内的平均速率。长时间没有有效更新时，旧速率会转为未知，而不是一直显示旧数字。

累计大于零不代表应用当前仍在联网；已退出且有流量的应用仍可出现在累计页。上传和下载累计都为零的账户会从该视图隐藏，筛选不会删除已记录的累计。

这些数据不是运营商账单，也不等于整机外网总流量。代理、回环、虚拟网卡、协议开销和测量窗口会影响与其他工具的对比；没有流量也不能证明某个下载任务已成功完成。

## 配置与本地数据

显示偏好保存在：

```text
%LOCALAPPDATA%\NetMonitor\ui.json
```

只保存主模式、窗口位置及微型窗口置顶偏好，不保存长期流量历史、累计或关注应用。图标从本地可执行文件读取，不联网下载；当前没有账号或云同步功能。

配置不写入 EXE 或 `_internal`，移动整个程序目录后仍使用当前用户的配置。要重置界面偏好，先正常退出，再备份并删除 `ui.json`；缺失或损坏的配置会回退到默认值。删除程序目录不会同时删除用户配置。

当前版本没有新增持久错误日志。未处理的启动异常沿用 PyInstaller 的错误对话框，请保留提示原文。

## 常见问题

| 现象 | 可以先检查 |
| --- | --- |
| 上传、下载一直为 `—` | 结合状态文字区分权限不足、采集不可用和数据过期；`0 B/s` 才表示有效采样确认无流量。已取得权限仍异常时，保留状态和错误原文并反馈 |
| 关闭窗口后程序仍在运行 | 主窗口通常隐藏到托盘；请使用菜单“退出”真正结束 |
| 只复制 EXE 后启动失败，提示 DLL 或 Qt 插件缺失 | 重新完整解压产品 ZIP，保留全部依赖目录 |
| 找不到窗口 | 从托盘选择“显示 Net Monitor”；需要重置位置时按配置章节处理 |
| 累计与其他软件不同 | 确认比较的是同一应用、同一会话和同一时间范围，并考虑代理、回环及协议开销 |
| 无法固定关注某个应用 | 该行可能缺少可靠身份，程序不会按同名应用或复用 PID 猜测对象 |
| 系统提示未知发布者或安全告警 | 当前包未签名；核对来源并保留原始提示，不要通过关闭安全保护解决 |

### 反馈问题

遇到问题可填写[问题反馈表单](https://github.com/Polarzen/net-monitor/issues/new?template=bug_report.yml)，也可从[反馈入口](https://github.com/Polarzen/net-monitor/issues/new/choose)选择空白 Issue。请提供版本或下载来源、Windows 版本／架构、实际与预期结果、操作步骤及频率。版本可从 ZIP 文件名或 `BUILD-INFO.json` 查看，无法取得可写“不确定”；偶发问题可写“暂时不能稳定复现”。无需安装 Python 或准备诊断包。源码提交、视图、权限状态、错误原文及截图均可按需补充。

**Issue 内容会公开。** 不必上传完整 `BUILD-INFO.json`、整个发行目录、私人日志或完整进程列表。截图只保留相关窗口，并遮挡私人路径、无关应用和浏览器内容；不要公开个人联系方式、IP、MAC、订阅地址或访问令牌。可能涉及安全漏洞时，请勿公开敏感利用细节。问题如何分类、修复及发布见[维护说明](docs/maintenance.md)。

## 从源码运行

当前公开版本为 `0.2.1.dev4`。main 可包含其后的验收工具和文档提交；发布包始终对应上方固定源码和 ZIP 哈希。内部候选的历史记录见 [dev4 开发候选](docs/dev4-candidate.md)。

需要 Windows、Git 和 Python **3.14 或更新版本**。当前验收及打包使用 Python **3.14.7**；构建 x64 测试包时还需匹配下节的精确版本和架构。

以下示例从主分支 `main` 创建新检出目录，使用 PowerShell：

```powershell
git clone --branch main https://github.com/Polarzen/net-monitor.git
Set-Location net-monitor
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\net-monitor.exe
```

已有工作区可复用其虚拟环境，不必再次创建。GUI launcher 不分配普通控制台；需要控制台调试时运行：

```powershell
.\.venv\Scripts\python.exe -m net_monitor
```

源码和打包程序使用同一正式入口；源码提权使用当前环境的 `pythonw.exe -m net_monitor`，打包提权直接重启当前 `NetMonitor.exe`。开发依赖与打包依赖分开管理。

## 构建 Windows x64 测试包

构建要求 **Windows 原生 CPython 3.14.7 x64**，采用 PyInstaller **onedir + windowed**。先提交已审阅的相关源码和构建输入；脚本会拒绝未提交的构建输入或不匹配的环境。

在上述新检出目录中，为构建创建独立环境：

```powershell
py -3.14 -m venv .venv-build-stage5
.\.venv-build-stage5\Scripts\python.exe -m pip install --require-hashes -r .\packaging\requirements-windows-x64.lock
.\tools\build_windows.ps1
```

`py -3.14` 选择的解释器必须实际为 3.14.7 x64；可先用 `py -3.14 -c "import platform; print(platform.python_version(), platform.machine())"` 检查。已有构建环境时复用即可。

使用 `-Channel public-prerelease` 可生成公开预发布候选元数据；默认 `internal-test`。构建成功不代表已发布或通过实际运行确认。

默认输出到 `artifacts/stage5/NetMonitor-<版本>-windows-x64-<源码短 SHA>-test/`，包含 ZIP、外部校验文件和构建报告。重复构建同一提交不会覆盖旧目录，可使用 `-OutputRoot` 指定新的输出根目录。

锁文件固定 PyInstaller 6.22.3、hooks-contrib 2026.8、PySide6 6.11.2、psutil 7.2.2 及传递依赖的版本和哈希。完整复现步骤、许可证来源、失败修复和产物身份见 [Stage 5 打包记录](docs/stage5-windows-package.md)。构建目录、虚拟环境和二进制产物均不进入 Git。

## 开发测试

安装上文的开发依赖后，可执行完整源码测试。布局测试需要固定字体；以下 PowerShell 示例先准备字体，只在测试期间设置离屏环境，结束后恢复原值：

```powershell
$testFontDirectory = Join-Path $env:TEMP 'net-monitor-test-fonts'
.\.venv\Scripts\python.exe tools/layout_fonts.py --prepare $testFontDirectory
if ($LASTEXITCODE -ne 0) { throw 'Test font preparation failed' }
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousLayoutFont = $env:NET_MONITOR_LAYOUT_FONT
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:NET_MONITOR_LAYOUT_FONT = Join-Path $testFontDirectory 'NotoSansCJKsc-Regular.otf'
    .\.venv\Scripts\python.exe -m pytest -v -ra
} finally {
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:NET_MONITOR_LAYOUT_FONT = $previousLayoutFont
}
```

首次准备字体需要联网，工具校验固定上游文件；测试字体不随产品分发。真实 GUI 验证不要使用 `offscreen` 或 `minimal` 平台。CI 的具体步骤见 [工作流](.github/workflows/ci.yml)。

## 验证状态与已知限制

以下状态只对应上述最终 dev4 ZIP；不自动适用于其他源码或哈希。

| 范围 | 本版结果 |
| --- | --- |
| 自动回归 | 本地完整回归 364 passed、1 skipped，打包检查 23 passed；源码 CI x64／ARM64 与 x64 打包通过 |
| 产物身份 | ZIP CRC、322 个清单条目及 205 个构建输入已复核；公开 ZIP 与实际运行包哈希一致 |
| 实际启动／提权 | 中文和空格目录、不同工作目录启动；管理员新实例路径、PID、创建时间和令牌已核实 |
| 真实采集与导出 | 起止两轮 60 秒本机回环负载；实际 CSV 的两个账户上下行原始字节与负载日志精确一致，默认不含路径／账户标识 |
| 两小时资源观察 | 同一实例 1,436 次采样，读取错误 0、最大间隔 5.271 秒；首尾区间与峰值见发布记录，不据此宣称无泄漏或全程界面响应 |
| 正常退出与 ETW | 用户经 Compact“窗口 → 退出”，确认目标实例与负载进程结束；结束时三个 ETW 丢失计数为 0，退出后原会话查询为 4201 |
| PID 复用 | 当前完整回归包含 10 项受控身份归属回归；没有现场制造 OS PID 复用 |
| 仍未完整验证 | 干净 Windows、真实多屏／混合缩放、全部 Micro/Card/关注/托盘交互、原生取消、显式零值、完整性能三场景及更长时间运行 |

本版达到带上述限制的公开测试版确认范围，不代表全套 Stage 4／Stage 5 或稳定版验收通过。详细数值与证据边界见[发布记录](docs/releases/0.2.1.dev4.md)，后续环境及签名步骤见[稳定版验收](docs/stable-readiness.md)；历史版本保留各自源码与哈希边界。

## 技术与文档

项目使用 Python、PySide6 和 psutil，通过 Windows ETW 的 `Microsoft-Windows-Kernel-Network` provider 与 TDH 获取按进程网络活动。多个视图共享同一采集链路；隐藏视图停止展示更新，采集、累计和有界短期历史继续维护。

应用按可信身份聚合，保留 PID 与创建时间以区分进程复用；累计直接来自确认的数据，不通过 UI 对速率积分。实现细节和历史证据集中在以下文档：

| 文档 | 内容 |
| --- | --- |
| [dev4 公开发布记录](docs/releases/0.2.1.dev4.md) | 已发布资产、源码/标签、实际验证及限制 |
| [稳定版验收](docs/stable-readiness.md) | 干净 Windows、多屏、运行观察及独立签名步骤 |
| [Stage 5 打包与交付](docs/stage5-windows-package.md) | 构建、版本、校验值、实际 EXE 验证及 CI artifact |
| [Stage 4 轻量化与验收](docs/stage4-lightweight.md) | 隐藏刷新、真实桌面／ETW、资源测量及限制 |
| [微型窗口设计](docs/stage3c-micro-widget.md) | 卡片、选择、关注、窗口和显示偏好 |
| [短期速率历史](docs/stage3e-rate-history.md) | 有界历史、曲线及未知区间 |
| [会话累计记录](docs/stage3b-integration-2026-09-17.md) | 累计语义、进程身份与集成边界 |

## 许可与分发

仓库当前没有项目顶层 `LICENSE` 文件，第三方组件说明不等于对项目源码授予开源许可证。包内包含 `THIRD-PARTY-NOTICES.txt` 和 `licenses/`；来源记录见 [第三方说明](packaging/THIRD-PARTY-NOTICES.txt)。

本版公开测试包保留第三方许可证、版权和实际来源；Qt/PySide/shiboken 采用 LGPLv3，匹配源码随 Release 提供，外部 DLL 与 Python 包装层可替换，详见[分发与替换说明](packaging/licenses/REDISTRIBUTION.txt)。Microsoft 运行库保留其单独条款。发布本项目二进制不等于为项目源码新增开源许可证。
