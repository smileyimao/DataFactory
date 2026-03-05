# V3 开发计划

> 基于 **docs/Roadmap.md** 整理，供审视与排期。v3 核心：**Auto-modality routing** + **模型就绪（数据血缘、MLflow 追溯）**。

**v2.10 已完成**：image/video 自动判定（`ingest.image_mode: "auto"`，按 raw 目录内容选择通路）。**v2.10.1**：混合模式 both（raw 有图+有视频时两类均处理）。详见 **docs/image_mode.md**。

**v3.0 已完成**：数据血缘（batch_lineage、label_import）、MLflow 血缘参数、Model Registry（models:/ URI、register_model.py）。详见 **CHANGELOG.md**、**docs/v3_task_list.md**。

---

## 一、阶段概览

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| **Phase 1** | Auto-modality routing（按文件自动识别与路由）— image/video ✅ v2.10；audio/lidar/vibration 待 v3 | P0 |
| **Phase 2** | 配置回退兼容 (Backward Compatibility) | P0 |
| **Phase 3** | 数据血缘与 Transform Log | P1 |
| **Phase 4** | MLflow 数据→模型追溯 | P1 |
| **Phase 5** | Labeling 工作流增强 | P2 |

---

## 二、Phase 1：Auto-modality Routing（详细步骤）

### 2.1 新建 modality_detector

| 步骤 | 任务 | 产出 |
|------|------|------|
| 1.1 | 新建 `engines/modality_detector.py` | `detect_modality(path) -> str` |
| 1.2 | 实现扩展名→modality 注册表（.mp4→video、.wav→audio、.pcd→lidar、.csv→vibration） | 字典/配置 |
| 1.3 | 可选：Magic bytes 判断（.bin 区分 lidar/vibration） | `_detect_by_magic(path)` |
| 1.4 | 可选：ffprobe 判断 .mp4 为 video 或纯 audio | `_detect_mp4_content(path)` |
| 1.5 | 未命中返回 `"unknown"` | - |

### 2.2 Ingest 改造

| 步骤 | 任务 | 产出 |
|------|------|------|
| 2.1 | 扩展 `get_video_paths()` → `scan_raw(cfg, paths)`，扫描 raw 下所有注册扩展名 | `scan_raw()` |
| 2.2 | 对每个文件调用 `detect_modality(path)` | 带 modality 标签的列表 |
| 2.3 | 按 modality 分组：`{video: [p1,p2], audio: [p3], unknown: [p4]}` | 分组结构 |
| 2.4 | unknown 文件移入 `quarantine/unknown_format/`（使用 retry_utils.safe_move） | pre_filter 扩展 |
| 2.5 | 确保 `quarantine/unknown_format/` 在 init_storage 或 ensure_dirs 中创建 | 配置 |

### 2.3 Pipeline 路由

| 步骤 | 任务 | 产出 |
|------|------|------|
| 3.1 | Pipeline 支持按 modality 分批：每批独立跑，batch_id 可带后缀 `Batch_20260224_video` | pipeline 改造 |
| 3.2 | 或：单批混合，pipeline 内按文件 modality 分发（推荐方案 A：分批） | 选定方案 |
| 3.3 | modality_filter 过滤：只处理白名单内 modality，其余跳过或进 quarantine | 过滤逻辑 |

### 2.4 Config 扩展

| 步骤 | 任务 | 产出 |
|------|------|------|
| 4.1 | 新增 `modality_filter: null` \| `"video"` \| `["video","audio"]` | config_loader |
| 4.2 | 新增 `unknown_format_action: "quarantine"` \| `"skip"` | config_loader |
| 4.3 | 扩展名注册表可配置（可选，初期可写死） | 可选 |

---

## 三、Phase 2：配置回退兼容

| 步骤 | 任务 | 产出 |
|------|------|------|
| 2.1 | config_loader：若存在 `modality` 且无 `modality_filter`，则 `modality_filter = [modality]` | 兼容逻辑 |
| 2.2 | 旧配置 `modality: "video"` 零改动继续工作 | 验证 |
| 2.3 | 单元测试：旧 config 加载后 modality_filter 正确 | test_config_loader |

---

## 四、Phase 3：数据血缘与 Transform Log — ✅ v3.0 已完成

| 步骤 | 任务 | 产出 | 状态 |
|------|------|------|------|
| 3.1 | **Transform Log**：记录抽帧率、压缩码率、分辨率等算子参数，可审计 | batch_lineage 表 + transform_params JSON | ✅ |
| 3.2 | **可视化血缘图谱**：按 Batch_ID 查看 raw → QC → refinery/inspection → labeled → training | scripts/query_lineage.py | ✅ |
| 3.3 | **标注回写关联**：标注完成后回写 DB，与批次/模型版本关联 | label_import 表 | ✅ |

---

## 五、Phase 4：MLflow 数据→模型追溯 — ✅ v3.0 已完成

| 步骤 | 任务 | 产出 | 状态 |
|------|------|------|------|
| 4.1 | **Dataset 关联**：MLflow run 关联 training 数据来源（batch_id、路径） | refinery_dir、inspection_dir、source_archive_dir 入 run params | ✅ |
| 4.2 | **Model lineage**：模型版本可追溯至训练数据批次与变换链路 | batch_lineage + label_import 元数据 | ✅ |
| 4.3 | **可复现**：给定模型版本，可反查其训练数据与 QC 参数 | query_lineage.py | ✅ |
| 4.4 | **Model Registry**：vision.model_path 支持 models:/name/version | engines/model_registry.py、scripts/mlflow/register_model.py | ✅ |

