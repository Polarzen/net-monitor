# Stage 5：Windows x64 内部测试包

日期：2026-10-10（Asia/Hong_Kong）。目标平台 Windows 11 x64；构建和桌面验证均在当前 Windows 11 x64 开发机进行。

**构建成功，最终 ZIP 解压后的 EXE 已实际运行，可作为带明确限制的内部试用包。打包版真实 ETW、管理员重启及部分桌面交互尚未完成验收，不是稳定版或正式发布。** 本轮未重做 Stage 4 全套采集／性能实验，也未将其历史结果改写为打包版通过。

## 交付产物与来源

| 项目 | 实际值 |
| --- | --- |
| 版本 | `0.2.1.dev1`，PE 数字版本 `0.2.1.1`，预发布标志 |
| 形式 | PyInstaller `onedir/windowed`，未签名，无 UPX |
| 最终产物源码提交 | `56f049bf32a570d4e6aa16a6d94471a1df607a25` |
| ZIP 字节数 | `38,756,980`（约 36.96 MiB） |
| 完整发行目录 | `98,869,116` 字节（约 94.29 MiB），303 个文件 |
| ZIP SHA-256 | `8304662d2fa61da592fb99729911f3fa9949723e791d3b75f237f6f63d0a9362` |
| 构建时间 | `2026-10-10T07:21:53.349196+00:00` |

本地 ZIP：

```text
D:\code\net-monitor\artifacts\stage5\NetMonitor-0.2.1.dev1-windows-x64-56f049bf32a5-test\NetMonitor-0.2.1.dev1-windows-x64-56f049bf32a5-test.zip
```

同目录提供 `SHA256SUMS.txt`、`build-result.json`、`static-inspection.json` 和原始 `build.log`。最终 ZIP 在解压验证及退出后重新计算 SHA-256，结果一致。早期失败／中间版本的输出保留作诊断，**本地桌面已实测的交付对象为上述 ZIP**。

