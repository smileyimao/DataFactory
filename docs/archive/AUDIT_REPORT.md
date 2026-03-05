# DataFactory 项目全面审计报告

**审计日期：** 2025-02-20  
**范围：** 全代码库 `/Users/mac/Developer/DataFactory`  
**说明：** 本报告仅作审计，未修改任何代码。

---

## 1. 死代码清单

### 1.1 从未被调用的函数

| 文件 | 函数 | 说明 |
|------|------|------|
| `config/config_loader.py` | `init_storage_structure()` | 已由 `init_storage_from_config()` 替代，main.py 等均调用后者；文档/CHANGELOG 仍提及旧名 |
| `config/config_loader.py` | `get_paths()` | 定义但从未调用；`docs/settings_guide.md` 有引用说明 |
| `scripts/cvat/cvat_api.py` | `upload_images()` | 定义但未使用；`auto_cvat_upload` 使用 `upload_images_from_zip()` |
| `engines/file_tools.py` | `list_video_paths()` | 非递归版本；ingest 使用 `list_video_paths_recursive()` |
| `engines/metrics.py` | `get(name)` | 定义但从未调用；仅 `inc()`、`get_all()` 被使用 |
| `engines/metrics.py` | `reset(name)` | 定义但从未调用 |

### 1.2 从未被调用的文件/模块

| 路径 | 说明 |
|------|------|
| `legacy/main_factory.py` | 已被 `main.py` + `core/pipeline.py` 替代 |
| `legacy/factory_guard.py` | 已被 `core/guard.py` 替代 |
| `legacy/core_engine.py` | 已被 `core/` + `engines/` 替代 |
| `legacy/db_manager.py` | 已被 `engines/db_tools.py` + `engines/fingerprinter.py` 替代 |
| `legacy/factory_config.yaml` | 已被 `config/settings.yaml` 替代 |

### 1.3 未使用的 import

经逐文件检查，主要模块的 import 均有使用。以下为需人工复核的边界情况：

| 文件 | Import | 说明 |
|------|--------|------|
| `main.py` | `argparse` | 用于 `main()` 的 CLI 解析 ✓ |
| `main.py` | `copy` | 用于 `_run_test_mode` 的 `copy.deepcopy` ✓ |
| `main.py` | `tempfile` | 用于 `_run_test_mode` 的 `tempfile.TemporaryDirectory` ✓ |

**结论：** 未发现明确未使用的 import。

---

## 2. 重复代码清单

### 2.1 文件名 sanitization（空格 → 下划线）

相同逻辑出现在 4 处：

| 文件 | 函数 | 实现 |
|------|------|------|
| `engines/labeled_return.py` | `_sanitized_name()` | `name.replace(" ", "_")` |
| `engines/production_tools.py` | `_safe_media_name()` | `name.replace(" ", "_")` |
| `scripts/export_for_cvat.py` | `_sanitize_filename()` | `name.replace(" ", "_")` |
| `scripts/export_for_cvat_native.py` | `_sanitize_filename()` | `name.replace(" ", "_")` |

### 2.2 YOLO 标签解析

类似解析逻辑分散在 2 处：

| 文件 | 函数 | 差异 |
|------|------|------|
| `engines/labeled_return.py` | `parse_yolo_txt()` | 返回 `[(class_id, x, y, w, h), ...]`，忽略第 6 列 |
| `scripts/export_for_cvat_native.py` | `_parse_yolo_label()` | 返回 `[(cid, cx, cy, w, h, conf?), ...]`，支持可选 conf |

### 2.3 配置加载与路径解析

多处脚本重复以下模式：

```python
config_loader.set_base_dir(BASE_DIR)
cfg = config_loader.load_config()
for_labeling = cfg.get("paths", {}).get("labeling_export", "") or os.path.join(BASE_DIR, "storage", "for_labeling")
if not os.path.isabs(for_labeling):
    for_labeling = os.path.join(BASE_DIR, for_labeling)
```

**出现于：** `export_for_labeling.py`、`export_for_cvat.py`、`export_for_cvat_native.py`、`import_labeled_return.py`、`query_lineage.py`、`register_model.py`、`compare_models.py`、`count_vehicles_track.py`、`test_email.py`。

### 2.4 测试配置覆盖

`main.py` 的 `_run_test_mode()` 与 `tests/e2e/test_guard.py` 中均有大量临时路径、目录创建、配置覆盖逻辑，结构相似。

---

## 3. 废弃功能清单

### 3.1 已废弃模块（legacy/）

| 文件 | 替代方案 |
|------|----------|
| `legacy/main_factory.py` | `main.py` + `core/pipeline.py` |
| `legacy/factory_guard.py` | `core/guard.py` |
| `legacy/core_engine.py` | `core/` + `engines/` |
| `legacy/db_manager.py` | `engines/db_tools.py`、`engines/fingerprinter.py` |
| `legacy/factory_config.yaml` | `config/settings.yaml` |

当前代码未 import legacy 模块，仅作参考保留。

### 3.2 未使用的配置/参数

| 项 | 说明 |
|----|------|
| `review.valid_inputs` | 配置中存在，但 `core/reviewer.py` 使用硬编码 `VALID_INPUTS = frozenset({"y", "n", "all", "none"})`，从未读取配置 |
| `--vehicle`（`export_for_cvat.py`） | 保留兼容，无实际效果 |
| `--format coco`（`run_demo_a.sh` 调用） | `export_for_cvat.py` 无 `--format` 参数，该参数会被 argparse 拒绝，脚本存在错误 |

### 3.3 扩展 API 无调用方

| 项 | 说明 |
|----|------|
| `engines/quality_tools.register_extra_check()` | 公开扩展 API，`decide_env` 会遍历 `_EXTRA_CHECK_REGISTRY`，但当前无注册项 |

