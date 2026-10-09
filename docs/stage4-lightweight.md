# Stage 4：轻量化收尾

本轮从 `feat/stage-4-lean-core` / `89e6c1f5d000f75790b034155135aa965bea372c` 继续，保留已在本地的 Stage 3F 和后续聚合优化，没有回退到历史参考提交。实际实现提交为 `612ebe5ddd1e9680facd17b36c38a7863b828730`，继续使用原 Stage 4 分支。

实现和自动回归已完成。性能证据是同机、固定模拟负载的离线 UI 对比，**不代表真实 ETW 产品资源占用**。真实 ETW 探测被权限拒绝，物理桌面交互尚未验收；本分支不是已全面验收的正式发布版本。

## 实际修改与信息分工

| 视图 | 常规信息与入口 | 本轮变化 |
| --- | --- | --- |
| Micro | 图标、应用名、上下行速率、前后台／未知、运行及关注状态 | 固定 220×112；删除 Sparkline 实例、布局占位和刷新代码；Spotlight 仅 tooltip；长名称省略，完整名可悬停查看 |
| ApplicationCard | 完整名称、身份 tooltip、速率、曲线、本次累计、Top 3、选择／关注、详细信息、Spotlight、管理员重启 | 曲线移到速率下面；合并状态与关注行；路径、累计说明和防抖说明移入 tooltip；Top 3 中选中对象用“当前应用”指代，保留原 key 绑定及选择能力 |
| Compact | 默认可见应用合计与 Top 5、Detailed 入口 | 与 Micro 保持一个主入口；隐藏时不刷新列表 |
| Detailed | 应用／PID 树及筛选、本次监控累计、已有 Spotlight 区 | 单实例；默认复用控制器的聚合结果；重复 heartbeat 不重复同步树；隐藏时停止展示工作 |

没有增加卡片、页签、选择模式、动画或交互层级。悬停预览、跨入卡片、延迟收起、点击保持、Esc、拖动、菜单、置顶／关注分离均沿用已有机制。累计页仍仅隐藏双向累计均为零的行，不删除账户；已退出且有流量的账户继续保留。

## 数据维护、隐藏与恢复

- `_on_snapshot` 继续接收共享快照、维护选择和累计投影，每个新快照记录一次速率历史；重复传入同一快照对象不重复记录，也不会重置过期时钟。
- 原 SamplingWorker、Service、Collector、ETW 与会话 Tracker 照常工作。历史保留 60 秒／每应用 120 点／最多 32 应用，使用同一单调时钟和原 LRU。窗口读取、菜单、heartbeat 和模式切换不补造历史。
- 移除 `snapshot_ready → Compact/Detail.apply_snapshot` 的直连。Controller 只向可见窗口或即将显示的窗口分发；隐藏窗口不格式化标签、不同步／排序树、不准备曲线、不申请或转换展示图标。
- 全隐藏时仍处理采样失败、时间过期和已有图标 IO 的完成结果，但不构造 WidgetFrame。Micro 可见而 Card 隐藏时，frame 不读取历史、不生成应用选择列表和 Top 3。
- 发布的展示快照与共享应用组同步映射 `STALE/FAILED → None`。重新显示主窗口、Card、Detailed，以及切换置顶导致的重新显示，都先同步有效状态。不会等待下一次采样、额外采样或闪回旧正速率。
- 快照身份仅用于避免重复投递树／列表，时间状态仍由 heartbeat 判定。曲线在显示时按当前时刻裁剪，前后台变化仍由既有 heartbeat 驱动。
- 隐藏和模式切换撤销前台证据。Spotlight 额外核对缓存前台 PID 对应的 application key 与 `create_time`，PID 复用后不能沿用旧证据；它独立于当前选择和固定关注。前台查询仍仅发生在既有 heartbeat，每次最多一次。
- 图标仍由原本地、有界异步缓存处理。隐藏时完成的请求可进入缓存，恢复显示时复用；只有当前 key 的像素可以更新当前应用，各隐藏窗口不接收 pixmap 更新。
- 卡片曲线只在样本变化时重新准备数组；修复原有“全零数据夹有 None 时画成一条完整水平线”的情况，未知区间保持断点。

