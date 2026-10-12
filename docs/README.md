# 文档索引

[返回项目说明](../README.md) · [工具索引](../tools/README.md)

## 当前版本与维护

| 文档 | 用途 |
| --- | --- |
| [dev5 公开发布记录](releases/0.2.1.dev5.md) | 当前包的图标、源码、哈希及验证范围 |
| [dev4 历史发布记录](releases/0.2.1.dev4.md) | 原包的主机定量验证及虚拟机反馈 |
| [稳定版验收](stable-readiness.md) | 验收要求、证据边界、未验证项目及签名步骤 |
| [发布后维护](maintenance.md) | 反馈分类、最小修复流程和不可变发布资产 |

当前公开版本为未签名 Pre-release。每份验证结论只适用于记录中的源码和包哈希；以对应发布记录为准，不把历史设计或工具输出当作当前版本验收通过。

## 设计与阶段记录

以下文档保留原路径，便于现有链接和证据引用继续定位。它们说明当时的设计、执行结果和限制。

| 文档 | 内容 |
| --- | --- |
| [Stage 3A 验收](stage3a-acceptance-2026-09-16.md) | 早期采集与应用聚合验收 |
| [Stage 3B 集成](stage3b-integration-2026-09-17.md) | 会话累计、进程身份和集成记录 |
| [Stage 3C 微型窗口](stage3c-micro-widget.md) | Micro、Card、选择、关注和显示偏好 |
| [Stage 3D 前后台状态](stage3d-micro-presence.md) | 应用前台、后台及未知身份 |
| [Stage 3E 速率历史](stage3e-rate-history.md) | 有界短期历史、曲线和未知区间 |
| [Stage 3F 网络焦点](stage3f-network-spotlight.md) | 前台与后台流量说明 |
| [Stage 4 轻量化](stage4-lightweight.md) | 刷新、资源测量及桌面验收 |
| [Stage 5 Windows 打包](stage5-windows-package.md) | 构建、依赖、发布包身份及历史试用 |

## 历史候选与证据

- [dev3 发布记录](releases/0.2.1.dev3.md)：保留该版本独立的产物身份和验证范围。
- [dev4 内部候选](dev4-candidate.md)：与最终公开 dev4 包分开记录。
- [Stage 4 证据](evidence/stage4/)和 [Stage 5 证据](evidence/stage5/)：已提交的原始历史材料，保留文件名和内容；结合对应阶段文档阅读。

新的本地构建产物、截图、原始日志和检查点放到根目录 `artifacts/` 下，该目录不进入 Git。需要公开的证据先检查隐私，再与具体版本及验证范围一起记录；不要把本地检查点或整个发行目录直接提交。
