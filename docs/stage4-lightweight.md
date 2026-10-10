# Stage 4：轻量化收尾

本轮从 `feat/stage-4-lean-core` / `89e6c1f5d000f75790b034155135aa965bea372c` 继续，保留已在本地的 Stage 3F 和后续聚合优化，没有回退到历史参考提交。实际实现提交为 `612ebe5ddd1e9680facd17b36c38a7863b828730`，继续使用原 Stage 4 分支。

实现和自动回归已完成。下文早期性能对比使用固定模拟负载，**不代表真实 ETW 产品资源占用**。2026-10-10 的桌面应用续验已补充真实窗口交互和管理员 ETW 回环证据，详情见文末“桌面应用续验”；仍有必要桌面行为未完成，本分支不是已全面验收的正式发布版本。

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

## CLI 阶段的 Windows 11 验收记录（历史）

本节保留首次验收及 CLI 重试原文；当前桌面宿主的连接、ETW 和资源测量结果见后文“2026-10-10 桌面应用续验”。

环境与真实 ETW 探测原文见 [environment.json](evidence/stage4/environment.json)。直接执行原项目 `permission_probe` 得到 `success=false`，`EnableTraceEx2` 返回 Windows error 5。该工具退出码为 0 仅表示探测正常结束，**不是 ETW 启用成功**。未自动弹 UAC，未改变系统缩放。

已执行的 UI 检查均为 real widgets + fake snapshots 的 **offscreen Qt**：

```powershell
foreach ($scale in @('1','1.25','1.5')) {
  $env:QT_SCALE_FACTOR = $scale
  .\.venv\Scripts\python.exe tools/render_stage3c.py --output docs/evidence/stage4/layout --platform Windows-offscreen-stage4
}
```

三种比例均通过，包含长名、超大速率、安静、未知、失败、权限不足、固定空闲、过期、Card 及 Detailed 累计状态。原始 PNG 和每个标签的字体／几何记录位于 [layout](evidence/stage4/layout/)，manifest 记录实现 SHA 和实际源码哈希。检查了生成的 Micro、Card 图像，没有把它们标成物理桌面截图。

桌面验收优先由 Computer Use 执行，不把能自动执行的交互转交给用户。已完成的功能回归和离屏布局不要求重复人工验收；但这些证据仍不等同于真实桌面交互通过。

用户授权 Computer Use 后再次执行了初始化、`sky.list_windows()`，并重置 JavaScript 会话后重新初始化、重试。两次均返回 `Computer Use native pipe is unavailable ... (os error 2)`，尚未获取任何真实窗口，也没有新的桌面截图或通过结果。更新记录保存在 [environment.json](evidence/stage4/environment.json) 的 `desktop_automation.latest_recheck`。当前阻塞是桌面连接，普通交互列为“待自动桌面复验”，不列为用户必做的人工清单。

| 项目 | 验收方式及当前状态 | 通过标准 |
| --- | --- | --- |
| 长名、大速率、空闲、未知、失败、过期、220×112 与三种比例布局 | 自动测试与离屏渲染已通过；Computer Use 补验真实窗口可读性。无需用户重复手测 | 名称可省略且能查看全名，速率与状态无裁切，未知不显示为零 |
| 悬停、跨入、延迟收起、点击保持、Esc、拖动、菜单和模式切换 | 待 Computer Use 自动桌面复验 | 悬停约 350 ms；跨入保持，离开收起，点击保持，Esc 收起；拖动不误触，切换后仅一个主入口 |
| 不抢焦点 | 待 Computer Use 自动桌面复验 | 在测试编辑窗口输入并等待刷新；焦点仍在该窗口 |
| 关闭到托盘及恢复 | 待 Computer Use 自动桌面复验；真实累计连续性另需 ETW 可用 | 恢复立即显示有效状态，数据停止时为 `—`，采集与累计不中断 |
| Detailed 反复打开／关闭 | 待 Computer Use 自动桌面复验；单实例和共享链路已通过自动测试 | 循环 20 次仍为一个实例，累计不重复、不丢失 |
| 正常退出、无额外控制台、ETW 清理 | 待 Computer Use 与进程／会话观测自动复验；真实 ETW 部分需先具备权限 | 正常退出后辅助资源及会话结束，重新启动可正常采集 |
| 真实性能及稳定性 | ETW 可用后由测量工具和 Computer Use 执行，无需用户手工抄录指标 | 固定负载，三个可见性场景预热 30 秒、观测至少 120 秒，记录资源与累计 |
| 管理员重启与 UAC 接受／取消 | 仅原生 UAC 决策需要用户操作；其余重启、旧实例存活和新实例采集检查由工具完成。当前尚未触发 | 取消后原实例继续，接受后真实 ETW 可用，无额外控制台 |
| Windows 系统级 DPI 切换 | 三种比例自动布局已经覆盖；不要求用户为重复布局测试修改系统设置。若需核对系统级 DPI 特有问题，再安排必要的人工配合 | 系统级 DPI 与应用／离屏缩放的证据分别记录，不互相冒充 |
| 多显示器与越界恢复 | 有设备时优先自动跨屏验证；物理拔插属于条件性扩展，不列为用户当前必做项 | 可用时检查跨屏与负坐标恢复；物理拔插未执行就如实标记，不声称通过 |