## 架构与范围核对

`Collector/WindowsProcessNetworkCollector`、`MonitorService`、`SamplingWorker`、ETW 生命周期、Session Tracker、TDH、核心数据契约和依赖清单均未修改。采样频率、2 秒速率窗口、累计记账和身份规则未改。没有增加产品线程、进程、timer、枚举／扫描、数据库或常驻依赖。

[静态审计原始记录](evidence/stage4/architecture-audit.json) 对比开始 HEAD 与本轮实现：29 个受保护文件内容不变，运行时 timer／线程／采集器／Service／Worker／ETW／进程枚举构造调用计数不变。功能测试同时覆盖共享服务、单 Worker、三个既有 Controller timer、Detailed 单实例、隐藏继续采样、无托盘退出及幂等 shutdown。静态审计不是物理 ETW 清理的替代证据。

## 自动测试

使用现有 `.venv/Scripts/python.exe`，Python 3.14.7；没有新建环境或升级依赖。

首次运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -ra
```

结果 **285 passed, 1 failed, 1 skipped**。原始失败是离屏字体缺失；还有既有 pytest 缓存写权限警告，见 [初始日志](evidence/stage4/baseline-tests.txt)。按项目原工具准备已校验的字体后，修改前仍为 **285 passed, 1 failed, 1 skipped**：同一渲染用例进一步暴露 Micro 状态文字被裁切，见 [字体齐备后的基线日志](evidence/stage4/baseline-font-tests.txt)。该裁切随本轮删除曲线和常驻 Spotlight 行而修复。

可复现的最终验证命令：

```powershell
.\.venv\Scripts\python.exe tools/layout_fonts.py --prepare "$env:TEMP\net-monitor-layout-font"
$env:NET_MONITOR_LAYOUT_FONT = "$env:TEMP\net-monitor-layout-font\NotoSansCJKsc-Regular.otf"
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m pytest -q -ra -o cache_dir="$env:TEMP\net-monitor-pytest-stage4"
.\.venv\Scripts\python.exe -m compileall -q src tools/measure_stage4.py tools/render_stage3c.py
git diff --check
```

完整结果 **312 passed, 1 skipped, 0 failed**，10.74 秒，见 [完整日志](evidence/stage4/final-tests.txt)。唯一跳过是 runner 无真实系统托盘的既有条件测试，未增加 skip。编译和 diff 空白检查通过。中途针对性回归为 **91 passed, 1 skipped**，见 [日志](evidence/stage4/targeted-tests.txt)；后续补齐初始失败状态、隐藏 Worker 和置顶恢复测试后以完整结果为准。

新增 26 个测试实例，旧断言只按新 UI 分工更新：检查 Compact/Micro 前先显示它们；Card 长说明改查 tooltip；安静状态取消重复第二行。未删除或跳过正确性检查。

| 要求 | 当前证据 |
| --- | --- |
| 220×112、无 Micro 曲线或占位、Card 正确历史 | `test_stage4_lightweight.py`；三种比例的 PNG／字形／几何检查 |
| 长名、大速率、全零、None、失败、过期 | `test_stage3c_session_ui.py`、扩展渲染场景与新恢复矩阵 |
| 隐藏 Micro/Compact/Detail/Card 无展示、全隐藏数据继续 | 新调用计数测试、实际 SamplingWorker 配合 fake service 的连续采样测试 |
| 四视图恢复新鲜／过期／失败；同快照随时间失效 | 12 项参数矩阵、重复树调用计数、首次快照前失败、置顶恢复测试 |
| 历史去重、60 秒／120 点／32 应用、LRU、None 断点 | 新读取／菜单／模式计数测试、原 `test_rate_history.py`、画线调用记录 |
| 自动选择／防抖／关注及身份独立 | 原 `test_stage3c_model.py`、`test_stage3d_presence.py`、`test_network_spotlight.py`；新前台 PID 复用测试 |
| 图标异步 key 校验、隐藏完成及恢复 | 原 `test_stage3c_icons.py`、新图标完成缓存／错误 key 防护测试 |
| 单实例／共享链路／timer／生命周期 | 原 UI／worker／collector／ETW 测试、构造调用审计、新隐藏采样测试 |
| 会话累计、零账户筛选和已退出有流量账户 | 原 session model/UI、application session 测试，完整测试集未删减 |

## 性能方法与结果

测量脚本为 [tools/measure_stage4.py](../tools/measure_stage4.py)，仅独立运行，不被产品导入。旧的 `measure_baseline.py` 实际只观察测量脚本自身，因此没有用其历史数字做本轮前后对比。

同一台 Windows 11 10.0.26200 x64、32 逻辑处理器、同一 Python 3.14.7 虚拟环境、Qt/PySide6 6.11.2、psutil 7.2.2、非管理员权限。相同离屏 Qt 和已校验字体、固定 24 应用／96 进程／24 累计账户，每 500 ms 注入一个新 fake snapshot，保持相同速率序列和累计增长规则。每场景新进程、预热 30 秒、设置 121 秒观测，记录约 120 个一秒 CPU 区间及实际时间戳。前版由 `git archive 89e6c1f ... src` 解压到临时目录后通过明确 `sys.path` 加载，没有覆盖当前工作区。

```powershell
# --source 为包含 src 的源码目录；同一解释器分别运行旧源码归档与当前目录。
.\.venv\Scripts\python.exe tools/measure_stage4.py --source $beforeRoot --revision 89e6c1f --scenario micro --duration 121 --output docs/evidence/stage4/before-micro.json
.\.venv\Scripts\python.exe tools/measure_stage4.py --source . --revision 612ebe5 --scenario micro --duration 121 --output docs/evidence/stage4/after-micro.json
# 同样执行 detail、hidden；另以 cycles 反复开关已有窗口观察资源数量。
```

`micro` 仅 Micro 可见；`detail` 仅 Detailed 可见；`hidden` 全部视图隐藏（使用 fake tray）；开始时均已创建同一个 Detailed。Card 始终关闭，避免不同视图负载混淆。脚本使用 fake service，**没有启动真实 Worker/ETW**；这隔离了本轮 UI 工作量，不能拿这里的低占用声称真实采集产品达标。

CPU 使用 psutil 区间 CPU%，**100% 表示一个逻辑处理器满载**，除以 32 才是全机归一化百分比。P95 使用最近秩法。内存分别记录 Windows 工作集（RSS）与 private bytes，不混用。每秒原始样本、实际时长、线程、句柄、Qt 对象、历史、账户数量及 UI 源文件 SHA-256 全部保存在 [evidence/stage4](evidence/stage4/)。进程观察自身指标的开销两版相同，UI 调用计数包装也两版相同。期间机器其它任务未冻结，单次短测不能建立统计显著性或长期无泄漏结论。

| 场景 | 实际观测秒 前→后 | CPU 均值% 前→后 | CPU P95% 前→后 | 工作集均值 MiB 前→后 | private bytes 均值 MiB 前→后 | 线程范围 前→后 |
| --- | --- | --- | --- | --- | --- | --- |
| 仅 Micro | 121.001 → 121.003 | 4.25 → 2.12 | 7.80 → 3.10 | 68.70 → 68.89 | 41.10 → 41.48 | 2–7 → 2–7 |
| 仅 Detailed | 120.999 → 120.999 | 5.42 → 5.12 | 7.80 → 7.90 | 71.80 → 72.16 | 44.20 → 44.65 | 9–14 → 9–14 |
| 全部隐藏 | 121.001 → 121.003 | 3.92 → 2.47 | 6.30 → 4.70 | 43.92 → 67.02 | 40.49 → 40.37 | 1–6 → 1–6 |

| 场景 | 句柄范围 前→后 | Qt widget 数 前→后 | 最终历史点数 前→后 |
| --- | --- | --- | --- |
| 仅 Micro | 227–231 → 227–231 | 126–126 → 122–122 | 2880 → 2880 |
| 仅 Detailed | 257–261 → 257–261 | 126–126 → 122–122 | 2880 → 2880 |
| 全部隐藏 | 225–229 → 225–228 | 126–126 → 122–122 | 2880 → 2880 |

以上均为离线 UI 单次观测值；工作集受 Windows 内存管理影响，不能把它与 private bytes 混为同一指标。首轮 Micro 基线 CPU 均值 2.39%，同代码补测为 4.25%，可见运行间波动，不能依据本表给出统计显著性或真实产品 CPU 降幅。

确定的展示调用变化如下（正式观测阶段，恢复显示的初始化在预热前）：

| 场景 | 隐藏 Micro apply_frame | 隐藏 Compact apply_snapshot | 隐藏 Detailed apply_snapshot / 树同步 | 历史 get_series |
| --- | --- | --- | --- | --- |
| 仅 Micro | 不适用 | 241 → 0 | 241 / 241 → 0 / 0 | 483 → 0 |
| 仅 Detailed | 482 → 0 | 241 → 0 | 不适用，可见树两版均 241 次 | 482 → 0 |
| 全部隐藏 | 482 → 0 | 241 → 0 | 241 / 241 → 0 / 0 | 482 → 0 |

全隐藏修改后 `calls={}`：没有 frame、展示 apply、树同步、曲线读取或图标请求，历史仍达到 24×120=2880 点，累计账户仍为 24。隐藏 Card 两版都没有 apply_frame，本轮进一步取消了仅为隐藏曲线而做的历史读取。

原始记录：[Micro 前](evidence/stage4/before-micro.json)／[后](evidence/stage4/after-micro.json)、[Detailed 前](evidence/stage4/before-detail.json)／[后](evidence/stage4/after-detail.json)、[全隐藏前](evidence/stage4/before-hidden.json)／[后](evidence/stage4/after-hidden.json)。记录中的后版标签 `89e6c1f+stage4-working-tree` 表示启动测量时尚未提交；其逐文件源码哈希已与实际实现 `612ebe5` 核对一致。


首轮 120 秒设置的基线只有 119 个完整 CPU 区间，保留在 `evidence/stage4/exploratory/`；正式对比使用统一 121 秒设置的补测，未将修改后的数据充作基线。


固定集合的窗口循环见 [after-cycles.json](evidence/stage4/after-cycles.json)：预热 30 秒，观测阶段 120.975 秒；包括预热共 302 轮（观测阶段 241 轮），每轮打开 Micro、Card、Detailed，切换 Compact/Micro，再隐藏所有窗口。

- Qt widget 数持续为 122、Controller 子 QObject／timer 数均为 3，累计账户数和历史应用数均为 24。
- 历史点数从 1512 增至 2880（24×120）后保持上限，属于有界历史填充。
- private bytes 首末为 40.52／40.73 MiB，工作集首末为 66.96／68.27 MiB；句柄范围 227–231、线程范围 2–7。完整均值、高分位和逐秒样本仍见原始 JSON。
- 循环场景的 `hidden_calls` 包含**显示之前立即同步**的合法调用；不能把它与稳定全隐藏场景混淆。后者的展示调用确实为零。

未见此固定集合、短时循环内 widget／timer／账户数持续增长；没有据此声称长期绝无泄漏。新进程身份带来的原设计账户保留未纳入该固定集合压力场景，也未删除底层账户来压低数据。

## Windows 11 实机验收状态

环境与真实 ETW 探测原文见 [environment.json](evidence/stage4/environment.json)。直接执行原项目 `permission_probe` 得到 `success=false`，`EnableTraceEx2` 返回 Windows error 5。该工具退出码为 0 仅表示探测正常结束，**不是 ETW 启用成功**。未自动弹 UAC，未改变系统缩放。

已执行的 UI 检查均为 real widgets + fake snapshots 的 **offscreen Qt**：

```powershell
foreach ($scale in @('1','1.25','1.5')) {
  $env:QT_SCALE_FACTOR = $scale
  .\.venv\Scripts\python.exe tools/render_stage3c.py --output docs/evidence/stage4/layout --platform Windows-offscreen-stage4
}
```

三种比例均通过，包含长名、超大速率、安静、未知、失败、权限不足、固定空闲、过期、Card 及 Detailed 累计状态。原始 PNG 和每个标签的字体／几何记录位于 [layout](evidence/stage4/layout/)，manifest 记录实现 SHA 和实际源码哈希。检查了生成的 Micro、Card 图像，没有把它们标成物理桌面截图。

桌面自动化初始化后调用 `sky.list_windows()` 返回 native pipe 不可用（os error 2），无法执行真实鼠标／键盘交互。以下全部明确为 **待人工验收**：

| 项目 | 复现步骤与通过标准 |
| --- | --- |
| 100%／125%／150% 物理缩放 | 用户自行在 Windows 设置切换比例；每次启动同一提交，检查微型窗各状态、长名称、速率与卡片按钮无裁切，逻辑尺寸仍 220×112 |
| 悬停、跨入、延迟收起、点击保持、Esc、拖动、菜单和模式切换 | 悬停约 350 ms，跨入卡片后移动鼠标；离开收起，点击保持，Esc 收起；拖动不误触展开，切换后仅一个主入口 |
| 不抢焦点 | 在记事本连续输入，等待采样和自动选择、悬停预览；焦点仍在输入窗口 |
| 关闭到托盘及恢复 | 启用真实采集后关闭主窗口，确认流量累计继续，托盘恢复立即显示当前有效状态；数据停止时应为 `—` |
| Detailed 反复打开／关闭 | 循环 20 次；始终一个实例、无新增采集会话，累计不重复也不丢失 |
| 多显示器与越界恢复 | 有第二显示器时跨屏拖动，再拔掉显示器；恢复到可用工作区，不落在屏幕外 |
| 管理员重启与 UAC 取消 | 用户点击管理员按钮，先取消确认原实例仍在，再接受确认真实 ETW；不出现不必要的控制台 |
| 正常退出及 ETW 清理 | 用户从托盘退出，确认 Worker、图标辅助资源和原 ETW 会话结束；重新启动可采集，无残留会话错误 |
| 真实性能及稳定性 | 用户授权提升权限后，以固定下载／上传负载，在三个真实可见性场景分别预热 30 秒、观察至少 120 秒，记录 CPU／工作集／private bytes／线程／句柄；长期运行区分有界历史与原设计保留的身份／累计账户 |

## 交付与限制

代码提交：`612ebe5ddd1e9680facd17b36c38a7863b828730`。文档与证据单独提交到同一任务分支。所有 after 测量源码哈希与该实现一致，布局 manifest 也记录该完整 SHA。

开始时 README 和 `docs/stage4-lean-core.md` 已暂存，`goal.md` 未跟踪。README 按当前明确要求继续更新；旧 Stage 4 草稿暂存内容原样保留，未纳入本轮提交，也未用其“Complete”及未经实测的性能结论作为证据。当前权威记录为本文；`goal.md` 同样保留在工作区。没有 reset、clean、stash、强制切换、强推、合并 main 或发布版本。

本轮已知限制：真实 ETW 和物理桌面验收未完成；离线 UI 性能不能推断真实采集总占用；固定集合、短时窗口循环只能说明该观测范围内的资源趋势，无法证明任何情况下都无泄漏。原设计跨新进程身份保留会话账户的内存增长未被裁剪或掩盖。
