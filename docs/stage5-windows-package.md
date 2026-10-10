# Stage 5：Windows x64 内部测试包

> 最新公开版本：[0.2.1.dev3 发布记录](releases/0.2.1.dev3.md)。下载、源码/标签、已运行 ZIP、组件材料和本轮验证集中在该记录；已发布产物不会随文档 CI 更换。

以下按阶段保留 dev1/dev2 历史结果，各自“通过”仅适用于明确的源码／哈希。旧 `82ba3a1` 是运行确认未完成的修复候选；旧 `2b6db24` 有已知 PID 归属缺陷，两者均不再是默认下载入口。

## 初始 dev1 打包记录（历史）

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


## CI 包真实运行补验（2026-10-10）

本轮唯一验收对象为上节 `e0eafaa3200910fd5ae47eeff343401276fa1e8f` 的 CI 产品 ZIP，版本 `0.2.1.dev1`，38,757,174 字节，SHA-256 `a5cdc3566e29b24498e08f3e08809af67d69861f07e3e4c8abb42447acdd89d3`。重新核对哈希，完整解压到 `%TEMP%\NetMonitor-CI-e0eafaa-runtime-20261010\NetMonitor`，302 个清单文件校验通过。EXE SHA-256 为 `023411e31a026a50309823ac4af1907e398a9505495f7f7b22099a5e010b547b`。没有更换包、修改 `_internal` 或重建。

运行时间为香港时间 19:00 起；详细 UTC 时间、路径、PID/create_time 和普通启动权限记录见 [package-launch.json](evidence/stage5/packaged-runtime/package-launch.json)，各项结果见 [runtime-results.json](evidence/stage5/packaged-runtime/runtime-results.json)。包内 BUILD-INFO 的摘要和文件哈希随证据保存，文档 HEAD 不作为 EXE 源码提交。

### 启动、提权与交互边界

- 普通 EXE PID `61952`，create_time `1791630012.8958185`，令牌确认未提权；从独立 cwd 启动，使用隔离 LOCALAPPDATA 预置 Compact。普通窗口正确显示需要管理员权限及 `—`，不是零流量。预置模式不记为鼠标切换。
- 首次桌面操作因物理 Esc 中断。用户随后明确确认：**点击了应用内“以管理员身份重启”并接受 UAC**。同一发行目录出现 PID `56508`、create_time `1791630179.940374`；只读 TokenElevation 查询为 true，原 PID 已退出。内部重启通过的依据是用户操作报告加上进程身份／权限核验；不是代理亲自完成按钮和原生 UAC。生产 UI 不公开 ShellExecute 原生返回值，该值未取得。
- 新管理员实例实际采集到了下述受控流量。Windows 直接“以管理员身份运行”没有必要再做，也未测试；原生取消未执行，仍只有已有源码自动测试证据。
- 管理员实例恢复的 Micro 未出现在 Computer Use 窗口／应用列表；用户协助切到 Compact 后可截图。管理员窗口仅公开外框／标题栏，工具点击“详细信息”和“窗口”菜单均未产生预期变化。疑似 Windows 交互权限边界，当前证据不足以定为产品缺陷；没有反复点击、改窗口标志或绕过权限。
- 用户协助打开 Detailed、切到累计页；其数据由工具读取真实截图。普通实例补验 PID `57732`、create_time `1791631387.039096` 可以由工具打开 Detailed，再关闭它且保留 Compact，最后从窗口菜单退出。普通权限下的可操作结果不代替管理员窗口交互通过。
- 提权后配置似乎来自普通用户目录，而非测试进程的隔离 LOCALAPPDATA。结束后将该用户配置的模式恢复为事先读取的 `micro`，保留其他字段；普通补验仍使用隔离配置。

### 真实回环负载

外部临时负载只复用 `tools/measure_stage4_live.py` 的 `receive_exact` 和 UTC 时间函数，未运行其源码观察器、collector probe 或测量主程序；选定 CI EXE 是唯一采集验收对象。客户端为 Python，服务端为 Pythonw，使用两个不同的程序分组，传输可丢弃 S/R 字节，地址仅 `127.0.0.1`。最多 240 帧，每帧客户端上传 65,536 B、下载 131,072 B，约每秒一帧；初始等待上限 120 秒，结束后存活空闲上限 180 秒。它不是外网带宽实验。