2026-10-10 17:42（香港时间）补充：Stage 5 分支已推送，三项 CI 作业均成功，并生成 [Actions 内部测试包 artifact](https://github.com/Polarzen/net-monitor/actions/runs/38042146780/artifacts/11665468996)。该 artifact 是 `e0eafaa` 的独立 CI 构建，和上表本地实测包的字节、源码提交记录不同；具体校验与验收边界见下文“远端交付补验”。

包内结构：

```text
NetMonitor/
  NetMonitor.exe
  _internal/
  BUILD-INFO.json
  FILE-MANIFEST.json
  使用说明.txt
  THIRD-PARTY-NOTICES.txt
  licenses/
```

`BUILD-INFO.json` 记录完整源码提交、189 个相关输入的 SHA-256、配置和锁文件身份、平台及依赖。文件清单记录 302 个文件并排除自身；外部 ZIP 校验覆盖整个归档。后续验收文档提交没有打入这个 EXE。SHA-256 不证明发布者身份。

## 复现构建

使用原生 **CPython 3.14.7 x64**。本次保留已有 `.venv`，专门创建 `.venv-build-stage5`；没有升级主项目环境。下列命令适用于本仓库当前已有的 `.venv`：

```powershell
Set-Location D:\code\net-monitor
& .\.venv\Scripts\python.exe -c "import platform,struct; assert platform.python_version() == '3.14.7' and struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64','x86_64')"
if ($LASTEXITCODE -ne 0) { throw 'Requires CPython 3.14.7 x64' }
if (!(Test-Path -LiteralPath .\.venv-build-stage5)) {
    & .\.venv\Scripts\python.exe -m venv .venv-build-stage5
    if ($LASTEXITCODE -ne 0) { throw 'Build venv creation failed' }
}
& .\.venv-build-stage5\Scripts\python.exe -m pip install --require-hashes -r .\packaging\requirements-windows-x64.lock
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed' }
& .\tools\build_windows.ps1
```

新机器可用已安装的 CPython 3.14.7 x64 解释器替代前两处 `.venv\Scripts\python.exe`，其余步骤不变。版本与架构不匹配时构建脚本拒绝继续。此流程固定依赖和步骤，不承诺逐字节可重现。

构建要求相关输入已提交；允许存在不参与构建的原有暂存文档。每次输出按当前完整 HEAD 的短 SHA 命名，**不会覆盖已有输出**。本机已有本次产物，再构建同一提交时使用新的输出根目录，例如：

```powershell
& .\tools\build_windows.ps1 -OutputRoot D:\code\net-monitor\artifacts\stage5\rebuild-1
```

复现本包的源码应使用提交 `56f049bf32a570d4e6aa16a6d94471a1df607a25` 的独立干净检出；不要重置当前含用户暂存内容的工作区。在后续文档提交上构建会记录新的 HEAD，不能把新包称为上述原始 ZIP。

实际锁定版本：

| 组件 | 版本 |
| --- | --- |
| Python | 3.14.7 x64 |
| PyInstaller / hooks-contrib | 6.22.3 / 2026.8 |
| PySide6、Essentials、Addons、shiboken6 | 6.11.2 |
| psutil | 7.2.2 |
| setuptools / packaging | 84.0.0 / 26.3 |
| pefile / altgraph / pywin32-ctypes | 2024.8.26 / 0.17.5 / 0.2.3 |

直接和传递依赖均在锁文件中固定版本及 wheel SHA-256；虚拟环境自带 pip 为 26.2.1。兼容与运行规则依据 [PyInstaller 6.22.3 更新记录](https://pyinstaller.org/en/v6.22.3/CHANGES.html)、[重启和 windowed 模式说明](https://pyinstaller.org/en/v6.22.3/common-issues-and-pitfalls.html)、[运行时路径说明](https://pyinstaller.org/en/v6.22.3/runtime-information.html)、[PySide6 6.11.2 元数据](https://pypi.org/project/PySide6/6.11.2/) 及 [Qt 官方部署文档](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)。

## 实现边界

- `packaging/entry.py` 只调用正式 `net_monitor.app.main`；spec 使用官方 Qt 依赖分析、GUI bootloader、默认 `asInvoker` 和 PE 版本资源。
- `src/net_monitor/__init__.py` 是版本权威；包元数据动态读取版本，QApplication 设置相同运行时版本。
- `elevation.py` 保留源码 `pythonw.exe -m net_monitor` 路径；frozen 模式使用当前 EXE 的绝对路径及其父目录，不复制任意参数。独立重启临时设置 `PYINSTALLER_RESET_ENVIRONMENT=1` 并恢复环境。原生失败／取消保留当前实例；ShellExecute 成功不等于新实例采集成功。
- 配置仍为 `%LOCALAPPDATA%\NetMonitor\ui.json`，无需迁移到 EXE 或 `_internal`；未增加流量持久化。没有新增错误日志；保留 PyInstaller windowed 启动异常对话框，标准流为 `None` 的入口行为已有回归测试。
- 构建子进程限制 DLL 搜索 PATH，并拒绝来自构建虚拟环境、Python 基础目录和 Windows 之外的二进制。只在 Qt 分析时排除经确认未使用的 PDF 图像插件和 QML 虚拟键盘插件；没有事后删除 DLL。Windows 平台、SVG／ICO／JPEG 等插件保留。
- 相对 Stage 4 起点，产品源码只改 `__init__.py`、`app.py`、`core/elevation.py`。Collector、服务、SamplingWorker、ETW／TDH／Session Tracker 和采集语义均未改变；没有新增产品线程、timer、辅助进程或遥测。

## 实际问题与修复

1. 首包 `c620a9751aa4` 构建成功，但真实 EXE 报 `DLL load failed while importing QtWidgets`。DLL 分析继承宿主 SDK 路径，误收同名但不兼容的 ICU DLL；Qt 所需的 20 个符号在该 DLL 中缺失，而系统 ICU 中齐全。修复为构建子进程的受限 PATH 和二进制来源检查。失败截图与诊断保留，不能把首次构建称为启动通过。
2. PATH 修复的中间回归暴露 `SystemRoot` 大小写：Windows 环境转普通字典后键名归一化。修正为兼容 `SYSTEMROOT`，对应测试随后通过。
3. `7b9945c0424c` 包已实际启动；最终 `56f049bf32a5` 再排除未用插件并补齐 OpenSSL／libffi 许可来源后重新构建、解压并操作。最终 ZIP 是本节最后一次构建，不是早期包改名。

完整构建日志见 [build.log](evidence/stage5/build.log)，静态报告见 [static-inspection.json](evidence/stage5/static-inspection.json)。[build-warnings.txt](evidence/stage5/build-warnings.txt) 保留静态扫描的 Unix／Java 可选模块及 `collections.abc` 等提示；最终真实入口已运行并打开 Detailed，当前已执行路径未出现这些模块的运行时导入错误。未运行路径仍不以此声称完整覆盖。

## 源码回归

本轮最终完整测试：**331 passed，1 skipped，13.77 秒**，在最终实现提交前执行。命令为 `.venv\Scripts\python.exe -m pytest -q -ra -p no:cacheprovider`；子进程环境设置 `QT_QPA_PLATFORM=offscreen`，并复用已校验的临时 Noto CJK 测试字体。

唯一跳过为 `tests/test_stage3a_ui.py:271` 的真实托盘条件测试：离屏 runner 没有真实系统托盘。测试字体没有打包。首次完整运行由于未配置既有布局测试所需字体为 `1 failed, 328 passed, 1 skipped`；配置字体后为 `329 passed, 1 skipped`。中间构建环境用例的真实失败及修复也保留在 [source-tests.json](evidence/stage5/source-tests.json)，没有删除或弱化测试。

新增覆盖源码／frozen 提权参数、中文和空格路径、取消与启动失败返回值、环境恢复、空标准流、配置缺失／损坏默认值及包资源隔离、单一版本来源、薄入口、构建 PATH 和 Qt 插件选择。原有控制器失败不退出、采集、累计、隐藏刷新和窗口生命周期随完整测试执行。源码自动测试不等于最终 EXE 的 UAC、真实桌面或 ETW 验收。

## 最终 EXE 验收

证据均来自实际 ZIP 解压的 EXE。没有以源码启动、fake snapshot 或内部 `show/hide` 调用冒充鼠标操作。Computer Use 使用本机 `@oai/sky`。

| 项目 | 结果与边界 |
| --- | --- |
| x64／GUI／普通启动 | 通过静态检查：Machine `0x8664`、Subsystem `2`、`asInvoker`、`uiAccess=false`；实际 `NotSigned`。没有强制管理员 manifest。 |
| 依赖与版本 | 必要 Python／Qt／qwindows 齐全；运行模块路径来自解压目录；版本字符串一致。目录没有测试字体、源码验收工具、用户配置或构建环境。 |
| 中文、空格、不同 cwd | 最终包解压在 `%TEMP%\Net Monitor 最终测试 56f049bf32a5\NetMonitor`，cwd 为同级 `工作 目录`；实际启动成功。测试子进程移除 Python／Qt 开发覆盖，没有改全局环境。 |
| 不可写发行目录 | 仅对自有临时解压目录临时拒绝写入，探针得到 `PermissionError`；EXE 仍成功运行并保存配置到隔离 `LOCALAPPDATA`。退出后恢复原 ACL，SDDL 与保存值一致。 |
| Compact／权限界面 | 最终 PID `7128`，create_time `1791617078.98634`；真实截图中文、按钮和状态可读，权限不足显示 `—`，没有伪零。使用种子 Compact 偏好测试模式恢复，不声称已鼠标切换 Micro。 |
| Detailed／主窗口生命周期 | Computer Use 打开 Detailed、切到本次累计页，再关闭 Detailed；Compact 继续运行。空累计页只是权限不足状态，不是流量功能通过。 |
| 拖动／配置保存 | Computer Use 拖动 Compact 后，经窗口菜单“退出”，PID 消失。配置在用户目录保存 `compact_position=[55,48]` 及 mode；未写发行目录。没有用小窗口截图推断精确屏幕坐标。 |
| 整目录迁移／再次启动 | 原 ACL 恢复后移至 `迁移后的 NetMonitor`，最终 PID `51080`，create_time `1791618014.4086685`；实际恢复 Compact，再次经程序窗口菜单退出，PID 消失。两次均是程序菜单退出，**不是托盘点击退出**。302 个清单文件保持原哈希。 |
| 默认 Micro | 中间同配置包 `7b9945c` 从缺失配置启动，进程及包内模块正常；Computer Use 未列出 Micro。仅对精确 PID／create_time 强制清理，不能记为正常退出。最终包 Micro 视觉／Card 未验证，未重复工具初始化循环。 |
| 配置缺失／损坏回退 | 源码自动测试通过；最终 EXE 的损坏配置视觉回退未执行。 |
| 管理员重启 | 对 `7b9945c` 的真实 Compact 点击已有管理员按钮；用户最终反馈“没有看到提示”。旧实例仍运行，无成功新实例证据。不再重复 UAC。最终包沿用相同提权源码，但实际成功／取消 UAC 均未验证。 |
| 真实 ETW 与连续性 | 打包版未验证：提权受阻，未建立有代表性的真实负载。隐藏采集、停流回落、累计保留和自有 ETW 会话退出清理也不能记为通过。Stage 4 实测仍只对应其原源码版本。 |
| Micro/Card／选择与关注 | 当前工具定位不到 Micro，未验证悬停、保持、焦点、选择应用、关注与取消、对象不被抢走。没有因此修改窗口标志。 |
| 托盘恢复／点击退出 | 未验证，未以程序菜单退出或托盘对象存在代替。 |
| 干净 Windows 机器 | 未执行。当前为开发机隔离目录验证，没有卸载 Python、破坏 PATH 或启用虚拟化。 |

进程路径、PID、时间、模块及配置记录：[final-launch.json](evidence/stage5/final-launch.json)、[final-lifecycle.json](evidence/stage5/final-lifecycle.json)。截图：[最终 Compact](evidence/stage5/final-compact.png)、[空累计页](evidence/stage5/final-detailed-empty-account.png)、[迁移后 Compact](evidence/stage5/final-relocated-compact.png)。截图只保存目标窗口必要内容，没有提交详细进程列表或无关窗口。

提交的文本证据把用户主目录前缀替换为 `%USERPROFILE%`，其余路径、PID、时间和结果保留。原始文件只留在忽略的本地产物目录 `acceptance-raw/`；原文与分享版本的哈希见 [evidence-redactions.json](evidence/stage5/evidence-redactions.json)。提交前重新核对 BUILD-INFO 中 189 个输入哈希均与当前文件一致，见 [final-verification.json](evidence/stage5/final-verification.json)。

最终首次运行的单次工作集观察为 `98,967,552` 字节、14 线程，仅用于进程身份与运行记录；它不是受控负载性能测量、长期泄漏测试或跨版本比较。

## 组件声明与发布限制

包内提供实际组件及锁定版本的许可文本、wheel 原文、上游来源和 SHA-256。131 个上游许可／归属文件逐一匹配哈希；Qt 归属记录是保守的上游超集，不表示每个列出的子组件均被编入。CPython、PySide/Qt、psutil、PyInstaller bootloader、OpenSSL 3.5.7、libffi 3.4.4 的来源均记录在 `licenses/` 和第三方说明中。

仓库没有项目 LICENSE，没有擅自替用户代码选许可证。Microsoft 运行库再分发条件及 Qt/PySide 等完整再分发义务尚未完成发行审查；当前不能宣称公开发布已获许可。未签名、未做干净机器测试、UAC／ETW 与关键交互未验证等限制随说明明确保留。没有指导关闭 Defender、SmartScreen 或 UAC。

## Git 与 CI

起点为 `feat/stage-4-lean-core` 的 `ef612a9b35f3c74bf62e89ff012d759cb5826623`；当前分支 `feat/stage-5-windows-package`。实现记录：

- `c620a9751aa43f372b63a1c9a1af2e4968441b72`：打包流程、适配与回归；首包实际启动失败保留。
- `3cbc4f1`：限制构建 DLL 搜索；中间键名失败保留。
- `7b9945c0424cc2717204b2ab487f12a2ed44ec08`：修正环境键名，实际可运行中间包。
- `56f049bf32a570d4e6aa16a6d94471a1df607a25`：最终插件范围及组件说明，**本 ZIP 对应提交**。
- 本文及验收证据在之后的独立文档提交中保存；其提交号以 Git 日志及交付报告为准。

新增 x64 Actions 作业使用同一锁文件、spec 和 PowerShell 入口，上传 14 天内部测试 artifact；原 Windows x64／ARM64 回归矩阵保留。没有创建 Release、标签或合并 main。

**首次交付时推送失败，Stage 5 CI 未触发；此阻塞已在下述远端交付补验中解除。** 当时出现 schannel TLS 握手失败；后续到达 GitHub 后被明确拒绝：

```text
refusing to allow an OAuth App to create or update workflow `.github/workflows/ci.yml` without `workflow` scope
```

首次交付收尾的只读远端查询再次遇到 TLS 握手失败，当时无法进一步确认远端引用。没有绕过权限、更换认证或删掉所要求的工作流来强行推送；本地源码、提交和 ZIP 保留。此段为历史失败记录。

### 远端交付补验（2026-10-10）

用户确认连接已修复后，原有五个 Stage 5 提交成功推送至 `origin/feat/stage-5-windows-package`，远端 HEAD 核对为 `e0eafaa3200910fd5ae47eeff343401276fa1e8f`。没有重做实现或本地桌面验收，没有把 ZIP、EXE 或原有无关暂存内容纳入 Git。

[CI 38042146780](https://github.com/Polarzen/net-monitor/actions/runs/38042146780) 已完成，最终结论为 **success**：

| 作业 | 实际结果 |
| --- | --- |
| Windows x64 internal test package | 构建、静态检查和 artifact 上传成功 |
| Full validation windows-2025 | 331 passed、1 skipped，8.02 秒 |
| Full validation windows-11-arm | 331 passed、1 skipped，17.56 秒 |

两平台的跳过项均为离屏 runner 没有真实系统托盘。这里的源码回归和打包静态检查不等于打包程序的原生 UAC 或真实 ETW 验收。

已下载 [Actions artifact 11665468996](https://github.com/Polarzen/net-monitor/actions/runs/38042146780/artifacts/11665468996)，核对其内部 ZIP 的 CRC、外部 `SHA256SUMS.txt`、302 个文件哈希、PE 架构、GUI 子系统和源码身份。该包未另行执行真实桌面操作，不将本地旧包的实测结论直接套用为该 CI 二进制的完整验收。

GitHub 当前记录的 artifact 到期时间为 2026-10-24 17:40（香港时间）；本地下载副本保留在下述路径。GitHub artifact 容器的 digest 与其中产品 ZIP 的 SHA-256 是不同对象。

| CI 产物 | 实际值 |
| --- | --- |
| 源码提交 | `e0eafaa3200910fd5ae47eeff343401276fa1e8f` |
| ZIP 字节数 | `38,757,174` |
| 完整目录字节数／文件数 | `98,869,201`／303 |
| ZIP SHA-256 | `a5cdc3566e29b24498e08f3e08809af67d69861f07e3e4c8abb42447acdd89d3` |
| 构建环境 | Windows Server 2025 x64，沿用锁定构建依赖 |

已下载的 CI ZIP：

```text
D:\code\net-monitor\artifacts\stage5\actions-38042146780\NetMonitor-0.2.1.dev1-windows-x64-e0eafaa32009-test\NetMonitor-0.2.1.dev1-windows-x64-e0eafaa32009-test.zip
```

本地已实测包仍为上文 `56f049b` 的 ZIP，未替换或重建。核对 `56f049b..e0eafaa` 的产品源码、packaging、pyproject 和构建脚本差异为空。当前补充只更新文档及 [remote-delivery.json](evidence/stage5/remote-delivery.json)，使用 `[skip ci]` 避免为交付记录重复执行相同代码的测试；本节 CI 结论始终绑定 `e0eafaa`。

推送与 artifact 缺失已解决；打包版管理员重启、真实 ETW、Micro/Card／托盘交互及干净机器验证仍保留原有未完成状态。连接修复没有证明这些桌面与采集项目通过。

原有暂存 `docs/stage4-lean-core.md` 的 blob 始终为 `e05e54120fee12ef6abe8bbcde81c5ba5b4a0045`；未跟踪 `goal.md` SHA-256 为 `3c406e89c9f3a815d59715eb595111732f649d72f6260ee14bed507a05a87cef`。只按明确路径提交本轮文件，不纳入这些内容。ZIP、EXE、构建虚拟环境和缓存没有提交。

路由环境的活动 provider 与 manifest 哈希不一致，按 V2.4 admission 拒绝创建子代理；没有修改全局 provider 或静默换角色。本轮在已有授权范围内由主代理完成。

本轮可交付有明确限制的内部试用包；已发现的启动 DLL 问题已修复并在最终产物复验。实际 UAC／真实采集等未知项仍需在具备条件的环境验证，当前不作完整验收或稳定发布结论。