只有桌面连接恢复后才能执行当前受阻的 Computer Use 项目。恢复连接不意味着还需要用户逐项人工验收；不因缺少额外显示器或未切换系统设置而要求用户准备非必要环境。

## CLI 阶段的交付与限制（历史）

代码提交：`612ebe5ddd1e9680facd17b36c38a7863b828730`。文档与证据单独提交到同一任务分支。所有 after 测量源码哈希与该实现一致，布局 manifest 也记录该完整 SHA。

开始时 README 和 `docs/stage4-lean-core.md` 已暂存，`goal.md` 未跟踪。README 按当前明确要求继续更新；旧 Stage 4 草稿暂存内容原样保留，未纳入本轮提交，也未用其“Complete”及未经实测的性能结论作为证据。当前权威记录为本文；`goal.md` 同样保留在工作区。没有 reset、clean、stash、强制切换、强推、合并 main 或发布版本。

本轮已知限制：真实 ETW 和物理桌面验收未完成；离线 UI 性能不能推断真实采集总占用；固定集合、短时窗口循环只能说明该观测范围内的资源趋势，无法证明任何情况下都无泄漏。原设计跨新进程身份保留会话账户的内存增长未被裁剪或掩盖。

## 2026-10-10 桌面应用续验

本节追加桌面宿主的新证据，不替换上文 CLI 的 native pipe 失败记录。起点与实际运行源码为 `feat/stage-4-lean-core` / `7f25287cdf675acbb8788d1d3a45552ec6245a3b`；`src` 与实现提交 `612ebe5ddd1e9680facd17b36c38a7863b828730` 内容相同，续验未修改产品源码。逐文件 SHA-256、解释器和权限探测见 [environment.json](evidence/stage4/desktop-acceptance/2026-10-10/environment.json)。

使用现有 Windows 11 x64 / Python 3.14.7 `.venv`，Qt 平台实际为 `windows`，屏幕 DPR 为 1.5，Micro 为 220×112 逻辑像素。没有重建环境、升级依赖或修改系统 DPI。启动环境中没有 Qt 测试覆盖变量。普通 GUI 首次使用现有 `net-monitor.exe`；后续独立观察入口使用真实 `UiController`、Service、Worker、Collector 和托盘，未注入 fake snapshot。

### 已取得的桌面操作证据

Computer Use 成功列举窗口、捕获真实 Compact 窗口，并实际打开、关闭 Detailed。因此桌面连接已经验证，不能继续将旧 native pipe 错误当作当前连接状态。操作时间和动作见 [desktop-actions.json](evidence/stage4/desktop-acceptance/2026-10-10/desktop-actions.json)，真实权限界面见 [截图](evidence/stage4/desktop-acceptance/2026-10-10/ordinary-compact-permission.png)。仅保存目标窗口的必要截图；被其他窗口遮挡的捕获没有作为证据保存。

