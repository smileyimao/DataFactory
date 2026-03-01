# V3 任务清单（含 Model Registry）

> 基于 v3_dev_plan.md + Roadmap 整理，补充 Model Registry。供排期与跟踪。

---

## 一、总览

| Phase | 内容 | 优先级 |
|-------|------|--------|
| **Phase 1** | Auto-modality routing（audio/lidar/vibration） | P0 |
| **Phase 2** | 配置回退兼容 | P0 |
| **Phase 3** | 数据血缘与 Transform Log | P1 |
| **Phase 4** | MLflow 数据→模型追溯 + **Model Registry** | P1 |
| **Phase 5** | Labeling 工作流增强 | P2 |

---

## 二、Phase 1：Auto-modality Routing

| # | 任务 | 产出 |
|---|------|------|
| 1.1 | 新建 `engines/modality_detector.py` | `detect_modality(path) -> str` |
| 1.2 | 扩展名→modality 注册表（.mp4→video、.wav→audio、.pcd→lidar、.csv→vibration） | 字典/配置 |
| 1.3 | 可选：Magic bytes 判断 .bin | `_detect_by_magic(path)` |
| 1.4 | 可选：ffprobe 判断 .mp4 内容 | `_detect_mp4_content(path)` |
| 1.5 | 扩展 `scan_raw()`，按 modality 分组 | `{video: [...], audio: [...]}` |
| 1.6 | unknown 文件移入 `quarantine/unknown_format/` | pre_filter 扩展 |
| 1.7 | Pipeline 按 modality 分批或分发 | batch_id 可带后缀 |
| 1.8 | Config：`modality_filter`、`unknown_format_action` | config_loader |

---

## 三、Phase 2：配置回退兼容

| # | 任务 | 产出 |
|---|------|------|
| 2.1 | `modality` 存在且无 `modality_filter` 时自动映射 | 兼容逻辑 |
| 2.2 | 旧配置 `modality: "video"` 零改动继续工作 | 验证 |
| 2.3 | 单元测试：config 兼容 | test_config_loader |

---

## 四、Phase 3：数据血缘与 Transform Log

| # | 任务 | 产出 | 状态 |
|---|------|------|------|
| 3.1 | **Transform Log**：抽帧率、码率、分辨率等算子参数 | batch_lineage 表 + transform_params JSON | ✅ |
| 3.2 | **可视化血缘图谱**：Batch_ID → raw → QC → refinery/inspection → labeled → training | scripts/query_lineage.py | ✅ |
| 3.3 | **标注回写关联**：标注完成回写 DB，关联 batch/model 版本 | label_import 表 | ✅ |

---

## 五、Phase 4：MLflow 数据→模型追溯 + Model Registry

| # | 任务 | 产出 | 状态 |
|---|------|------|------|
| 4.1 | **Dataset 关联**：MLflow run 关联 training 数据来源（batch_id、路径） | refinery_dir、inspection_dir、source_archive_dir 入 run params | ✅ |
| 4.2 | **Model lineage**：模型版本可追溯至训练数据批次与变换链路 | batch_lineage + label_import 元数据 | ✅ |
| 4.3 | **可复现**：给定模型版本，反查训练数据与 QC 参数 | query_lineage.py | ✅ |
| 4.4 | **MLflow Model Registry**：训练产出注册到 Registry，按名称+版本加载 | scripts/register_model.py | ✅ |
| 4.5 | **config 引用 Registry**：`vision.model_path` 支持 `models:/vehicle_detector/2` | model_registry.resolve_model_uri | ✅ |
| 4.6 | **Track/评估 run 关联**：count_vehicles_track 等评估 run 关联 model version | 待扩展 | — |

---

## 六、Phase 5：Labeling 工作流增强

| # | 任务 | 产出 |
|---|------|------|
| 5.1 | 与 Label Studio/CVAT 对接（可选） | 集成 |
| 5.2 | 标注完成后回写 DB，关联 batch/model 版本 | 与 Phase 3.3 联动 |

---

## 七、依赖关系

```
Phase 1 ──┬──> Phase 2  [可并行]
          │
          └──> Phase 3 (数据血缘) ──> Phase 4 (MLflow + Model Registry)
                    │
                    └──> Phase 5 (Labeling)
```

---

## 八、Model Registry 补充说明

| 项 | 说明 |
|----|------|
| **工具** | MLflow Model Registry（开源免费） |
| **能力** | 版本管理、阶段流转、血缘、按名加载 |
| **与 config** | `vision.model_path` 可填 `models:/vehicle_detector/2` 或本地路径 |
| **训练产出** | retrain 后 `mlflow.log_model()` 注册，替代手动拷到 models/ |

---

*文档版本：v1 | 2026-02*
