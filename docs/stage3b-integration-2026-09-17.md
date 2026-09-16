# Stage 3B 本地集成记录（2026-09-17）

状态：**本记录保存合并提交前的本地验证结果：A 的精确提交已完成双平台验证，B 已通过本地测试与独立只读审查。最终合并 SHA、远端同步和该 SHA 的 CI/ETW 结果以交付报告为准；本文不以本地测试代替远端或桌面验收。**

## 输入与验证边界

本次集成以 B HEAD `962a3a04e4bdd21d309106c017a5fd96ad7b9d98` 和 A `ee156d725f4a2ea2d1ee7255070d91d8b54ad1d6` 为已知输入。A 的精确双平台结果已完成：

- [CI #35118756782](https://github.com/Polarzen/net-monitor/actions/runs/35118756782)：`100 passed`、`0 failed`、`1 skipped`；skip 是 runner 无真实系统托盘。
- [ETW Experiment #35118757413](https://github.com/Polarzen/net-monitor/actions/runs/35118757413)：`45 passed`、`0 failed`；raw loopback ×2、production collector ×2、完整身份、上下行各 `512 KiB` 闭合、collector 关闭和 standard-user permission error `5` 均通过。

A 的日志不包含直接 `loss` 字段。旧本地观察的 direct numeric QUERY 单独记录过 status `0`、loss `0`；这条证据不替代 A 的 CI/ETW 结论。

当前 shell 不是管理员，未启动真实 ETW、GUI 或 UAC。Windows 11 实机 build `26200`、Python `3.14.7` 的 Stage 3A 用户观察仍以 [Stage 3A 验收记录](stage3a-acceptance-2026-09-16.md) 为准；100%/125% DPI 未验证，150% DPI 已有用户观察。历史临时目录仍按 Stage 3A 记录保留，未在本次工作中删除。

## 合并后的固定语义

架构继续是一个 `MonitorService`、一个 `SamplingWorker`、一个 `WindowsProcessNetworkCollector`、一个 ETW Session。GUI 约 500 ms 刷新，GUI 进程速率窗口为 2 秒，进程刷新为 2 秒并保持 `include_status=False`；采集工作在线程中执行，UI 线程不增加采集工作。默认 collector 的 `rate_window_seconds=0.0` 和 service 公开行为保持兼容。

应用会话 tracker 只在本次 Net Monitor 会话内累计；被监测进程退出后，已确认累计仍保留，不跨 Net Monitor 重启保存。可信身份为 `(pid, create_time)`，首次可信累计样本全额计入；每个方向都维护独立高水位，增量为 `max(0, current-high)`，高水位为 `max(high,current)`。回退、乱序和 reset 不猜 epoch，因此样本重新超过旧高水位前可能漏计。两个方向互不影响。`create_time=None` 不建立 attribution、不进入持久累计；网络行任一累计字段为 `None` 时整行跳过，负值按 0 处理；退休行的 `row.pid` 与 `process.pid` 不一致时跳过。

首次 attribution 的 application key 在整个 session 固定。exe 暂时缺失、恢复、再次缺失不会迁移或双计；metadata 恢复只更新当前观察输入，不创建第二个账户。PID reuse 由 `(pid, create_time)` 分离，旧身份只保留已确认累计，新身份隔离 baseline。

`NetworkAggregator.retain_pids(pids)` 在同一锁内取出并删除非活动 PID 桶，返回 `removed` totals。collector 在该原子切点前已提交的事件交接给退休样本；切点后的迟到事件不能猜回旧身份。活动 PID 桶保留，PID reuse 的旧身份只交接 `previous_*`，避免把混合桶的新流量补归旧身份。退休队列由 service 在 tracker 更新前 drain，并且每个样本只消费一次；没有 `drain_retired` 的旧 collector 仍得到空退休序列。关闭后历史账户保留，活动进程数降为 0 的结果保留在 session snapshot 中。

collector 的 rate history 保留 A 的窗口基线、计数器回退清 history、时钟回退重新锚定和 cleanup 行为。ETW probe 保留 psutil 读取的 name/executable/create_time、signal 前 baseline、idle 总量稳定与精确零速率恢复和既有退出码；双向活动等待允许上下行在不同 poll 出现，私有等待函数返回 latest 和两个方向的峰值，JSON 活动 rate 使用峰值、idle 字段使用 latest。

## 本地强 oracle

本地测试覆盖以下固定结果：

- tracker 及退休样本 `150 → 120 → 130 → 170 → 170` 的累计为 `170`，并验证上下行高水位独立；`100 → 0 → 20 → 101` 的累计为 `101`。
- 重复、乱序、退休重复 drain 不增长；未知 `create_time` 活动/退休不新增累计或 attribution；若同 exe 账户已存在，枚举到的未知身份仍计入 active count；metadata 缺失→恢复→缺失只保留一个账户；退休 PID 不匹配、负值和任一缺失累计字段都不引入错误累计。
- PID reuse 的旧身份 `100` 与混合桶隔离；新身份首次为 `0`，后续 `80` 只增长 `80`。原子切点前 `100` 加切点前事件 `50` 交接为 `150`，第二次 drain 为空；prune 只移退休 PID，活动 PID 保留，切点后新事件不改已返回 totals。
- A 的窗口 rate、回退、clock rollback、cleanup、probe identity/baseline/idle 测试全部保留；重复样本不建立新 identity，进程 churn 的增长仅来自有意保留的 identity 和累计账户。

## 本地验证命令

所有 Python 命令使用仓库虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pytest -ra
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

本地最终 `pytest -ra`：Python `3.14.7`，收集 `118` 项，`117 passed`、`0 failed`、`1 skipped`；唯一 skip 是 runner 无真实系统托盘（`tests/test_stage3a_ui.py:268`）。`tests/test_application_session.py` 定向测试为 `15 passed`。`compileall -q src tests` 通过，`git diff --check` 通过；这些结果只代表本地未提交工作树，不代表未来 CI 或真实管理员 ETW。

## 未验证与下一步

集成后的最终提交仍需由 Root 负责 Git 集成和在有权限环境安排双平台 CI/ETW；本地不宣称新的 workflow、真实管理员 probe、GUI/UAC、资源 soak 或 100%/125% DPI 结果。Stage 3A 的用户实机观察、150% DPI 结果、历史日志 warning 与临时目录边界继续按原验收记录解释。