为验证对象复用，独立工具 [observe_stage4_desktop.py](../tools/observe_stage4_desktop.py) 连接现有 heartbeat 记录窗口对象身份和显隐变化；它不增加产品 timer、线程或输入自动化。测试使用临时显示偏好，并将 Compact 标题标记为 `Desktop Acceptance`。正常桌面动作仍由 Computer Use 执行。资源测量入口另可按参数初始化指定场景，并通过现有 shutdown 限时结束；这种程序化生命周期检查不等同于托盘点击退出。

| 项目 | 本轮结果 | 证据与边界 |
| --- | --- | --- |
| 桌面连接与可逆操作 | 通过 | 真实 Compact 截图、Detailed 打开及关闭 |
| 普通权限提示 | 通过 | `permission_denied` 与“需要管理员权限”；`—` 没有被当作真实流量通过 |
| Detailed 连续开关 20 次 | 通过 | [核验](evidence/stage4/desktop-acceptance/2026-10-10/20-cycles-verification.json)：20 次打开、20 次关闭，同一 Python 对象，Compact 始终显示；[原始日志](evidence/stage4/desktop-acceptance/2026-10-10/ordinary-ui-20-cycles.jsonl) |
| 关闭 Detailed 不退出主程序 | 通过 | 同一 GUI PID 与 create_time 持续存活，窗口恢复可操作 |
| Compact → Micro 仅一个主入口 | 单向通过 | Computer Use 选择真实菜单后，日志记录 Compact 隐藏、Micro 显示；反向切换尚未完成 |
| Micro 实际尺寸 | 几何已确认，视觉未完成 | 220×112 / DPR 1.5；不以运行时尺寸冒充真实 Micro 截图 |
| Micro/Card 悬停、跨入、延迟收起、点击保持、Esc、拖动、停靠、选择及固定关注 | 工具受阻 | `list_windows()` 不返回 Micro 工具窗口；切换后旧 Compact 的捕获返回 `window is not a usable app window`。没有构造句柄或改产品窗口标志绕过限制 |
| 实际托盘条件测试 | 通过 | `QT_QPA_PLATFORM=windows` 下原条件用例实际执行：`1 passed in 0.52s`，不是沿用 skip |
| 托盘恢复模式、托盘点击退出 | 未完成 | 创建真实托盘不等于恢复／退出交互通过；测试 Micro 实例按精确 PID 清理，[记录](evidence/stage4/desktop-acceptance/2026-10-10/ordinary-cleanup.json) 不记作正常托盘退出 |
| 自动刷新不抢焦点 | 普通权限场景通过 | 临时编辑窗口三段输入；输入间及之后 140.5 秒、279 次独立前台观测全部仍为编辑器；Micro 快照计数 75 → 352 |
| 悬停预览不抢焦点 | 工具受阻 | 当前接口不能定位 Micro 或执行已记录的 hover；不扩大自动刷新检查的结论 |
| 置顶与关注分离、selected/foreground/focused 独立 | 沿用自动回归；真实数据交互未完成 | 本轮没有将代码和 fake snapshot 测试扩大为桌面通过 |

早期普通窗口被管理员重启或正常退出中断的记录单独保留在 `ordinary-ui-observations.jsonl`，不能把其中 10 次开关与后续记录拼成连续 20 次。最终 20 次结果来自一个不中断实例。原生窗口句柄在重开时变化，因此复用结论使用实际 Python 对象身份，不使用 HWND 相同作为替代。

焦点检查使用新建的独立、可丢弃文本编辑窗口，Computer Use 依次输入三段测试文字。[截图](evidence/stage4/desktop-acceptance/2026-10-10/focus-editor-after-input.png)、[动作](evidence/stage4/desktop-acceptance/2026-10-10/focus-actions.json)与[核验](evidence/stage4/desktop-acceptance/2026-10-10/focus-verification.json)相互对应；`focus-editor-attempt2.jsonl` 和 `focus-gui-attempt2.jsonl` 保留原始记录。工具输入会主动激活编辑器，因此结论来自输入之间独立的 500 ms 前台轮询，未将输入自身的激活当作证据。Micro 处于普通权限提示状态，没有触发 hover。第一次编辑窗口在文字输入前达到 90 秒上限并正常关闭，随后工具报 `foreground window did not report a process id`；该次保留为未完成尝试，不记作产品抢焦点或输入通过。

