# 历史工具归档

[返回工具索引](../README.md)

本目录保留从原 `tools/` 移入的历史文件，内容未作改写。它们不参与当前 CI、构建或产品运行。

| 文件 | 历史用途 |
| --- | --- |
| `_add_groups_property.py`、`_fix_compact_window.py`、`_fix_micro.py` | 对特定旧版源码执行一次性修改 |
| `_patch_card.py`、`_patch_controller.py`、`_patch_detail.py`、`_patch_micro_window.py`、`_patch_model.py` | 插入或替换旧版 UI 和模型片段 |
| `_create_docs.py`、`_write_spotlight.py`、`_write_tests.py`、`_update_version.py` | 生成当时的文档、实现、测试或版本文本 |
| `measure_baseline.py`、`baseline_metrics.txt` | 旧测量脚本及输出；测量对象是脚本自身进程，不是 Net Monitor 发行程序 |

一次性脚本包含固定字符串替换和直接文件写入，部分在导入时就会改写文件；不要在当前仓库运行或导入它们。需要修改现有实现时应直接审阅源码并进行针对性变更。归档不会让这些脚本适配当前版本，历史基线数字也不能用于当前应用性能验收。