客户端 PID `63912`、create_time `1791630734.7280102`；服务端 PID `47048`、create_time `1791630735.1903183`。身份由负载自身记录，GUI 两个应用组各显示 1 个进程。受工具权限限制，没有在 GUI 展开 PID 子项并核对 create_time，不能把应用组观察宣称为已完成 PID 子项验收。

本轮实际传输 204 帧，UTC 11:13:01.926 开始，11:16:26.164 停流，之后进程继续存活约 180 秒，11:19:26 正常结束。记录见 [client-load.jsonl](evidence/stage5/packaged-runtime/client-load.jsonl) 和 [server-load.jsonl](evidence/stage5/packaged-runtime/server-load.jsonl)。

| 观察阶段 | 客户端下载／上传 | 服务端下载／上传 | 范围 |
| --- | --- | --- | --- |
| 活跃 Detailed | 127.62／63.81 KB/s；累计 19,398,656／9,699,328 B | 63.81／127.62 KB/s；累计 9,699,328／19,398,656 B | 界面真实应用组；方向相反、速率有效、累计随后增长 |
| 停流后 11:17:33 UTC | 26,738,688／13,369,344 B | 13,369,344／26,738,688 B | 两组进程数均 1，显示“最近枚举有进程” |
| 负载退出后 11:21:12 UTC | 26,738,688／13,369,344 B | 13,369,344／26,738,688 B | 两组进程数均 0，显示“未运行”，账户仍保留 |

界面最终累计恰与本轮负载有效载荷记录一致；这不是 ETW 对任意协议、网卡或网络逐字节相等的保证。空闲观察和退出后观察之间累计未变。只取得一次进程仍活着的空闲累计截图；后续外部 psutil 检查时负载已按上限退出，记录了 NoSuchProcess，不能补写为第二次空闲存活核验。实时页当时仅显示联网应用，工具无法取消筛选，因此没有观察到目标行的明确 `0 B/s`；不能由列表消失或累计稳定推断零速率通过。

### 本轮结果与剩余项目

| 项目 | 结论 |
| --- | --- |
| CI ZIP 的真实 EXE 启动 | 通过；源码／哈希／路径绑定到 `e0eafaa` CI 包 |
| 应用内管理员重启 | 通过，用户实际操作按钮与 UAC；旧实例退出、同目录新实例实际提权并采集 |
| 真实 ETW、方向、速率、累计增长 | 通过本机回环应用组级观察；未用源码或历史 Stage 4 代替 |
| 空闲累计、退出账户 | 观察到空闲到退出后累计不变、账户保留；缺少两次独立空闲采样 |
| 显式零速率／PID 子项 | 受管理员窗口交互限制，未验证 |
| 正常应用退出 | 用户从 **窗口菜单** 退出管理员实例，PID `56508` 消失；代理从窗口菜单退出普通补验，PID `57732` 消失；均不是托盘点击退出 |
| 自有 ETW 会话清理 | 未验证。生产会话使用随机 UUID，现有 UI 未公开本实例会话名，未枚举／停止其他会话，也未将进程结束直接视为会话清理成功 |
| 再次启动采集 | 普通 EXE 再启动通过；再次提权与采集未执行 |
| 原生取消 | 未执行；只有相应 CI 源码测试，不能当作真实用户取消 |
| 隐藏期间采集／恢复当前数据及历史 | 受管理员窗口交互限制，未验证 |
| Micro/Card 悬停、保持、Esc、拖动、焦点 | Micro 无法定位，现有 sky API 也没有 hover；未验证 |
| 选择、固定／取消关注、对象不被抢走 | 工具受阻，未验证 |
| 托盘恢复及托盘点击退出 | 未验证；没有用窗口菜单退出替代 |

没有复现需要修改产品的缺陷，本轮未改产品源码、测试或构建输入，不递增版本、不重打包。沿用 `e0eafaa` 的 CI：Windows x64 与 ARM64 各 331 passed、1 skipped（离屏 runner 无真实托盘），未重复完整回归。桌面阻塞明确保留，结论仅为 **CI 内部试用包已验证启动、应用内提权及上述回环采集范围**，不是完整验收或稳定发布。