### 原生 UAC 与真实 ETW

首次正式 GUI 普通实例（实际 Python PID 2664）之后出现已提权 PID 7588，创建时间 `1791601605.1318035`；用户确认接受应用内管理员重启的 UAC，旧 launcher/Python 实例已退出。没有代点安全许可或输入凭据。原生 UAC 取消路径本轮未执行；额外启动的普通诊断实例清理不算托盘退出证据。

普通权限 `permission_probe` 再次得到 `success=false / EnableTraceEx2 / error 5`，退出码 0 仅表示探测完成。第一次独立诊断提权请求返回 `ShellExecuteW=5`，没有诊断进程或输出；用户随后说明没有看到相应系统 UAC，并明确要求重试。第二次原生 UAC 接受后返回 42，诊断进程确实以管理员运行。

[verify_stage4_etw.py](../tools/verify_stage4_etw.py) 仅运行现有探测入口，使用受控 `127.0.0.1` 负载，最多四次双向各 512 KiB 数据交换。它不会被产品导入或随产品启动。结果见 [etw-probes-attempt2.json](evidence/stage4/desktop-acceptance/2026-10-10/etw-probes-attempt2.json)：

- 提权后的 `permission_probe` 内部 `success=true`。
- raw probe 连续两次均匹配受控子进程 PID，双向各记录 524,288 字节。
- production collector probe 连续两次均 `collector_available=true`、`identity_verified=true`、`collector_closed=true`；上传和下载都有正速率，累计均为 524,288 字节，停流后双向归零且累计稳定。
- 同一 raw 名称、同一 production 名称分别成功复用，未更换名称掩盖重启失败。独立 `ControlTraceW(..., QUERY)` 对这两个自有名称均返回 4201，确认会话不存在，见 [会话查询](evidence/stage4/desktop-acceptance/2026-10-10/etw-session-query.json)。未停止系统或其他程序的会话。

探测内的 `logman` 本地化文本发生编码损失，原始结果保留但不作为语义依据；清理结论另由不依赖文本编码的直接 API 查询支持。以上是 Windows ETW 与生产 Collector 的真实回环证据，**不是外网带宽、GUI 约 2 秒速率窗口、GUI 隐藏累计或托盘退出的替代证据**。

### 真实产品进程资源测量

独立工具 [measure_stage4_live.py](../tools/measure_stage4_live.py) 完成三个真实 GUI 场景，原始每秒资源记录和 GUI 状态日志见 [live-performance](evidence/stage4/desktop-acceptance/2026-10-10/live-performance/)，逐项重新计算的核验见 [root-verification.json](evidence/stage4/desktop-acceptance/2026-10-10/live-performance/root-verification.json)。没有调用旧 `measure_stage4.py`，没有 fake service、fake tray 或合成快照。

测量时间为 2026-10-10 12:21–12:31（UTC+8）。三个新 GUI 进程均管理员权限、Qt `windows`、同一产品源码哈希，使用各自临时偏好。每场预热实际不少于 30 秒，然后获取 120 个一秒 CPU 区间样本，含记录开销的实际观测分别为 121.877、121.862、121.851 秒；每个 GUI 共运行约 190.4 秒。独立观察进程 PID 8780 和负载进程均不包含在 GUI 资源数字中。CPU 100% 表示占满一个逻辑处理器；本机 32 个逻辑处理器，整机百分比为该值除以 32。

| 场景（其余窗口隐藏） | GUI PID / create_time | CPU 单核均值 / P95 | CPU 整机均值 / P95 | 工作集 MiB 均值 / P95 | Private MiB 均值 / P95 | 线程范围 | 句柄范围 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Micro | 14116 / 1791606075.7442372 | 2.918% / 4.7% | 0.0912% / 0.1469% | 82.24 / 82.42 | 43.61 / 43.73 | 5–10 | 343–347 |
| Detailed | 27432 / 1791606267.5441487 | 5.279% / 7.8% | 0.1650% / 0.2438% | 93.94 / 94.00 | 51.78 / 51.91 | 11–16 | 390–394 |
| 全部隐藏，真实托盘保留 | 2624 / 1791606459.6120427 | 2.257% / 4.7% | 0.0705% / 0.1469% | 79.22 / 81.17 | 43.27 / 43.32 | 4–9 | 339–343 |

