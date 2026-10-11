# 工具索引

[项目说明](../README.md) · [文档索引](../docs/README.md)

从仓库根目录执行需要运行的单个工具，不要批量运行整个目录。以下工具不由产品入口自动调用；参数及前置条件以各脚本和所链接的验收文档为准。

## 构建与发行包校验

| 工具 | 用途 |
| --- | --- |
| [build_windows.ps1](build_windows.ps1) / [build_windows.py](build_windows.py) | 使用锁定环境构建 Windows x64 包，检查产物并生成清单；默认输出到 `artifacts/stage5/` |
| [verify_windows_release.ps1](verify_windows_release.ps1) | 只读核对指定 ZIP、解压目录、版本和哈希，输出新的 JSON；不启动程序或提权 |

操作步骤见 [README 构建说明](../README.md#构建-windows-x64-测试包)和[稳定版验收](../docs/stable-readiness.md)。已有公开包保持不变；新构建不会替代原包的运行证据。

## 离屏布局与模拟测量

| 工具 | 用途 |
| --- | --- |
| [layout_fonts.py](layout_fonts.py) | 下载并校验用于 CI 和离屏布局的固定字体 |
| [render_stage3c.py](render_stage3c.py) | 用受控假快照渲染真实控件并检查布局 |
| [measure_stage4.py](measure_stage4.py) | 指定源码和场景的离线 UI 工作负载测量 |

这些结果不代表真实 ETW 采集、物理多屏或发行 EXE 的资源表现。

## 真实桌面与 ETW 验收

| 工具 | 用途 |
| --- | --- |
| [observe_stage4_desktop.py](observe_stage4_desktop.py) | 真实桌面应用的交互观察，记录选定视图 |
| [measure_stage4_live.py](measure_stage4_live.py) | 真实桌面 UI、采样工作线程和 ETW 进程的外部测量 |
| [verify_stage4_etw.py](verify_stage4_etw.py) | 有边界的真实 ETW 探针 |
| [verify_stage4_gui_drain.py](verify_stage4_gui_drain.py) / [launch_stage4_gui_drain.cmd](launch_stage4_gui_drain.cmd) | 检查负载退出前存在空闲区间时的 GUI 采集行为 |

这组工具可能启动窗口、负载或 ETW 会话，只在明确的验收场景下执行。环境、权限、参数和结论边界见 [Stage 4 文档](../docs/stage4-lightweight.md)；需要操作原生 UAC 时由测试者处理。目录整理和普通文档维护不需要运行这组工具。

## 历史工具归档

[archive/](archive/README.md) 保存一次性源码改写脚本、旧基线测量脚本及其历史输出，供追溯使用，不是当前构建或验证入口。