普通 Compact 截图与必要文本在本证据目录。活动与累计原始截图包含无关应用名／路径，只留在 Git 忽略的本地 `artifacts/stage5/packaged-runtime-raw/`，不提交完整个人进程清单；公开 JSON 只转录本轮负载行的原始数值，并保留原始截图 SHA-256。共享文本的用户目录前缀替换为 `%USERPROFILE%`。所有临时负载和本轮 EXE 已结束，没有强制结束或修改其他 ETW 会话。

本次只提交 README、本文及 `docs/evidence/stage5/packaged-runtime/` 的已审阅证据，使用 `[skip ci]`。保留原有 Stage 4 暂存 blob 与未跟踪 `goal.md`，不提交 ZIP／EXE，不合并 main、不发布 Release。


## 内部试用与问题闭环（2026-10-10）

本轮从原 `e0eafaa` CI 包做一次日常使用流程，未重复已通过的打包、提权和完整回环累计验收。起始 HEAD 为 `82e13a1d4360743caee55dd86cc38bbb7caa70be`，没有可复用实例；普通实例使用隔离 Compact 偏好，明确属于测试初始化。运行中发现以下可复现问题，才按约定修复并递增开发版。

### 实际问题与最小修复

普通权限、默认 380 逻辑像素宽的 Compact 中，“需要管理员权限才能读取按进程网络流量”尾部被裁切。最大化后可完整显示，恢复默认尺寸后再次裁切。权限状态和重启按钮仍可读，没有把这个显示问题写成采集或提权失败。[原包截图](evidence/stage5/internal-trial/compact-permission-before.png)来自实际 EXE。

原因是权限说明与按钮同处横向布局，QLabel 没有换行。在固定中文测试字体下，文字单行需要 234 px，而默认宽度只分配 202 px，最小 340 宽度只分配 162 px。修复只在这一个现有 QLabel 上启用 word wrap；未改 Collector、MonitorService、SamplingWorker、ETW、累计、窗口标志或权限策略。

实现提交 `2b6db24173a17532e3371d7e14406247d72e380e`，版本递增到 `0.2.1.dev2`，同步包内版本说明。新增几何回归检查文字边界完全位于可用区域、重启按钮可用且不与文字重叠。两个宽度用例修复前均失败，修复后通过。