Card 全程隐藏；Detailed 场景中 Micro 和 Compact 均隐藏。三个场景记录到的进程数范围分别为 398–405、399–405、398–413，累计账户数为 163–165、162–163、163–174。这些集合来自当时实际桌面，未固定或裁剪账户以降低占用。

每个独立负载在 `127.0.0.1` 上以 1 Hz 进行 160 次 64 KiB 上传、128 KiB 下载，自报总量 10 MiB / 20 MiB，持续约 159 秒。GUI 记录中的负载 PID 和 create_time 与实际子进程匹配，应用分组键一致，资源采样期间双向速率均为正，累计单调增长。全部 GUI 采样为 `available`，快照计数持续增加至 378 / 378 / 377；外部资源记录使用的 GUI 状态最大年龄低于 1.5 秒，GUI 日志相邻采样最大间隔低于 1.54 秒。

负载退出后，三个场景的进程网络行均消失，有流量的应用账户保留且活动进程数归零。最终累计分别为 10,354,688 / 20,709,376、10,354,688 / 20,709,376、10,420,224 / 20,840,448 字节，较负载自报值少 1.25%、1.25%、0.625%。原值完整保留。负载发送完成即退出，ETW 批次交付与身份退役存在时间边界；当前记录没有定位差额发生于起始还是退出边界，不能据此声称逐字节完整、归因于 UI 或修改受保护核心。它仍提供了明确的上传／下载方向、正确身份、活动累计和退出后账户保留证据。

三个 GUI 均经现有 `exit_application` 正常关闭，退出码 0、`shutdown_complete=true`、Worker 已结束；实际 PID 已消失，自有 ETW 会话查询均为 4201，没有强制清理。顺序启动的后续两个场景也能重新采集。隐藏场景真实累计不中断，但场景初始化与限时关闭由独立入口调用真实 Controller 完成，**不等于 Computer Use 托盘恢复／点击退出通过**。负载退出前未安排独立空闲阶段，GUI 约 2 秒速率窗口的停流回落尚缺直接证据；不能借用前述零窗口 collector probe 替代。

测量只覆盖本次回环负载与短时运行；验收入口在现有 heartbeat 上增加少量状态记录开销，三个场景均采用同一方式。没有在采样期间操作或截图 GUI。该结果不是无仪器开销的发行版基准、外网带宽测量、随机配对性能对比或长期无泄漏证明。

### 本轮代码与验证边界

仅新增独立验收工具和证据，产品 UI、Controller、Collector、MonitorService、SamplingWorker、ETW、Session Tracker、TDH、采样频率、累计及历史契约均未修改。没有发现足以按最小复现确认并修复的产品缺陷；工具定位、截图几何和焦点接口错误没有被归因于产品。

沿用同一 `src` 内容的历史完整测试 `312 passed, 1 skipped`；本轮补跑原真实托盘用例为 `1 passed`。新工具执行了语法检查、普通权限阻断、防覆盖检查以及真实观察器的限时退出预检；具体真实 ETW 结果见上文。本轮未重跑整个历史测试集，也没有将历史测试称作本轮执行。

开始时暂存的 `docs/stage4-lean-core.md`（blob `e05e54120fee12ef6abe8bbcde81c5ba5b4a0045`）与未跟踪 `goal.md` 继续保留，不纳入本轮交付。

当前结论仍为**部分验收完成，尚不能标记 Stage 4 全面通过，也不能宣布已具备合并与打包条件**。Micro/Card、悬停焦点、真实托盘恢复／退出和真实关注行为仍需可定位该类窗口的桌面工具能力；GUI 停流后的速率窗口及恢复后的当前历史也未完成。缺少第二显示器、没有物理拔插或额外 DPI 切换不作为当前阻塞。