---

## 4. 配置清单（settings.yaml 未使用项）

### 4.1 未被代码读取的配置项

| 配置键 | 位置 | 说明 |
|--------|------|------|
| `review.valid_inputs` | `settings.yaml`、`settings.default.yaml`、`config_loader._default_config` | 从未被 `core/reviewer.py` 读取，使用硬编码 |

### 4.2 其余配置项使用情况

以下配置项均有代码引用：

- `modality`、`paths.*`（含 `dashboard_port`、`test_source`、`batch_subdirs`、`batch_fails_suffix` 等）
- `ingest.*`（含 `image_mode`、`image_extensions`、`pre_filter_enabled` 等）
- `quality_thresholds.*`、`production_setting.*`（含 `dual_gate_high/low`、`pass_rate_gate`、`save_only_screened`、`human_review_flat` 等）
- `review.mode`、`review.timeout_seconds`
- `email_setting.*`、`vision.*`（含 `cascade_light_*`、`use_i_frame_only`、`motion_threshold` 等）
- `mlflow.*`、`version_mapping.*`、`timezone`、`logging.*`
- `startup_*`、`labeling_pool.*`、`labeled_return.*`、`retry.*`、`rolling_cleanup.*`

---

## 5. 脚本清单

### 5.1 核心 / 长期保留

| 脚本 | 用途 |
|------|------|
| `export_for_labeling.py` | 从 archive 导出待标注清单到 for_labeling |
| `import_labeled_return.py` | 标注回传、伪标签对比、达标并入训练集 |
| `export_for_cvat.py` | 生成 CVAT 图片 zip（创建 Task） |
| `export_for_cvat_native.py` | 生成 CVAT 原生 XML 标注 zip |
| `cvat_api.py` | 本地 CVAT API 封装（模块 + CLI），`--auto-cvat` 使用 |
| `cvat_upload_annotations.py` | 通过 CVAT API 上传标注（云版，需 CVAT_URL/CVAT_TOKEN） |
| `cvat_setup_labels.py` | 创建 CVAT Project 及 27 个 label（云版） |
| `query_lineage.py` | 批次与标注血缘查询 |
| `reset_factory.py` | 清空 storage/db，用于测试 |
| `reset_config.py` | 从 default 恢复 settings.yaml |
| `download_models.py` | 下载 YOLO 模型 |
| `register_model.py` | 在 MLflow 注册模型 |
| `test_email.py` | 测试邮件配置 |

### 5.2 工具 / 一次性或分析用

| 脚本 | 用途 |
|------|------|
| `count_vehicles_track.py` | 基于 YOLO track 统计车辆数 |
| `compare_models.py` | 对比两个模型在同一数据上的表现 |

### 5.3 Shell 脚本

| 脚本 | 用途 | 备注 |
|------|------|------|
| `run_demo_a.sh` | 一键演示：清空 → 投料 → pipeline → 导出 CVAT | 调用 `export_for_cvat.py --format coco`，但该脚本无 `--format` 参数，会报错 |
| `demo_prepare.sh` | 调用 run_demo_a.sh 等 | 依赖 run_demo_a.sh |

### 5.4 脚本分类汇总

| 类别 | 数量 | 脚本 |
|------|------|------|
| 核心 / 长期 | 13 | export_for_labeling, import_labeled_return, export_for_cvat, export_for_cvat_native, cvat_api, cvat_upload_annotations, cvat_setup_labels, query_lineage, reset_factory, reset_config, download_models, register_model, test_email |
| 工具 / 分析 | 2 | count_vehicles_track, compare_models |
| Shell 演示 | 2 | run_demo_a.sh, demo_prepare.sh |

---

## 6. 其他发现

### 6.1 CVAT 相关脚本的配置差异

| 脚本 | 配置 | 场景 |
|------|------|------|
| `cvat_api.py` | `CVAT_LOCAL_URL`、`CVAT_LOCAL_USERNAME`、`CVAT_LOCAL_PASSWORD` | 本地 CVAT（Docker） |
| `cvat_upload_annotations.py`、`cvat_setup_labels.py` | `CVAT_URL`、`CVAT_TOKEN` | 云版 CVAT |

两套配置互不兼容，需根据部署方式选择。

### 6.2 run_demo_a.sh 参数错误

第 47 行：

```bash
python scripts/export_for_cvat.py --format coco --vehicle
```

`export_for_cvat.py` 仅支持 `-o/--output`、`--vehicle`，无 `--format` 参数，运行会因未知参数报错。

---

## 7. 汇总

| 类别 | 数量 |
|------|------|
| 死函数 | 6 |
| 死模块（legacy） | 5 |
| 未使用配置项 | 1（`review.valid_inputs`） |
| 重复逻辑模式 | 4 |
| 废弃参数/脚本错误 | 2（`--format coco`、`review.valid_inputs`） |
| 核心脚本 | 13 |
| 工具脚本 | 2 |
| Shell 演示脚本 | 2 |

---

## 8. 建议（仅供参考，未实施）

1. **死代码**：考虑删除或标注 `init_storage_structure`、`get_paths`、`upload_images`、`list_video_paths`、`metrics.get`、`metrics.reset`；或补充文档说明保留原因。
2. **重复逻辑**：抽取公共函数，如 `sanitize_filename()`、统一 YOLO 解析、统一 config/path 加载。
3. **配置**：在 `core/reviewer.py` 中读取 `review.valid_inputs`，或从配置中移除该项。
4. **run_demo_a.sh**：删除 `--format coco` 参数，或为 `export_for_cvat.py` 增加 `--format` 支持。
5. **legacy**：保留作参考时，在 README 或文档中明确标注为已废弃。