---

## 六、Phase 5：Labeling 工作流增强

| 步骤 | 任务 | 产出 |
|------|------|------|
| 5.1 | 与 Label Studio/CVAT 对接（可选） | 集成 |
| 5.2 | 标注完成后回写 DB，与批次/模型版本关联 | 与 Phase 3.3 联动 |
| **5.3** | **时序异常检测**：见下节 | 困难帧优先标注 |

---

### 6.1 Phase 5.3：时序异常检测（详细步骤）

**目标**：对视频流逐帧分析，自动识别检测结果突变的帧（前后有检测、中间骤降），标记为高优先级标注样本，作为 inspection 子集写入 manifest，CVAT 导出时用不同颜色/属性提示标注人员重点标注。

**检测逻辑**：
- 前后帧检测数 ≥ 3，中间帧 = 0 或 &lt; 前后均值 20% → 标记为 `temporal_anomaly`
- 窗口：连续 3～5 帧为零，前后有非零 → 该零窗口内所有帧均标记

| 步骤 | 任务 | 产出 |
|------|------|------|
| **5.3.1** | 新建 `engines/temporal_anomaly.py` | `detect_anomaly_frames(counts: List[int], cfg) -> Set[int]` |
| 5.3.2 | 实现核心逻辑：`counts[i]` 为第 i 帧检测数；若 `counts[i]==0` 且前后邻域（±1 或扩展）有 ≥3 检测，或连续 3～5 帧为 0 且窗口两端非零，则 `i ∈ anomaly` | 帧索引集合 |
| 5.3.3 | 配置：`temporal_anomaly.enabled: true`、`min_neighbor_count: 3`、`drop_ratio: 0.2`、`zero_window_min: 3`、`zero_window_max: 5` | `config/settings.yaml` 新增 `temporal_anomaly` 段 |
| **5.3.4** | 在 `labeling_export.auto_update_after_batch` 中接入：传入 `path_info`（含 `qc_detections_by_video`），对每条 inspection 项解析 `filename` 提取 `(video_basename, frame_idx)`，调用 `detect_anomaly_frames` 判断，若命中则 `item["reason"] = "temporal_anomaly"`、`item["priority"] = "high"` | manifest 扩展 |
| 5.3.5 | `export_for_cvat_native`：加载 manifest_for_labeling.json（若存在），按 `path` 提取 basename 建立 filename→reason 映射；对 `reason=temporal_anomaly` 的图片，其下所有 box 增加 `<attribute name="frame_reason">temporal_anomaly</attribute>`；meta 中为各 label 增加 `frame_reason` 属性 | CVAT 区分 |
| 5.3.6 | `config/ensure_dirs`：无需新增目录（anomaly 作为 inspection 子集，共用 `for_labeling/images/`） | - |
| 5.3.7 | 单元测试：`test_temporal_anomaly.py`，用例如 `[5,0,9]`、`[5,0,0,0,9]`、`[3,0,0,0,0,4]` 等 | 覆盖 |
| 5.3.8 | 新建 `_parse_inspection_filename(filename) -> (video_key, frame_idx)`：提取 `_f(\d{5})`，前缀与 `qc_detections_by_video` 的 key 做 normalize 匹配 | labeling_export 或 temporal_anomaly |

**验收标准（Phase 5.3）**：
- [ ] 视频 `[5,0,9]` 的中间帧、`[5,0,0,0,9]` 的零窗口帧被正确标记
- [ ] manifest 中对应条目含 `"reason": "temporal_anomaly"`、`"priority": "high"`
- [ ] export_for_cvat_native 导出的 XML 中，anomaly 帧的 box 有区分属性
- [ ] 配置 `temporal_anomaly.enabled: false` 时可关闭

**数据流**：
```
qc_detections_by_video (path_info)
    → temporal_anomaly.detect_anomaly_frames  per video
    → auto_update_after_batch 匹配 filename → frame_idx，写 reason
    → manifest_for_labeling.json 含 "reason": "temporal_anomaly"
    → export_for_cvat_native 读 reason，CVAT 中高亮/区分
```

**filename 解析**：inspection 输出为 `{safe_name}_f{f_idx:05d}.jpg`（如 `20260227_xxx_outputVideo_2.MOV_f00100.jpg`）。用正则 `_f(\d{5})\.(jpg|png)$` 提取 `frame_idx`，前缀为 `safe_name`（空格已变下划线）。`qc_detections_by_video` 的 key 为原始 video basename（可能含空格），匹配时需 normalize：`key.replace(" ", "_") == safe_name` 或维护双向映射。

---

## 七、依赖关系

```
Phase 1 (Auto-modality) ──┬──> Phase 2 (Backward Compat)  [可并行]
                          │
                          └──> Phase 3 (数据血缘) ──> Phase 4 (MLflow 追溯)
                                    │
                                    └──> Phase 5 (Labeling)
```

**建议排期**：Phase 1 + Phase 2 先做（约 2–3 周）；Phase 3/4/5 可迭代推进。

---

## 八、验收标准（Phase 1+2）

- [ ] 混合 raw 目录（.mp4 + .wav + .xyz）一次 scan，自动分流到对应 pipeline
- [ ] 未知格式进 `quarantine/unknown_format/`，有 WARNING 日志
- [ ] 旧配置 `modality: "video"` 无需修改即可运行
- [ ] 单元测试覆盖 modality_detector、config 兼容

---

*文档版本：v1 | 基于 Roadmap v2026.02*