- 本地针对性回归：34 passed、1 skipped。
- 本地完整回归：333 passed、1 skipped，12.17 秒。
- [CI 38051119145](https://github.com/Polarzen/net-monitor/actions/runs/38051119145)：打包、x64、ARM64 三项作业成功；两平台各 333 passed、1 skipped，分别 11.38／17.33 秒。
- 跳过项均是离屏环境无真实托盘；没有删除、弱化测试或增加 skip。日志见 [internal-trial](evidence/stage5/internal-trial/)。

### 新包身份与实际复验

使用现有 Actions 锁定依赖和构建脚本重新构建；没有再制造一个不同的本地构建。原 `0.2.1.dev1` ZIP 保留。实际复验的是新 [Actions artifact 11668988603](https://github.com/Polarzen/net-monitor/actions/runs/38051119145/artifacts/11668988603) 内的产品 ZIP，下载后校验外部 SHA256SUMS、CRC 和 302 个清单文件，再运行完整解压目录的 EXE。

| 字段 | 本轮最终对象 |
| --- | --- |
| 版本／源码提交 | `0.2.1.dev2`／`2b6db24173a17532e3371d7e14406247d72e380e` |
| ZIP 字节数 | `38,757,752` |
| ZIP SHA-256 | `b63547f20e0f09418cdd1194d93be05650ec92c3ef53c6f46c8f634e5c27e795` |
| EXE SHA-256 | `97211256d60947eb556b2b26544acdcd4a034fc46a121b0ee0f30fab555f092e` |
| 实际 EXE | `%TEMP%\NetMonitor-CI-2b6db24-trial-20261010\NetMonitor\NetMonitor.exe` |
| Artifact 到期 | 2026-10-24 20:13（香港时间）；本地副本保留 |

```text
D:\code\net-monitor\artifacts\stage5\actions-38051119145\NetMonitor-0.2.1.dev2-windows-x64-2b6db24173a1-test\NetMonitor-0.2.1.dev2-windows-x64-2b6db24173a1-test.zip
```

新包普通 PID `59068`，create_time `1791634991.753301`。默认 Compact 已显示完整的两行权限说明，[修复后截图](evidence/stage5/internal-trial/compact-permission-after.png)与原包对应同一失败场景；按钮仍可用。工具实际打开 Detailed 并关闭返回主窗口，权限不足与 `—` 易于区分。一次无截图的关闭请求遇到工具 geometry unavailable，刷新截图后关闭成功，不作为产品故障。

为继续这次实际使用，工具点击一次管理员入口，用户接受 UAC。新 PID `61092`、create_time `1791635146.3442104`，确认属于新发行目录且 TokenElevation 为 true；普通 PID 已退出。这里的提权是流程准备，不重跑原生取消或多次 UAC。管理员窗口的历史输入限制没有新的能力变化，因此没有重复无效点击，也没有让用户代做整套检查。

### 活动到空闲及使用边界

原有临时回环 helper 原样复用，只运行一次短负载，没有新建测速框架。客户端 PID `58964`、create_time `1791635305.7215047`；服务端 PID `51856`、create_time `1791635306.0618584`。流量仅 `127.0.0.1` 和可丢弃字节，程序上限仍为 240 帧／约 240 秒；本次实际 44 帧、约 44 秒，客户端发送 2,883,584 B、接收 5,767,168 B。

UTC 12:28:49.868，实际新 EXE 的 Compact 显示客户端约下载 127.44 KB/s、上传 63.72 KB/s，服务端相反。停流后分别在 12:29:37.740 和 12:30:10.351 核对负载 PID、create_time、EXE 和存活状态，并紧接着观察界面；两次都还活着，两组均已离开活跃 Top 5。

这只是活动到空闲的实际使用观察。**列表消失不等于已取得明确 `0 B/s`，两次存活观察也不等于两次零速率或累计采样。** 当前没有通过工具展开管理员实例的 PID 子项、固定／取消关注、隐藏后托盘恢复或查看卡片历史。本轮没有为这些已知限制重试输入、提升工具宿主、修改安全设置或改窗口类型。

负载通过正常结束信号退出，精确身份对应的客户端、服务端及 launcher 均已消失。用户确认从新包的“窗口 → 退出”正常结束，随后核对 PID `61092`／create_time 对应实例已消失；这是窗口菜单退出，不是托盘退出。所有本轮实例和负载均已结束，未强制清理；未以进程消失替代 ETW 会话清理。生产 UI 没有公开本实例会话名，未枚举／停止其他会话；原生取消、退出后再次提权采集及干净机器也未执行。

### 配置、证据及结论

本轮普通实例使用隔离 LOCALAPPDATA。正常用户偏好起始为 Micro，但其后出现了本轮工具没有写入的模式／位置变化；保留最新字段，没有用旧备份整文件覆盖。管理员实例使用这些当前用户偏好。本轮没有直接修改正常 `ui.json`。

[trial-results.json](evidence/stage5/internal-trial/trial-results.json)集中记录包切换、缺陷、修复、CI、新包身份和流程结果。只有不含无关应用的修复前后截图进入 Git；活动截图、原始偏好和临时负载留在忽略目录 `artifacts/stage5/internal-trial-raw/`，公开记录只保留必要数值和负载身份，用户目录前缀替换为 `%USERPROFILE%`。

结论限定为：新 `0.2.1.dev2` CI 内部包的提示裁切已修复并在实际 EXE 复验，适合继续进行同范围内部试用。本次已执行范围内未复现其他新的产品缺陷；工具受限项保留。旧 `0.2.1.dev1` 的累计精度／账户保留等证据不自动继承给新二进制。新代码已执行完整 CI，之后纯文档／证据提交可使用 `[skip ci]`；原有 Stage 4 暂存和 `goal.md` 保留，二进制不进 Git，不合并 main、不创建 Release。

## 主分支整合期间的身份归属修复

2026-10-10，[整合 PR #1](https://github.com/Polarzen/net-monitor/pull/1) 的自动审查指出进程枚举缓存与 PID 复用之间的归属缺口。独立模拟复现：旧应用已发送 100 B，新应用在两秒枚举间隔内复用同一 PID 并发送 50 B，旧实现会将旧账户累计记为 150 B，刷新身份后也不纠正。该复现只向真实采集器和服务注入受控身份／事件，没有启动真实 ETW、桌面、UAC 或回环负载。

用户随后明确授权扩大本轮范围，先修复再重新验证。修复限于 `WindowsProcessNetworkCollector`：在取得计数快照后，使用新的进程句柄核对创建时间；退出交接也在原子移除计数后核验。身份变化、退出或不可访问时，当前值显示未知，旧账户仅保留最后确认的累计。暂时无法核验后恢复同一身份时，重新建立计数基线，排除不确定区间，同时延续已确认累计。无法归属的尾部或间隔字节可能少计，不把它们猜测归给旧进程。ETW 生命周期、TDH、采样频率、两秒进程枚举周期和速率窗口未改。

新增 10 项回归在修复前全部失败，修复后连同采集器、服务及会话累计的针对性回归共 48 项通过。旧模拟测试显式注入可信身份验证器，原有业务断言保持不变。合并仍以修复后实际候选的 Windows x64／ARM64 完整回归和 x64 构建／静态检查为条件；最终候选、合并 SHA、CI 结果和新 ZIP 哈希记录在 PR，不提前声明 main 已通过。

版本按本轮约定保留 `0.2.1.dev2`，不同构建由完整源码 SHA 和独立 ZIP 哈希区分。原已实测 `2b6db24` 包不包含这次修复；该整合轮次当时保留了原入口和原证据，并披露其 PID 复用已知问题，修复包不能继承旧 dev1／dev2 的运行证据。当前入口已由下一节调整为修复候选，旧包转为历史对照。该整合轮次未创建 Release，也未重做桌面或性能验收。

## PID 修复包定向确认与入口调整（2026-10-10）

**决策：保留修复候选，不宣称已完成有限运行确认。** 本轮按照“权限／工具限制或证据不足时保留候选”的分支更新文档；具体原因是 Computer Use 启动调用被物理 Esc 中止，随后用户明确选择“停止运行确认，保留候选；我从程序菜单退出”。包获取和文件校验成功；这不是已经复现的产品回归，也不能据此判定修复包不可用。

### 唯一对象与包核验

| 字段 | 本轮对象 |
| --- | --- |
| 产品版本／源码 | `0.2.1.dev2`／`82ba3a1f21f240e114a112d2b94800ef3b285696` |
| main CI／artifact | [38056842914](https://github.com/Polarzen/net-monitor/actions/runs/38056842914)／[11671937543](https://github.com/Polarzen/net-monitor/actions/runs/38056842914/artifacts/11671937543) |
| 产品 ZIP | `NetMonitor-0.2.1.dev2-windows-x64-82ba3a1f21f2-test.zip` |
| ZIP 大小／SHA-256 | `38,757,694` B／`400f047c83ec3d8341f9356fa41db6de202f4ca28b3bef19ce07f70d4648cb9d` |
| EXE SHA-256 | `b2e376749333b19414ffe1449a3721526ec8661413ff7eb771fa4ffdb73f660f` |
| 实际运行路径 | `%TEMP%\NetMonitor-CI-82ba3a1-pid-runtime-20261010\NetMonitor\NetMonitor.exe` |
| artifact 状态 | 2026-10-10 查询未过期，到期 `2026-10-24 21:45`（香港时间） |

复用上一轮保存的可信本地 ZIP，重新计算上述 SHA-256、检查归档 CRC，并完整解压到本轮专用目录。包内 BUILD-INFO 确认源码提交、版本与干净构建输入；解压后逐一核对 302 个文件的大小和哈希。未重新下载或构建，未改 `_internal`、DLL 或发行目录内容。原 ZIP 和解压目录保留；公开[包身份记录](evidence/stage5/pid-fix-runtime/package.json)仅保留必要路径，私人原始资料置于 Git 忽略目录。

### 实际执行和未取得的证据

启动前只读进程查询没有 NetMonitor.exe，Computer Use 返回的可操作窗口中也没有 Net Monitor。已有用户偏好为 Compact，本轮未写入偏好，也未把偏好值当作实际可见模式证明。启动命令唯一指向上表修复包；当前会话未设置 Qt 离屏平台。

Computer Use 启动调用报告物理 Esc 中止后，没有继续任何桌面输入或重置工具。只读核验确认实际创建了 PID `57848`，create_time `1791641810.896024`（约香港时间 22:16:50.896），可执行路径与上表一致；2026-10-10 `14:21:03.096891 UTC` 的令牌查询为 **未提权**。进程环境没有 `QT_QPA_PLATFORM=offscreen/minimal`；唯一 Qt 环境项是包自身的 `_internal/PySide6/plugins` 路径。该证据只能确认正确 EXE 的普通进程已启动，不能证明界面、权限提示或采集正常。

用户随后选择停止本次运行确认。未请求 UAC，未运行负载，也未启动资源观察器；已复制到忽略目录的历史负载 helper 没有执行。因此等待身份可见、活动传输、停流存活和负载正常退出等阶段均未发生，没有速率／方向、累计不回退、退出账户不串账、显式零速率、两次空闲累计或界面响应的运行证据。没有取得有效界面截图，也没有用源码 GUI、probe 或旧截图代替。

用户在最小退出提示后回复“已退出”。`14:28:38.591743 UTC` 的只读核验确认 PID + create_time 对应实例已消失，当前 NetMonitor.exe 数量为零；记录的退出方式依据是用户报告的“窗口 → 退出”，工具没有操作或观察菜单，不能记为托盘退出测试。没有强制终止。自有 ETW 会话清理仍未验证，未枚举或停止任何其他会话。

### 资源与验证边界

本轮有效资源采样区间 **0**。虽然只读查询得知机器有 32 个逻辑处理器，但未建立已确认的可见窗口模式和真实采集状态，用户又停止了运行确认，因此没有执行 30 秒预热及 120 个一秒区间。CPU 均值／P95／最大值、工作集、private bytes、线程、句柄、采样时长和进程规模均无有效记录，未用普通进程存在或旧 Stage 4 数值填补。没有同条件旧版对照，不能判断性能变化，也不声明“无性能回退”。结构化结果见 [runtime-results.json](evidence/stage5/pid-fix-runtime/runtime-results.json)。

沿用目标源码的**历史** main CI `38056842914`：Windows x64、ARM64 各 343 passed、1 skipped、0 failed，x64 构建和静态检查成功；新增 10 项身份归属回归通过。唯一测试跳过项需要真实系统托盘。本轮没有产品代码变更，因此没有重新执行完整本地回归。既有 CI 的确切检出、JUnit 与产物核对见 [PR #1 收尾记录](https://github.com/Polarzen/net-monitor/pull/1#issuecomment-6098201814)。受控测试验证已知 PID 复用边界，不等于现场发生真实 OS PID 复用，也不代替本轮 EXE 的正常活动与退出确认。

保留修复的保守归属限制：无法核验身份的间隔或退出尾部可能少计，可信身份恢复后排除不确定字节。未更改采样频率、枚举周期或身份检查以取得更好结果。Micro/Card、关注、托盘、原生取消、干净机器、长期稳定性等历史缺口仍按原范围保留。

### 入口、变更与保护

README 的顶部入口、首次启动包名、哈希示例、权限描述和验证表统一指向 `82ba3a1` 候选，并明确“运行确认尚未完成”。旧 `2b6db24` dev2 的原包、哈希、artifact 及历史实测记录全部保留，但明确带有已复现 PID 归属缺陷，不再作为默认推荐。相同版本号通过完整源码提交和 ZIP 哈希区分，没有改名冒充新版本，也没有生成 dev3。

本轮仅修改 README、本文及 `docs/evidence/stage5/pid-fix-runtime/`；无产品、测试、构建输入或工作流变更。使用从已核实 `origin/main` 的 `82ba3a1` 创建的 `chore/pid-fix-runtime-handoff` 分支提交小范围文档 PR。纯文档提交使用 `[skip ci]`，沿用上文目标源码的历史 CI；任何后续文档构建都不是本轮验收对象。没有重新整合 Stage 5、发布 Release、删除分支或旧产物。

普通用户 `ui.json` 与启动前逐字节一致；本轮没有直接修改用户配置。原 `D:\code\net-monitor` 的分支、HEAD、完整 Git index、暂存／未暂存差异及 Stage 4 草稿、`goal.md`、`AGENTS.md` 按独立基线核对，均保持原样。最终保护核验见 [handoff-validation.json](evidence/stage5/pid-fix-runtime/handoff-validation.json)。所有本轮实例已结束，负载和观察器从未启动，不留后台验收任务。
